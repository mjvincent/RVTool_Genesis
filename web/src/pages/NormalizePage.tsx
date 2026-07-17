import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Button, InlineNotification, ProgressBar,
  Breadcrumb, BreadcrumbItem, Loading,
} from '@carbon/react';
import { Checkmark, ChevronRight, Reset } from '@carbon/icons-react';
import { api, Project, ProcessingStatus } from '../api/client';
import StepProgress from '../components/StepProgress';

export default function NormalizePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const projectId = id!;

  const [project, setProject]         = useState<Project | null>(null);
  const [recordCount, setRecordCount] = useState<number | null>(null);
  const [status, setStatus]           = useState<ProcessingStatus | null>(null);
  const [loading, setLoading]         = useState(true);
  const [processing, setProcessing]   = useState(false);
  const [processError, setProcessError] = useState('');
  const [resetMsg, setResetMsg]       = useState('');

  // Per-record heartbeat: seconds elapsed since last status change
  const [heartbeat, setHeartbeat]     = useState(0);
  const lastCompleteRef               = useRef<number>(0);
  const heartbeatRef                  = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollRef                       = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollIntervalRef               = useRef<number>(2000);
  const pollFailuresRef               = useRef<number>(0);

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
          const s = statusResp.value;
          setStatus(s);
          lastCompleteRef.current = s.complete;
          // Only resume poll if work has actually started — not for a fresh all-pending project
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
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
      pollIntervalRef.current = 2000;
      pollFailuresRef.current = 0;
      setProcessError('');
      setResetMsg('');
    };
  }, [projectId]);

  // Auto-start polling when processing flag is set
  useEffect(() => {
    if (processing && !pollRef.current) {
      startPolling();
    }
    if (processing && !heartbeatRef.current) {
      startHeartbeat();
    }
  }, [processing]); // eslint-disable-line react-hooks/exhaustive-deps

  function startHeartbeat() {
    if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    setHeartbeat(0);
    heartbeatRef.current = setInterval(() => {
      setHeartbeat(h => h + 1);
    }, 1000);
  }

  function startPolling(interval = pollIntervalRef.current) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollIntervalRef.current = interval;
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.processing.getStatus(projectId);
        // Successful response — reset backoff
        pollFailuresRef.current = 0;
        if (pollIntervalRef.current > 2000) {
          // Restart at normal speed
          startPolling(2000);
          return;
        }
        setStatus(s);
        // Reset heartbeat counter whenever a new record completes
        if (s.complete > lastCompleteRef.current) {
          lastCompleteRef.current = s.complete;
          setHeartbeat(0);
        }
        if (s.is_complete || (s.total > 0 && s.pending === 0 && s.processing === 0)) {
          clearInterval(pollRef.current!);
          pollRef.current = null;
          if (heartbeatRef.current) { clearInterval(heartbeatRef.current); heartbeatRef.current = null; }
          setProcessing(false);
          setHeartbeat(0);
        }
      } catch {
        pollFailuresRef.current += 1;
        if (pollFailuresRef.current >= 3) {
          // Back off: double interval, cap at 30s
          const next = Math.min(pollIntervalRef.current * 2, 30000);
          startPolling(next);
        }
      }
    }, interval);
  }

  async function handleProcess() {
    setProcessing(true);
    setProcessError('');
    lastCompleteRef.current = status?.complete ?? 0;
    setHeartbeat(0);
    try {
      await api.processing.start(projectId);
      startPolling();
      startHeartbeat();
    } catch {
      setProcessError(`Could not start normalization: ${(err as any)?.detail || (err as any)?.message || 'Please try again.'}`);
      setProcessing(false);
    }
  }

  async function handleResetStuck() {
    setResetMsg('');
    try {
      const r = await api.processing.resetStuck(projectId);
      if (r.reset_count > 0) {
        setResetMsg(`Reset ${r.reset_count} stuck record(s). Resuming…`);
        // Re-fetch status, then restart processing
        const s = await api.processing.getStatus(projectId);
        setStatus(s);
        lastCompleteRef.current = s.complete;
        if (s.pending > 0) {
          setProcessing(true);
          await api.processing.start(projectId);
          startPolling();
          startHeartbeat();
        }
      } else {
        setResetMsg('No stuck records found.');
      }
    } catch (err) {
      setResetMsg(`Reset failed: ${(err as any)?.detail || (err as any)?.message || 'try again.'}`);
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <Loading description="Loading project…" withOverlay={false} />
      </div>
    );
  }

  if (recordCount === 0) {
    navigate(`/projects/${projectId}/upload`);
    return null;
  }

  const isComplete   = !!(status?.is_complete && (status?.total ?? 0) > 0);
  const pct          = status && status.total > 0
    ? Math.round((status.complete / status.total) * 100)
    : 0;
  const completedSteps: number[] = isComplete ? [1, 2] : [1];
  const hasErrors    = (status?.error ?? 0) > 0;
  const isStuck      = processing && heartbeat > 90;   // >90 s on same record = warn
  const isInProgress = processing || (status && (status.complete > 0 || status.processing > 0) && !status.is_complete);

  // Format elapsed time as m:ss
  function fmtElapsed(secs: number) {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

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

        {resetMsg && (
          <InlineNotification
            kind={resetMsg.includes('failed') ? 'error' : 'info'}
            title={resetMsg}
            subtitle=""
            lowContrast
            style={{ marginBottom: '1rem' }}
            onCloseButtonClick={() => setResetMsg('')}
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
          ) : isInProgress ? (
            <>
              {/* Progress bar + counts */}
              <div className="norm-progress-label">
                <span>
                  <strong>{status?.complete ?? 0}</strong> of <strong>{status?.total ?? recordCount}</strong> records normalized
                  {(status?.error ?? 0) > 0 && <span style={{ color: '#da1e28', marginLeft: '0.5rem' }}>({status!.error} errors)</span>}
                </span>
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>{pct}%</span>
              </div>
              <ProgressBar value={pct} max={100} label="" helperText="" />

              {/* Per-record heartbeat row */}
              <div style={{
                marginTop: '0.75rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                fontSize: '0.875rem',
                color: isStuck ? '#f1c21b' : '#525252',
              }}>
                {/* Animated thinking dot */}
                <span style={{
                  display: 'inline-block',
                  width: 10, height: 10,
                  borderRadius: '50%',
                  background: isStuck ? '#f1c21b' : '#0f62fe',
                  animation: 'norm-pulse 1.2s ease-in-out infinite',
                }} />
                {isStuck ? (
                  <span>⚠ Current record is taking longer than expected ({fmtElapsed(heartbeat)}).</span>
                ) : (
                  <span>Processing record {(status?.complete ?? 0) + 1} of {status?.total ?? recordCount} — {fmtElapsed(heartbeat)} elapsed on this record…</span>
                )}
              </div>
              {status?.current_record_name && (
                <div style={{ marginTop: '0.25rem', fontSize: '0.8125rem', color: '#6f6f6f', paddingLeft: '1.375rem' }}>
                  Currently processing: <strong>{status.current_record_name}</strong>
                </div>
              )}
              {/* Reset stuck button — shown after 90 s on same record */}
              {isStuck && (
                <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                  <Button
                    kind="tertiary"
                    size="sm"
                    renderIcon={Reset}
                    onClick={handleResetStuck}
                  >
                    Reset stuck &amp; resume
                  </Button>
                  <span style={{ fontSize: '0.8125rem', color: '#525252' }}>
                    This will skip the stuck record and continue with the remaining ones.
                  </span>
                </div>
              )}

              <p style={{ marginTop: '0.75rem', fontSize: '0.8125rem', color: '#6f6f6f' }}>
                Each record takes ~6–15 s depending on model speed. Average per batch: ~{Math.round((status?.total ?? recordCount ?? 0) * 10 / 60)} minutes total.
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
