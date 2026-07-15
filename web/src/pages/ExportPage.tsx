import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, InlineNotification, InlineLoading, Breadcrumb, BreadcrumbItem, Select, SelectItem } from '@carbon/react';
import { DocumentDownload, Checkmark, Information, Lightning, Edit } from '@carbon/icons-react';
import { api, Project, ProcessingStatus, IBM_VPC_REGIONS, IBM_POWERVS_REGIONS } from '../api/client';
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

  // Region edit state
  const [editingRegion, setEditingRegion] = useState(false);
  const [editRegion, setEditRegion]       = useState('');
  const [editZone, setEditZone]           = useState('');
  const [regionSaving, setRegionSaving]   = useState(false);

  // x86 exports
  const [vpcLoading, setVpcLoading]     = useState(false);
  const [pureLoading, setPureLoading]   = useState(false);
  const [asmLoading, setAsmLoading]     = useState(false);
  const [vpcDone, setVpcDone]           = useState(false);
  const [pureDone, setPureDone]         = useState(false);
  const [asmDone, setAsmDone]           = useState(false);

  // PowerVS region edit state
  const [editingPvsRegion, setEditingPvsRegion] = useState(false);
  const [editPvsRegion, setEditPvsRegion]       = useState('');
  const [editPvsDatacenter, setEditPvsDatacenter] = useState('');
  const [pvsRegionSaving, setPvsRegionSaving]   = useState(false);

  // PowerVS exports
  const [pvsSolLoading, setPvsSolLoading]       = useState(false);
  const [pvsCoolLoading, setPvsCoolLoading]     = useState(false);
  const [pvsFullLoading, setPvsFullLoading]     = useState(false);
  const [pvsAsmLoading, setPvsAsmLoading]       = useState(false);
  const [pvsSolDone, setPvsSolDone]             = useState(false);
  const [pvsCoolDone, setPvsCoolDone]           = useState(false);
  const [pvsFullDone, setPvsFullDone]           = useState(false);
  const [pvsAsmDone, setPvsAsmDone]             = useState(false);

  // Price Estimator filler — reset state on every use (no caching)
  const [estimatorFile, setEstimatorFile]       = useState<File | null>(null);
  const [estimatorLoading, setEstimatorLoading] = useState(false);
  const [estimatorError, setEstimatorError]     = useState('');
  const [estimatorDone, setEstimatorDone]       = useState(false);

  const [error, setError] = useState('');

  useEffect(() => {
    api.projects.get(projectId).then(p => {
      setProject(p);
      setEditRegion(p.vpc_region ?? 'us-south');
      setEditZone(p.vpc_datacenter ?? 'us-south-1');
      setEditPvsRegion(p.pvs_region ?? 'us-south');
      setEditPvsDatacenter(p.pvs_datacenter ?? 'dal10');
    }).catch(() => {});
    api.processing.getStatus(projectId).then(setStatus).catch(() => {});
    api.exports.getPowerVSCount(projectId).then(r => setPowervsCount(r.powervs_count)).catch(() => {});
  }, [projectId]);

  async function handleSaveRegion() {
    setRegionSaving(true);
    try {
      const updated = await api.projects.update(projectId, { vpc_region: editRegion, vpc_datacenter: editZone });
      setProject(updated);
      setEditingRegion(false);
    } catch { /* keep editing open on error */ }
    finally { setRegionSaving(false); }
  }

  const recordCount = status?.complete ?? 0;
  const x86Count = recordCount - powervsCount;

  // ── x86 handlers ──────────────────────────────────────────────────────────
  async function handleCloudSolutionExport() {
    setVpcLoading(true); setError('');
    try {
      const exp = await api.exports.generateVPCCalculator(projectId);
      const resp = await api.exports.downloadVPCCalculator(projectId, exp.id);
      await triggerDownload(resp, (exp as any).filename || `VPC_Calculator_${projectId}.xlsx`);
      setVpcDone(true);
    } catch { setError('Failed to generate Cloud Solution export.'); }
    finally { setVpcLoading(false); }
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
  async function handleSavePvsRegion() {
    setPvsRegionSaving(true);
    try {
      const updated = await api.projects.update(projectId, { pvs_region: editPvsRegion, pvs_datacenter: editPvsDatacenter });
      setProject(updated);
      setEditingPvsRegion(false);
    } catch { /* keep editing open on error */ }
    finally { setPvsRegionSaving(false); }
  }

  async function handlePVSSolutionExport() {
    setPvsSolLoading(true); setError('');
    try {
      const exp = await api.exports.generatePowerVSCalculator(projectId);
      const resp = await api.exports.downloadPowerVSCalculator(projectId, exp.id);
      await triggerDownload(resp, (exp as any).filename || `CloudSolution_PowerVS_${projectId}.xlsx`);
      setPvsSolDone(true);
    } catch { setError('Failed to generate PowerVS Cloud Solution export.'); }
    finally { setPvsSolLoading(false); }
  }

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

  async function handlePVSFullExport() {
    setPvsFullLoading(true); setError('');
    try {
      const exp = await api.exports.generateRVToolsPowerVSFull(projectId);
      const resp = await api.exports.downloadRVToolsPowerVSFull(projectId, exp.id);
      await triggerDownload(resp, (exp as any).filename || `RVTools_PowerVS_Full_${projectId}.xlsx`);
      setPvsFullDone(true);
    } catch { setError('Failed to generate PowerVS full RVTools export.'); }
    finally { setPvsFullLoading(false); }
  }

  async function handleFillEstimator() {
    if (!estimatorFile) return;
    setEstimatorLoading(true);
    setEstimatorError('');
    setEstimatorDone(false);
    try {
      const datacenter = (project?.pvs_datacenter ?? 'dal10').toUpperCase();
      const resp = await api.pricingTemplate.fill(projectId, estimatorFile, datacenter);
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error((body as any).detail || `HTTP ${resp.status}`);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const disposition = resp.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename="?([^"]+)"?/);
      a.href = url;
      a.download = match ? match[1] : `PowerVS_PriceEstimator_${projectId}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      setEstimatorDone(true);
      // Reset file input so user is prompted fresh next time
      setEstimatorFile(null);
    } catch (e: any) {
      setEstimatorError(e?.message || 'Failed to fill estimator template.');
    } finally {
      setEstimatorLoading(false);
    }
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

        {/* ── IBM Cloud Target region banner ─────────────────────────────── */}
        {project && (
          <div style={{ background: '#f0f4ff', border: '1px solid #d0e2ff', borderRadius: 4, padding: '0.875rem 1rem', marginBottom: '1.5rem', display: 'flex', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 240 }}>
              <p style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#0043ce', margin: '0 0 0.25rem' }}>IBM Cloud Target</p>
              {!editingRegion ? (
                <p style={{ fontSize: '0.875rem', color: '#161616', margin: 0 }}>
                  Region: <strong>{project.vpc_region ?? 'us-south'}</strong>
                  {' · '}Zone: <strong>{project.vpc_datacenter ?? 'us-south-1'}</strong>
                  {' · '}{IBM_VPC_REGIONS[project.vpc_region ?? 'us-south']?.geography ?? 'North America'}
                </p>
              ) : (
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.75rem', flexWrap: 'wrap', marginTop: '0.25rem' }}>
                  <Select
                    id="export-region-select"
                    labelText="Region"
                    size="sm"
                    value={editRegion}
                    onChange={(e: React.ChangeEvent<HTMLSelectElement>) => {
                      const r = e.target.value;
                      setEditRegion(r);
                      setEditZone(IBM_VPC_REGIONS[r]?.zones[0] ?? `${r}-1`);
                    }}
                    style={{ minWidth: 220 }}
                  >
                    {Object.entries(IBM_VPC_REGIONS).map(([k, v]) => (
                      <SelectItem key={k} value={k} text={v.label} />
                    ))}
                  </Select>
                  <Select
                    id="export-zone-select"
                    labelText="Availability zone"
                    size="sm"
                    value={editZone}
                    onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setEditZone(e.target.value)}
                    style={{ minWidth: 140 }}
                  >
                    {(IBM_VPC_REGIONS[editRegion]?.zones ?? [`${editRegion}-1`]).map(z => (
                      <SelectItem key={z} value={z} text={z} />
                    ))}
                  </Select>
                  <Button size="sm" kind="primary" onClick={handleSaveRegion} disabled={regionSaving}>
                    {regionSaving ? 'Saving…' : 'Save'}
                  </Button>
                  <Button size="sm" kind="ghost" onClick={() => { setEditingRegion(false); setEditRegion(project.vpc_region ?? 'us-south'); setEditZone(project.vpc_datacenter ?? 'us-south-1'); }}>
                    Cancel
                  </Button>
                </div>
              )}
            </div>
            {!editingRegion && (
              <Button size="sm" kind="ghost" renderIcon={Edit} onClick={() => setEditingRegion(true)} style={{ whiteSpace: 'nowrap' }}>
                Change region
              </Button>
            )}
          </div>
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

              {/* Card 0: Cloud Solution Export — PRIMARY, direct IBM Cloud Cost Estimator upload */}
              <div className="export-card" style={{ borderTop: '3px solid #0f62fe' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <DocumentDownload size={20} style={{ color: '#0f62fe', flexShrink: 0 }} />
                  <span className="export-card-title">Cloud Solution Export</span>
                  <InfoTooltip text="3-sheet IBM Cloud VPC Calculator workbook (Project Settings, Exceptions, Data Domains). Upload directly to the IBM Cloud Cost Estimator for VPC pricing. Equivalent to the output of rvtools2vpc.vmware-solutions.cloud.ibm.com. Filename: CloudSolution_<ProjectName>_<date>.xlsx." />
                  <span style={{ fontSize: '0.75rem', color: '#0043ce', display: 'block', width: '100%', marginTop: '0.1rem' }}>
                    (IBM Cloud Cost Estimator — region: <strong>{project?.vpc_region ?? 'us-south'}</strong> / zone: <strong>{project?.vpc_datacenter ?? 'us-south-1'}</strong>)
                  </span>
                </div>
                <p className="export-card-desc">
                  3-sheet workbook for the IBM Cloud Cost Estimator. Profiles your <strong>{x86Count} x86 servers</strong> onto IBM VPC flex instances with data volumes. Includes an Exceptions sheet for unmatched profiles.
                </p>
                {vpcLoading ? (
                  <InlineLoading description="Generating…" />
                ) : (
                  <Button renderIcon={vpcDone ? Checkmark : DocumentDownload} kind={vpcDone ? 'ghost' : 'primary'} onClick={handleCloudSolutionExport} size="md">
                    {vpcDone ? 'Downloaded ✓' : 'Download Cloud Solution export'}
                  </Button>
                )}
              </div>

              {/* Card 1: Full RVTools Export (22-sheet — for VCF Migration Lite / advanced tools) */}
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
                {pureLoading ? (
                  <InlineLoading description="Generating…" />
                ) : (
                  <Button renderIcon={pureDone ? Checkmark : DocumentDownload} kind={pureDone ? 'ghost' : 'secondary'} onClick={handlePureExport} size="md">
                    {pureDone ? 'Downloaded ✓' : 'Download RVTools export'}
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
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
                <Lightning size={20} style={{ color: '#6929c4' }} />
                <h2 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#6929c4', textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>
                  PowerVS Workloads
                  <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0, marginLeft: '0.5rem', color: '#8a3ffc' }}>
                    ({powervsCount} AIX/IBM i server{powervsCount !== 1 ? 's' : ''})
                  </span>
                </h2>
              </div>
              <p style={{ fontSize: '0.8125rem', color: '#525252', marginBottom: '0.75rem' }}>
                These servers run AIX or IBM i and have been automatically designated as IBM Power Virtual Server workloads.
                Upload the exports below to IBM Cool <strong>separately</strong> from the x86 exports to get dedicated PowerVS pricing.
              </p>
              {/* PowerVS region/datacenter selector */}
              {!editingPvsRegion ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8125rem', color: '#525252' }}>
                  <span>PowerVS target:</span>
                  <strong style={{ color: '#6929c4' }}>{project?.pvs_region ?? 'us-south'} / {project?.pvs_datacenter ?? 'dal10'}</strong>
                  <button onClick={() => setEditingPvsRegion(true)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 4px', color: '#6929c4', display: 'inline-flex', alignItems: 'center' }}>
                    <Edit size={14} />
                  </button>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <Select id="pvs-region-sel" labelText="PowerVS Region" value={editPvsRegion} onChange={e => { setEditPvsRegion(e.target.value); setEditPvsDatacenter(IBM_POWERVS_REGIONS[e.target.value]?.datacenters[0] ?? 'dal10'); }} size="sm" style={{ minWidth: 220 }}>
                    {Object.entries(IBM_POWERVS_REGIONS).map(([k, v]) => <SelectItem key={k} value={k} text={v.label} />)}
                  </Select>
                  <Select id="pvs-dc-sel" labelText="Datacenter" value={editPvsDatacenter} onChange={e => setEditPvsDatacenter(e.target.value)} size="sm" style={{ minWidth: 120 }}>
                    {(IBM_POWERVS_REGIONS[editPvsRegion]?.datacenters ?? ['dal10']).map(dc => <SelectItem key={dc} value={dc} text={dc} />)}
                  </Select>
                  <Button size="sm" onClick={handleSavePvsRegion} disabled={pvsRegionSaving}>
                    {pvsRegionSaving ? 'Saving…' : 'Save'}
                  </Button>
                  <Button size="sm" kind="ghost" onClick={() => setEditingPvsRegion(false)}>Cancel</Button>
                </div>
              )}
            </div>

            {/* 2×2 grid: Cloud Solution | Cool Tool | RVTools 22-sheet | AI Assumptions */}
            <div className="export-card-row" style={{ gridTemplateColumns: 'repeat(2, 1fr)', marginBottom: '2.5rem' }}>

              {/* Card 4: PowerVS Cloud Solution Export (NEW — 3-sheet IBM PowerVS Calculator) */}
              <div className="export-card" style={{ borderTop: '3px solid #6929c4' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <DocumentDownload size={20} style={{ color: '#6929c4', flexShrink: 0 }} />
                  <span className="export-card-title">PowerVS Cloud Solution Export</span>
                  <InfoTooltip text="3-sheet IBM PowerVS Calculator workbook (Project Settings, Exceptions, Data Domains). PowerVS equivalent of the x86 Cloud Solution Export. Contains machine type, entitled processors, OS family, storage tier and size for each AIX/IBM i server." />
                  <span style={{ fontSize: '0.75rem', color: '#6929c4', display: 'block', width: '100%', marginTop: '0.1rem' }}>
                    (IBM PowerVS Cost Estimator — datacenter: <strong>{project?.pvs_datacenter ?? 'dal10'}</strong>)
                  </span>
                </div>
                <p className="export-card-desc">
                  3-sheet workbook for IBM PowerVS pricing. Profiles your <strong>{powervsCount} PowerVS records</strong> onto s922/s1022/e980 machine types with storage.
                </p>
                {pvsSolLoading ? (
                  <InlineLoading description="Generating…" />
                ) : (
                  <Button renderIcon={pvsSolDone ? Checkmark : DocumentDownload} kind={pvsSolDone ? 'ghost' : 'primary'} onClick={handlePVSSolutionExport} size="md">
                    {pvsSolDone ? 'Downloaded ✓' : 'Download PowerVS Cloud Solution export'}
                  </Button>
                )}
              </div>

              {/* Card 5: PowerVS Cool Tool Export (IBM Cool — 4-sheet) */}
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

              {/* Card 5: PowerVS RVTools Export (22-sheet — VCF Migration Lite) */}
              <div className="export-card" style={{ borderTop: '3px solid #6929c4' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <DocumentDownload size={20} style={{ color: '#6929c4', flexShrink: 0 }} />
                  <span className="export-card-title">PowerVS RVTools Export</span>
                  <InfoTooltip text="Full 22-sheet RVTools workbook for PowerVS (AIX/IBM i) records. Required by VCF Migration Lite and other tools that validate all 22 RVTools tabs on import." />
                  <span style={{ fontSize: '0.75rem', color: '#6929c4', display: 'block', width: '100%', marginTop: '0.1rem' }}>(Full 22-sheet / VCF Migration Lite format)</span>
                </div>
                <p className="export-card-desc">
                  Full 22-sheet RVTools format for PowerVS records. Contains <strong>{powervsCount} PowerVS records</strong>. Use when your tooling requires all 22 RVTools tabs.
                </p>
                {pvsFullLoading ? (
                  <InlineLoading description="Generating…" />
                ) : (
                  <Button renderIcon={pvsFullDone ? Checkmark : DocumentDownload} kind={pvsFullDone ? 'ghost' : 'secondary'} onClick={handlePVSFullExport} size="md">
                    {pvsFullDone ? 'Downloaded ✓' : 'Download PowerVS RVTools export'}
                  </Button>
                )}
              </div>

              {/* Card 6: PowerVS Assumptions */}
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

            {/* ── PowerVS Price Estimator filler (bottom of PowerVS section) ─── */}
            <div style={{
              borderTop: '1px solid #d0d0d0', paddingTop: '1.5rem', marginTop: '0.5rem',
              background: '#f9f4ff', border: '1px solid #d4bbf7', borderRadius: 6,
              padding: '1.25rem 1.5rem',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <Lightning size={18} style={{ color: '#6929c4', flexShrink: 0 }} />
                <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#6929c4', margin: 0 }}>
                  IBM PowerVS Price Estimator
                </h3>
              </div>
              <p style={{ fontSize: '0.8125rem', color: '#3d3d3d', marginBottom: '1rem', lineHeight: 1.5 }}>
                Upload the latest IBM PowerVS Price Estimator template (.xlsx) to auto-fill it with
                this project's <strong>{powervsCount} LPAR{powervsCount !== 1 ? 's' : ''}</strong>.
                You will be prompted to upload the template each time — no file is cached between uses.
              </p>

              {estimatorError && (
                <div style={{
                  background: '#fff1f1', border: '1px solid #da1e28', borderRadius: 4,
                  padding: '0.5rem 0.75rem', marginBottom: '0.75rem', fontSize: '0.8125rem', color: '#da1e28',
                }}>
                  {estimatorError}
                </div>
              )}

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                <label
                  htmlFor="estimator-file-input"
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                    padding: '0.5rem 1rem', fontSize: '0.875rem', fontWeight: 500,
                    background: '#fff', border: '1px solid #8a3ffc', borderRadius: 4,
                    color: '#6929c4', cursor: 'pointer', whiteSpace: 'nowrap',
                  }}
                >
                  📂 {estimatorFile ? estimatorFile.name : 'Choose Estimator Template…'}
                </label>
                <input
                  id="estimator-file-input"
                  type="file"
                  accept=".xlsx,.XLSX"
                  style={{ display: 'none' }}
                  // Reset key forces a fresh input element so the same file can be re-selected
                  key={estimatorDone ? 'reset' : 'active'}
                  onChange={e => {
                    const f = e.target.files?.[0] ?? null;
                    setEstimatorFile(f);
                    setEstimatorError('');
                    setEstimatorDone(false);
                  }}
                />
                <Button
                  renderIcon={estimatorDone ? Checkmark : DocumentDownload}
                  kind={estimatorDone ? 'ghost' : 'primary'}
                  size="md"
                  disabled={!estimatorFile || estimatorLoading}
                  onClick={handleFillEstimator}
                >
                  {estimatorLoading ? 'Filling…' : estimatorDone ? 'Downloaded ✓' : 'Fill & Download'}
                </Button>
                {estimatorLoading && <InlineLoading description="Filling template…" />}
              </div>
              <p style={{ fontSize: '0.75rem', color: '#6f6f6f', marginTop: '0.75rem', marginBottom: 0 }}>
                The filled file will be named <em>PowerVS_PriceEstimator_{'{ProjectName}'}_{'{timestamp}'}.xlsx</em>
              </p>
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
