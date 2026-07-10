import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, InlineNotification, InlineLoading, Breadcrumb, BreadcrumbItem } from '@carbon/react';
import { DocumentDownload, Checkmark, Information, Lightning } from '@carbon/icons-react';
import { api, Project, ProcessingStatus } from '../api/client';
import StepProgress from '../components/StepProgress';

// ---------------------------------------------------------------------------
// Inline tooltip component
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
          width: 280,
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
// Download helper
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

  const [project, setProject]           = useState<Project | null>(null);
  const [status, setStatus]             = useState<ProcessingStatus | null>(null);
  const [powervsCount, setPowervsCount] = useState(0);

  // x86 exports
  const [coolLoading, setCoolLoading]   = useState(false);
  const [pureLoading, setPureLoading]   = useState(false);
  const [asmLoading, setAsmLoading]     = useState(false);
  const [coolDone, setCoolDone]         = useState(false);
  const [pureDone, setPureDone]         = useState(false);
  const [asmDone, setAsmDone]           = useState(false);

  // PowerVS exports
  const [pvsCoolLoading, setPvsCoolLoading] = useState(false);
  const [pvsAsmLoading, setPvsAsmLoading]   = useState(false);
  const [pvsCoolDone, setPvsCoolDone]       = useState(false);
  const [pvsAsmDone, setPvsAsmDone]         = useState(false);

  const [error, setError] = useState('');

  useEffect(() => {
    api.projects.get(projectId).then(setProject).catch(() => {});
    api.processing.getStatus(projectId).then(setStatus).catch(() => {});
    api.exports.getPowerVSCount(projectId).then(r => setPowervsCount(r.powervs_count)).catch(() => {});
  }, [projectId]);

  const recordCount = status?.complete ?? 0;
  const x86Count = recordCount - powervsCount;

  // ── x86 handlers ──────────────────────────────────────────────────────────
  async function handleCoolExport() {
    setCoolLoading(true); setError('');
    try {
      const exp = await api.exports.generateRVTools(projectId);
      const resp = await api.exports.downloadRVTools(projectId, exp.id);
      await triggerDownload(resp, (exp as any).filename || `RVTools_x86_${projectId}.xlsx`);
      setCoolDone(true);
    } catch { setError('Failed to generate x86 Cloud Solutioning Tool export.'); }
    finally { setCoolLoading(false); }
  }

  async function handlePureExport() {
    setPureLoading(true); setError('');
    try {
      const exp = await api.exports.generateRVToolsPure(projectId);
      const resp = await api.exports.downloadRVToolsPure(projectId, exp.id);
      await triggerDownload(resp, (exp as any).filename || `RVToolsPure_x86_${projectId}.xlsx`);
      setPureDone(true);
    } catch { setError('Failed to generate x86 RVTools export.'); }
    finally { setPureLoading(false); }
  }

  async function handleAssumptions() {
    setAsmLoading(true); setError('');
    try {
      const exp = await api.exports.generateAssumptions(projectId);
      const resp = await api.exports.downloadAssumptions(projectId, exp.id);
      await triggerDownload(resp, (exp as any).filename || `Assumptions_${projectId}.xlsx`);
      setAsmDone(true);
    } catch { setError('Failed to generate assumptions report.'); }
    finally { setAsmLoading(false); }
  }

  // ── PowerVS handlers ──────────────────────────────────────────────────────
  async function handlePVSCoolExport() {
    setPvsCoolLoading(true); setError('');
    try {
      const exp = await api.exports.generateRVToolsPowerVS(projectId);
      const resp = await api.exports.downloadRVToolsPowerVS(projectId, exp.id);
      await triggerDownload(resp, (exp as any).filename || `RVTools_PowerVS_${projectId}.xlsx`);
      setPvsCoolDone(true);
    } catch { setError('Failed to generate PowerVS Cloud Solutioning Tool export.'); }
    finally { setPvsCoolLoading(false); }
  }

  async function handlePVSAssumptions() {
    setPvsAsmLoading(true); setError('');
    try {
      const exp = await api.exports.generateAssumptionsPowerVS(projectId);
      const resp = await api.exports.downloadAssumptionsPowerVS(projectId, exp.id);
      await triggerDownload(resp, (exp as any).filename || `Assumptions_PowerVS_${projectId}.xlsx`);
      setPvsAsmDone(true);
    } catch { setError('Failed to generate PowerVS assumptions report.'); }
    finally { setPvsAsmLoading(false); }
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

        {/* Separation banner — only shown when both types coexist */}
        {powervsCount > 0 && x86Count > 0 && (
          <InlineNotification
            kind="info"
            title="Workloads automatically separated"
            subtitle={`This project contains ${x86Count} x86/VPC server${x86Count !== 1 ? 's' : ''} and ${powervsCount} PowerVS (AIX/IBM i) server${powervsCount !== 1 ? 's' : ''}. They have been automatically separated into two independent exports below. Upload each file to IBM Cool separately to obtain separate pricing proposals.`}
            lowContrast
            style={{ marginBottom: '1.5rem' }}
          />
        )}

        {/* ── x86 / VPC Section ──────────────────────────────────────────── */}
        {x86Count > 0 && (
          <>
            <h2 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#525252', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '1rem' }}>
              x86 / VPC Workloads
              <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0, marginLeft: '0.5rem', color: '#6f6f6f' }}>
                ({x86Count} server{x86Count !== 1 ? 's' : ''})
              </span>
            </h2>
            <div className="export-card-row" style={{ gridTemplateColumns: '1fr 1fr 1fr', marginBottom: '2.5rem' }}>

              {/* Card 1: Cool Tool Export (4-sheet — the input IBM Cool actually reads) */}
              <div className="export-card">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <DocumentDownload size={20} style={{ color: '#0f62fe', flexShrink: 0 }} />
                  <span className="export-card-title">Cool Tool Export</span>
                  <InfoTooltip text="4-sheet RVTools workbook (vInfo, vNetwork, vPartition, vHost) — the format IBM Cool reads as input. Upload this file directly to the IBM Cloud Solutioning Tool to generate VPC pricing. File is named COOL_<ProjectName>_<date>.xlsx." />
                  <span style={{ fontSize: '0.75rem', color: '#525252', display: 'block', width: '100%', marginTop: '0.1rem' }}>(IBM Cool input — COOL_ProjectName_date.xlsx)</span>
                </div>
                <p className="export-card-desc">
                  4-sheet workbook for the IBM Cloud Solutioning Tool (IBM Cool). Contains <strong>{x86Count} x86 records</strong>. Upload this file to IBM Cool to generate VPC pricing.
                </p>
                {pureLoading ? (
                  <InlineLoading description="Generating…" />
                ) : (
                  <Button renderIcon={pureDone ? Checkmark : DocumentDownload} kind={pureDone ? 'ghost' : 'primary'} onClick={handlePureExport} size="md">
                    {pureDone ? 'Downloaded ✓' : 'Download Cool Tool export'}
                  </Button>
                )}
              </div>

              {/* Card 2: Full RVTools Export (22-sheet — for VCF Migration Lite / advanced tools) */}
              <div className="export-card">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <DocumentDownload size={20} style={{ color: '#0043ce', flexShrink: 0 }} />
                  <span className="export-card-title">RVTools Export</span>
                  <InfoTooltip text="22-sheet RVTools workbook including all standard RVTools 4.x tabs. Required by VCF Migration Lite and other tools that validate for all 22 sheets on import. x86 records only." />
                  <span style={{ fontSize: '0.75rem', color: '#525252', display: 'block', width: '100%', marginTop: '0.1rem' }}>(VCF Migration Lite / full RVTools format)</span>
                </div>
                <p className="export-card-desc">
                  Full 22-sheet RVTools format for VCF Migration Lite and other tools requiring all RVTools tabs. Contains <strong>{x86Count} records</strong>.
                </p>
                {coolLoading ? (
                  <InlineLoading description="Generating…" />
                ) : (
                  <Button renderIcon={coolDone ? Checkmark : DocumentDownload} kind={coolDone ? 'ghost' : 'secondary'} onClick={handleCoolExport} size="md">
                    {coolDone ? 'Downloaded ✓' : 'Download RVTools export'}
                  </Button>
                )}
              </div>

              {/* Card 3: Assumptions Report */}
              <div className="export-card">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <DocumentDownload size={20} style={{ color: '#6929c4', flexShrink: 0 }} />
                  <span className="export-card-title">AI Assumptions Report</span>
                  <InfoTooltip text="Separate .xlsx documenting every AI inference. Includes an 'Excluded Servers' sheet listing any servers you excluded in the Review step with their reasons." />
                </div>
                <p className="export-card-desc">
                  AI decisions for all records. Includes an Excluded Servers audit sheet.
                </p>
                {asmLoading ? (
                  <InlineLoading description="Generating…" />
                ) : (
                  <Button renderIcon={asmDone ? Checkmark : DocumentDownload} kind={asmDone ? 'ghost' : 'tertiary'} onClick={handleAssumptions} size="md">
                    {asmDone ? 'Downloaded ✓' : 'Download Assumptions report'}
                  </Button>
                )}
              </div>
            </div>
          </>
        )}

        {/* ── PowerVS Section ────────────────────────────────────────────── */}
        {powervsCount > 0 && (
          <>
            <div style={{ borderTop: '2px solid #6929c4', paddingTop: '1.5rem', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <Lightning size={20} style={{ color: '#6929c4' }} />
                <h2 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#6929c4', textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>
                  PowerVS Workloads
                  <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0, marginLeft: '0.5rem', color: '#8a3ffc' }}>
                    ({powervsCount} AIX/IBM i server{powervsCount !== 1 ? 's' : ''})
                  </span>
                </h2>
              </div>
              <p style={{ fontSize: '0.8125rem', color: '#525252', margin: 0 }}>
                These servers run AIX or IBM i and have been automatically designated as IBM Power Virtual Server workloads.
                Upload the exports below to IBM Cool <strong>separately</strong> from the x86 exports to get dedicated PowerVS pricing.
              </p>
            </div>

            <div className="export-card-row" style={{ gridTemplateColumns: '1fr 1fr', marginBottom: '2.5rem' }}>

              {/* Card 4: PowerVS Cool Tool Export */}
              <div className="export-card" style={{ borderTop: '3px solid #6929c4' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <DocumentDownload size={20} style={{ color: '#6929c4', flexShrink: 0 }} />
                  <span className="export-card-title">PowerVS Cool Tool Export</span>
                  <InfoTooltip text="4-sheet RVTools workbook for IBM Cool — PowerVS (AIX/IBM i) records only. Upload this to IBM Cool separately from the x86 Cool Tool export to get dedicated IBM Power Virtual Server pricing." />
                  <span style={{ fontSize: '0.75rem', color: '#6929c4', display: 'block', width: '100%', marginTop: '0.1rem' }}>(IBM Cool input — COOL_PowerVS_ProjectName_date.xlsx)</span>
                </div>
                <p className="export-card-desc">
                  4-sheet workbook for IBM Cool. Contains <strong>{powervsCount} PowerVS records</strong>. x86 records excluded. Upload separately from the x86 Cool Tool export.
                </p>
                {pvsCoolLoading ? (
                  <InlineLoading description="Generating…" />
                ) : (
                  <Button renderIcon={pvsCoolDone ? Checkmark : DocumentDownload} kind={pvsCoolDone ? 'ghost' : 'primary'} onClick={handlePVSCoolExport} size="md">
                    {pvsCoolDone ? 'Downloaded ✓' : 'Download PowerVS Cool Tool export'}
                  </Button>
                )}
              </div>

              {/* Card 5: PowerVS Assumptions */}
              <div className="export-card" style={{ borderTop: '3px solid #6929c4' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <DocumentDownload size={20} style={{ color: '#8a3ffc', flexShrink: 0 }} />
                  <span className="export-card-title">PowerVS AI Assumptions Report</span>
                  <InfoTooltip text="AI decisions and inferences for PowerVS (AIX/IBM i) records only." />
                </div>
                <p className="export-card-desc">
                  AI decisions for PowerVS records only.
                </p>
                {pvsAsmLoading ? (
                  <InlineLoading description="Generating…" />
                ) : (
                  <Button renderIcon={pvsAsmDone ? Checkmark : DocumentDownload} kind={pvsAsmDone ? 'ghost' : 'tertiary'} onClick={handlePVSAssumptions} size="md">
                    {pvsAsmDone ? 'Downloaded ✓' : 'Download PowerVS Assumptions'}
                  </Button>
                )}
              </div>
            </div>
          </>
        )}

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
