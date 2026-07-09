import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, InlineNotification, InlineLoading, Breadcrumb, BreadcrumbItem } from '@carbon/react';
import { DocumentDownload, Checkmark } from '@carbon/icons-react';
import { api, Project, ProcessingStatus } from '../api/client';
import StepProgress from '../components/StepProgress';

export default function ExportPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const projectId = id!;

  const [project, setProject] = useState<Project | null>(null);
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [rvLoading, setRvLoading] = useState(false);
  const [asmLoading, setAsmLoading] = useState(false);
  const [rvDone, setRvDone] = useState(false);
  const [asmDone, setAsmDone] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.projects.get(projectId).then(setProject).catch(() => {});
    api.processing.getStatus(projectId).then(setStatus).catch(() => {});
  }, [projectId]);

  const recordCount = status?.complete ?? 0;

  async function handleRVTools() {
    setRvLoading(true); setError('');
    try {
      const exp = await api.exports.generateRVTools(projectId);
      const resp = await api.exports.downloadRVTools(projectId, exp.id);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      // Use server-supplied filename so the file has a meaningful name, not just the UUID
      const disposition = resp.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename="?([^"]+)"?/);
      a.href = url;
      a.download = match ? match[1] : (exp as any).filename || `RVTools-${projectId}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      setRvDone(true);
    } catch { setError('Failed to generate RVTools export.'); }
    finally { setRvLoading(false); }
  }

  async function handleAssumptions() {
    setAsmLoading(true); setError('');
    try {
      const exp = await api.exports.generateAssumptions(projectId);
      const resp = await api.exports.downloadAssumptions(projectId, exp.id);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const disposition = resp.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename="?([^"]+)"?/);
      a.href = url;
      a.download = match ? match[1] : (exp as any).filename || `Assumptions-${projectId}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      setAsmDone(true);
    } catch { setError('Failed to generate assumptions report.'); }
    finally { setAsmLoading(false); }
  }

  return (
    <>
      <div className="page-header-band">
        <div className="page-header-inner">
          <Breadcrumb style={{ marginBottom: '0.5rem' }}>
            <BreadcrumbItem onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>Projects</BreadcrumbItem>
            {project && <BreadcrumbItem onClick={() => navigate(`/projects/${projectId}/upload`)} style={{ cursor: 'pointer' }}>{project.name}</BreadcrumbItem>}
            <BreadcrumbItem isCurrentPage>Export</BreadcrumbItem>
          </Breadcrumb>
          <h1 className="page-heading">Export</h1>
          <p className="page-description">
            Download the IBM Cool-ready RVTools file and the AI assumptions report.
          </p>
        </div>
      </div>

      <StepProgress projectId={projectId} currentStep={4} completedSteps={status?.is_complete ? [1, 2, 3] : [1]} />

      <div className="page-body">
        {error && (
          <InlineNotification
            kind="error"
            title="Export error"
            subtitle={error}
            lowContrast
            style={{ marginBottom: '1.5rem' }}
            onCloseButtonClick={() => setError('')}
          />
        )}

        <div className="export-card-row">
          {/* RVTools card */}
          <div className="export-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <DocumentDownload size={20} style={{ color: '#0f62fe' }} />
              <span className="export-card-title">RVTools Export</span>
            </div>
            <p className="export-card-desc">
              Standards-compliant .xlsx with 4 sheets (vInfo, vNetwork, vPartition, vHost),
              ready for the IBM Cool sizing tool. Contains <strong>{recordCount} records</strong>.
            </p>
            {rvLoading ? (
              <InlineLoading description="Generating…" />
            ) : (
              <Button
                renderIcon={rvDone ? Checkmark : DocumentDownload}
                kind={rvDone ? 'ghost' : 'primary'}
                onClick={handleRVTools}
                size="md"
              >
                {rvDone ? 'Downloaded ✓' : 'Download RVTools file'}
              </Button>
            )}
          </div>

          {/* Assumptions report card */}
          <div className="export-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <DocumentDownload size={20} style={{ color: '#6929c4' }} />
              <span className="export-card-title">AI Assumptions Report</span>
            </div>
            <p className="export-card-desc">
              Separate .xlsx documenting every value the AI inferred or defaulted —
              field name, assumed value, original customer value, reasoning, and confidence level.
            </p>
            {asmLoading ? (
              <InlineLoading description="Generating…" />
            ) : (
              <Button
                renderIcon={asmDone ? Checkmark : DocumentDownload}
                kind={asmDone ? 'ghost' : 'secondary'}
                onClick={handleAssumptions}
                size="md"
              >
                {asmDone ? 'Downloaded ✓' : 'Download Assumptions report'}
              </Button>
            )}
          </div>
        </div>

        <div className="step-actions">
          <Button kind="ghost" onClick={() => navigate(`/projects/${projectId}/review`)}>
            ← Back to Review
          </Button>
          <Button kind="ghost" onClick={() => navigate('/')}>
            Back to Projects
          </Button>
        </div>
      </div>
    </>
  );
}
