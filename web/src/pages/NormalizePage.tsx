import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, InlineNotification, ProgressBar, Breadcrumb, BreadcrumbItem, Loading } from '@carbon/react';
import { Checkmark, ChevronRight } from '@carbon/icons-react';
import { api, Project, ProcessingStatus } from '../api/client';
import StepProgress from '../components/StepProgress';

export default function NormalizePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const projectId = id!;

  const [project, setProject] = useState<Project | null>(null);
  const [recordCount, setRecordCount] = useState<number | null>(null);
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [processError, setProcessError] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const [proj, recordsResp, statusResp] = await Promise.allSettled([
          api.projects.get(projectId),
          api.uploads.getRecords(projectId),
          api.processing.getStatus(projectId),
        ]);

        if (cancelled) return;

        if (proj.status === 'fulfilled') setProject(proj.value);
        if (recordsResp.status === 'fulfilled') {
          setRecordCount(recordsResp.value.records?.length ?? 0);
        } else {
          setRecordCount(0);
        }
        if (statusResp.status === 'fulfilled') {
          setStatus(statusResp.value);
          // Resume poll only if work has actually started (complete > 0 or a record
          // is mid-flight). Do NOT set processing=true for a fresh project where
          // everything is still pending — that hides the "Start" button.
          const s = statusResp.value;
          if (!s.is_complete && (s.complete > 0 || s.processing > 0)) {
            setProcessing(true);
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    init();
    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [projectId]);

  // Auto-start polling when processing flag is set (covers both fresh start and page-refresh resume)
  useEffect(() => {
    if (processing && !pollRef.current) {
      startPolling();
    }
  }, [processing]); // eslint-disable-line react-hooks/exhaustive-deps

  function startPolling() {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.processing.getStatus(projectId);
        setStatus(s);
        if (s.is_complete || (s.total > 0 && s.pending === 0 && s.processing === 0)) {
          clearInterval(pollRef.current!);
          pollRef.current = null;
          setProcessing(false);
        }
      } catch { /* keep polling */ }
    }, 2000);
  }

  async function handleProcess() {
    setProcessing(true);
    setProcessError('');
    try {
      await api.processing.start(projectId);
      startPolling();
    } catch {
      setProcessError('Could not start normalization. Please try again.');
      setProcessing(false);
    }
  }

  // Still loading initial data — show full-page spinner
  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <Loading description="Loading project…" withOverlay={false} />
      </div>
    );
  }

  // No records uploaded — redirect back
  if (recordCount === 0) {
    navigate(`/projects/${projectId}/upload`);
    return null;
  }

  const isComplete = !!(status?.is_complete && (status?.total ?? 0) > 0);
  const pct = status && status.total > 0
    ? Math.round((status.complete / status.total) * 100)
    : 0;
  // Steps 1 (Upload) is always done if we're here; step 2 (Normalize) is done when complete
  const completedSteps: number[] = isComplete ? [1, 2] : [1];

  const hasErrors = (status?.error ?? 0) > 0;

  return (
    <>
      <div className="page-header-band">
        <div className="page-header-inner">
          <Breadcrumb style={{ marginBottom: '0.5rem' }}>
            <BreadcrumbItem onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>Projects</BreadcrumbItem>
            {project && (
              <BreadcrumbItem onClick={() => navigate(`/projects/${projectId}/upload`)} style={{ cursor: 'pointer' }}>
                {project.name}
              </BreadcrumbItem>
            )}
            <BreadcrumbItem isCurrentPage>Normalize</BreadcrumbItem>
          </Breadcrumb>
          <h1 className="page-heading">AI Normalization</h1>
          <p className="page-description">
            The AI reads each record and maps it to a standard RVTools format, filling gaps with IBM defaults.
          </p>
        </div>
      </div>

      <StepProgress projectId={projectId} currentStep={2} completedSteps={completedSteps} />

      <div className="page-body">
        {processError && (
          <InlineNotification
            kind="error"
            title="Processing error"
            subtitle={processError}
            lowContrast
            style={{ marginBottom: '1rem' }}
            onCloseButtonClick={() => setProcessError('')}
          />
        )}

        <div className="ibm-card">
          {isComplete ? (
            <>
              <div className="norm-complete-banner">
                <Checkmark size={20} />
                <span>
                  Normalization complete — {status!.complete} of {status!.total} records processed
                  {hasErrors && ` (${status!.error} failed — see Review step to retry)`}
                </span>
              </div>
              <div style={{ marginTop: '1rem' }}>
                <ProgressBar value={100} max={100} label="" helperText="" />
              </div>
            </>
          ) : processing || (status && (status.complete > 0 || status.processing > 0) && !status.is_complete) ? (
            <>
              <div className="norm-progress-label">
                <span>{status?.complete ?? 0} of {status?.total ?? recordCount} records normalized</span>
                <span>{pct}%</span>
              </div>
              <ProgressBar value={pct} max={100} label="" helperText="" />
              <p style={{ marginTop: '0.75rem', fontSize: '0.875rem', color: '#525252' }}>
                Processing… this may take a few minutes depending on model speed.
              </p>
            </>
          ) : (
            <>
              <p style={{ fontSize: '0.9375rem', color: '#161616', margin: '0 0 0.5rem' }}>
                <strong>{recordCount}</strong> records ready for normalization
              </p>
              <p style={{ fontSize: '0.875rem', color: '#525252', margin: '0 0 1.5rem', lineHeight: 1.6 }}>
                The AI will map each server record to the RVTools vInfo, vNetwork, vPartition, and vHost schema.
                Missing values will be filled with IBM standard defaults and recorded as assumptions.
              </p>
              <Button onClick={handleProcess} renderIcon={ChevronRight}>
                Start AI Normalization
              </Button>
            </>
          )}
        </div>

        {hasErrors && isComplete && (
          <InlineNotification
            kind="warning"
            title={`${status!.error} record(s) failed`}
            subtitle="You can retry individual records from the Review step, or proceed with the successfully normalized records."
            lowContrast
            style={{ marginTop: '1rem' }}
          />
        )}

        <div className="step-actions">
          <Button
            renderIcon={ChevronRight}
            onClick={() => navigate(`/projects/${projectId}/review`)}
            disabled={!isComplete}
          >
            Continue to Review
          </Button>
          <Button kind="ghost" onClick={() => navigate(`/projects/${projectId}/upload`)}>
            ← Back to Upload
          </Button>
        </div>
      </div>
    </>
  );
}
