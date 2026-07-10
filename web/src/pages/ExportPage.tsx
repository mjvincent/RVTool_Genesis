import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, InlineNotification, InlineLoading, Breadcrumb, BreadcrumbItem } from '@carbon/react';
import { DocumentDownload, Checkmark, Information } from '@carbon/icons-react';
import { api, Project, ProcessingStatus } from '../api/client';
import StepProgress from '../components/StepProgress';

// ---------------------------------------------------------------------------
// Inline tooltip component — Carbon Tooltip requires specific setup; a simple
// hover tooltip keeps the dependency minimal.
// ---------------------------------------------------------------------------
function InfoTooltip({ text }: { text: string }) {
  const [visible, setVisible] = useState(false);
  return (
    <span
      style={{ position: 'relative', display: 'inline-flex', verticalAlign: 'middle', marginLeft: '0.35rem', cursor: 'pointer' }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
      tabIndex={0}
      aria-label={text}
    >
      <Information size={16} style={{ color: '#6f6f6f' }} />
      {visible && (
        <span style={{
          position: 'absolute',
          bottom: 'calc(100% + 8px)',
          left: '50%',
          transform: 'translateX(-50%)',
          background: '#161616',
          color: '#f4f4f4',
          fontSize: '0.8125rem',
          lineHeight: 1.5,
          padding: '0.5rem 0.75rem',
          borderRadius: 2,
          width: 260,
          zIndex: 9999,
          boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          whiteSpace: 'normal',
          pointerEvents: 'none',
        }}>
          {text}
        </span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Download helper — re-used for all three exports
// ---------------------------------------------------------------------------
async function triggerDownload(response: Response, fallback: string) {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="?([^"]+)"?/);
  a.href = url;
  a.download = match ? match[1] : fallback;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function ExportPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const projectId = id!;

  const [project, setProject]     = useState<Project | null>(null);
  const [status, setStatus]       = useState<ProcessingStatus | null>(null);
  const [coolLoading, setCoolLoading]   = useState(false);
  const [pureLoading, setPureLoading]   = useState(false);
  const [asmLoading, setAsmLoading]     = useState(false);
  const [coolDone, setCoolDone]   = useState(false);
  const [pureDone, setPureDone]   = useState(false);
  const [asmDone, setAsmDone]     = useState(false);
  const [error, setError]         = useState('');

  useEffect(() => {
    api.projects.get(projectId).then(setProject).catch(() => {});
    api.processing.getStatus(projectId).then(setStatus).catch(() => {});
  }, [projectId]);

  const recordCount = status?.complete ?? 0;

  // --- Cloud Solutioning Tool (IBM Cool) — 22 sheets ---
  async function handleCoolExport() {
    setCoolLoading(true); setError('');
    try {
      const exp = await api.exports.generateRVTools(projectId);
      const resp = await api.exports.downloadRVTools(projectId, exp.id);
      await triggerDownload(resp, (exp as any).filename || `RVTools-Cool-${projectId}.xlsx`);
      setCoolDone(true);
    } catch { setError('Failed to generate Cloud Solutioning Tool export.'); }
    finally { setCoolLoading(false); }
  }

  // --- Pure RVTools Export — 4 sheets ---
  async function handlePureExport() {
    setPureLoading(true); setError('');
    try {
      const exp = await api.exports.generateRVToolsPure(projectId);
      const resp = await api.exports.downloadRVToolsPure(projectId, exp.id);
      await triggerDownload(resp, (exp as any).filename || `RVToolsPure-${projectId}.xlsx`);
      setPureDone(true);
    } catch { setError('Failed to generate RVTools export.'); }
    finally { setPureLoading(false); }
  }

  // --- Assumptions Report ---
  async function handleAssumptions() {
    setAsmLoading(true); setError('');
    try {
      const exp = await api.exports.generateAssumptions(projectId);
      const resp = await api.exports.downloadAssumptions(projectId, exp.id);
      await triggerDownload(resp, (exp as any).filename || `Assumptions-${projectId}.xlsx`);
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
            {project && (
              <BreadcrumbItem onClick={() => navigate(`/projects/${projectId}/upload`)} style={{ cursor: 'pointer' }}>
                {project.name}
              </BreadcrumbItem>
            )}
            <BreadcrumbItem isCurrentPage>Export</BreadcrumbItem>
          </Breadcrumb>
          <h1 className="page-heading">Export</h1>
          <p className="page-description">
            Download your outputs below. Each format serves a different target tool.
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

        <div className="export-card-row" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>

          {/* ── Card 1: Cloud Solutioning Tool (IBM Cool) ── */}
          <div className="export-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
              <DocumentDownload size={20} style={{ color: '#0f62fe', flexShrink: 0 }} />
              <span className="export-card-title">Cloud Solutioning Tool Export</span>
              <InfoTooltip text="22-sheet RVTools workbook required by IBM Cool and VCF Migration Lite. Includes vInfo, vDisk, vCPU, vMemory, vNetwork, vHost, and all remaining stub sheets that these tools validate on import. Upload this file to the IBM Cloud Solutioning Tool (IBM Cool)." />
              <span style={{ fontSize: '0.75rem', color: '#525252', display: 'block', width: '100%', marginTop: '0.1rem' }}>(IBM Cool)</span>
            </div>
            <p className="export-card-desc">
              22-sheet workbook for the IBM Cloud Solutioning Tool and VCF Migration Lite.
              Includes all required tabs for format validation.
              Contains <strong>{recordCount} records</strong>.
            </p>
            {coolLoading ? (
              <InlineLoading description="Generating…" />
            ) : (
              <Button
                renderIcon={coolDone ? Checkmark : DocumentDownload}
                kind={coolDone ? 'ghost' : 'primary'}
                onClick={handleCoolExport}
                size="md"
              >
                {coolDone ? 'Downloaded ✓' : 'Download Cool export'}
              </Button>
            )}
          </div>

          {/* ── Card 2: Pure RVTools Export ── */}
          <div className="export-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
              <DocumentDownload size={20} style={{ color: '#0043ce', flexShrink: 0 }} />
              <span className="export-card-title">RVTools Export</span>
              <InfoTooltip text="Standard 4-sheet RVTools workbook (vInfo, vNetwork, vPartition, vHost) — the same format produced by the native RVTools application. Use this with any tool that expects a plain RVTools export, or for importing into other IBM or third-party sizing tools." />
            </div>
            <p className="export-card-desc">
              Standard 4-sheet RVTools format (vInfo, vNetwork, vPartition, vHost) —
              the native RVTools output format. Compatible with any RVTools-aware tool.
              Contains <strong>{recordCount} records</strong>.
            </p>
            {pureLoading ? (
              <InlineLoading description="Generating…" />
            ) : (
              <Button
                renderIcon={pureDone ? Checkmark : DocumentDownload}
                kind={pureDone ? 'ghost' : 'secondary'}
                onClick={handlePureExport}
                size="md"
              >
                {pureDone ? 'Downloaded ✓' : 'Download RVTools file'}
              </Button>
            )}
          </div>

          {/* ── Card 3: AI Assumptions Report ── */}
          <div className="export-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <DocumentDownload size={20} style={{ color: '#6929c4', flexShrink: 0 }} />
              <span className="export-card-title">AI Assumptions Report</span>
              <InfoTooltip text="Separate .xlsx documenting every value the AI inferred, defaulted, or converted — field name, assumed value, original customer value, reasoning, and confidence level (High / Medium / Low). Use this to review and validate the AI's decisions before submitting the RVTools file." />
            </div>
            <p className="export-card-desc">
              Documents every AI inference — field name, assumed value, original value,
              reasoning, and confidence level. Keep for audit and review purposes.
            </p>
            {asmLoading ? (
              <InlineLoading description="Generating…" />
            ) : (
              <Button
                renderIcon={asmDone ? Checkmark : DocumentDownload}
                kind={asmDone ? 'ghost' : 'tertiary'}
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
