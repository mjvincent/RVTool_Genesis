import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, InlineNotification, InlineLoading, Breadcrumb, BreadcrumbItem, Select, SelectItem, Modal, RadioButtonGroup, RadioButton } from '@carbon/react';
import { DocumentDownload, Checkmark, Information, Lightning, Edit } from '@carbon/icons-react';
import { api, Project, ProcessingStatus, ReadinessSummary, AuditLogEntry, IBM_VPC_REGIONS, IBM_POWERVS_REGIONS } from '../api/client';
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
  const [readiness, setReadiness]       = useState<ReadinessSummary | null>(null);
  const [auditLog, setAuditLog]         = useState<AuditLogEntry[]>([]);
  const [auditOpen, setAuditOpen]       = useState(false);

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

  // Billing type modal
  const [billingModalOpen, setBillingModalOpen] = useState(false);
  const [billingType, setBillingType]           = useState('PAYG');

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

  // Pricing template state (upload-then-populate model)
  const [templateStatus, setTemplateStatus] = useState<{ has_template: boolean; filename: string | null; updated_at: string | null } | null>(null);
  const [templateUploading, setTemplateUploading] = useState(false);
  const [populateLoading, setPopulateLoading]     = useState(false);
  const [populateDone, setPopulateDone]           = useState(false);
  const [populateSummary, setPopulateSummary]     = useState<{ written: number; skipped: number; machineCounts: Record<string, number> } | null>(null);

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
    api.processing.getReadinessSummary(projectId).then(setReadiness).catch(() => {});
    api.processing.getAuditLog(projectId).then(setAuditLog).catch(() => {});
    api.exports.getPowerVSCount(projectId).then(r => setPowervsCount(r.powervs_count)).catch(() => {});
    api.pricingTemplate.getStatus(projectId).then(setTemplateStatus).catch(() => {});
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
  async function handleCloudSolutionExport(chosenBillingType: string) {
    setBillingModalOpen(false);
    setVpcLoading(true); setError('');
    try {
      const exp = await api.exports.generateVPCCalculator(projectId, chosenBillingType);
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

  async function handleTemplateUpload(file: File) {
    setTemplateUploading(true); setError('');
    try {
      await api.pricingTemplate.upload(projectId, file);
      const status = await api.pricingTemplate.getStatus(projectId);
      setTemplateStatus(status);
      setPopulateDone(false); // reset so user can download fresh
    } catch (e: any) { setError(e?.message || 'Failed to upload template.'); }
    finally { setTemplateUploading(false); }
  }

  async function handlePopulate() {
    setPopulateLoading(true); setError(''); setPopulateSummary(null);
    try {
      const resp = await api.pricingTemplate.populate(projectId);
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Failed to populate estimator.' }));
        throw new Error(err.detail || 'Failed to populate estimator.');
      }
      // Read summary headers BEFORE consuming body (triggerDownload reads the blob)
      const written = parseInt(resp.headers.get('X-Written-Count') || '0', 10);
      const skipped = parseInt(resp.headers.get('X-Skipped-Count') || '0', 10);
      const machineRaw = resp.headers.get('X-Machine-Counts') || '{}';
      const machineCounts: Record<string, number> = JSON.parse(machineRaw);
      await triggerDownload(resp, `PowerVS_PriceEstimator_${projectId}.xlsx`);
      setPopulateDone(true);
      setPopulateSummary({ written, skipped, machineCounts });
    } catch (e: any) { setError(e?.message || 'Failed to generate populated estimator.'); }
    finally { setPopulateLoading(false); }
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
        {/* ── Migration Readiness Banner ──────────────────────────────────── */}
        {readiness && (
          <div style={{
            background: readiness.export_ready ? '#defbe6' : readiness.error > 0 ? '#fff1f1' : '#fdf6e3',
            border: `1px solid ${readiness.export_ready ? '#24a148' : readiness.error > 0 ? '#da1e28' : '#f1c21b'}`,
            borderRadius: 4,
            padding: '0.875rem 1rem',
            marginBottom: '1.5rem',
          }}>
            {/* Decision line */}
            <p style={{ margin: '0 0 0.75rem', fontSize: '0.9375rem', fontWeight: 600, color: readiness.export_ready ? '#0e6027' : readiness.error > 0 ? '#a2191f' : '#4d3800' }}>
              {readiness.export_ready
                ? '✓ Ready to export'
                : readiness.pending > 0 && readiness.complete_x86 === 0
                  ? '⏳ Processing not yet started'
                  : readiness.error > 0
                    ? `✗ ${readiness.error} record${readiness.error !== 1 ? 's' : ''} need attention before export`
                    : '⚠ No complete x86 records to export yet'}
            </p>
            {/* Stat tiles */}
            <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
              {[
                { label: 'Total servers',    value: readiness.total,             color: '#161616' },
                { label: 'x86 ready',        value: readiness.complete_x86,      color: '#0e6027' },
                { label: 'PowerVS ready',    value: readiness.complete_powervs,  color: '#6929c4' },
                { label: 'Pending',          value: readiness.pending,           color: readiness.pending > 0 ? '#a56d01' : '#525252' },
                { label: 'Errors',           value: readiness.error,             color: readiness.error > 0 ? '#a2191f' : '#525252' },
                { label: 'Excluded',         value: readiness.excluded,          color: '#525252' },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ minWidth: 72, textAlign: 'center' }}>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700, lineHeight: 1, color }}>{value}</div>
                  <div style={{ fontSize: '0.75rem', color: '#525252', marginTop: '0.2rem' }}>{label}</div>
                </div>
              ))}
            </div>
          </div>
        )}

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
                  <Button renderIcon={vpcDone ? Checkmark : DocumentDownload} kind={vpcDone ? 'ghost' : 'primary'} onClick={() => setBillingModalOpen(true)} size="md">
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

            {/* ── IBM Price Estimator section ─────────────────────────────── */}
            <div style={{ borderTop: '1px solid #d8b4fe', paddingTop: '1.25rem', marginTop: '0.5rem', marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <DocumentDownload size={18} style={{ color: '#6929c4' }} />
                <span style={{ fontSize: '0.875rem', fontWeight: 600, color: '#6929c4' }}>IBM Price Estimator (Excel)</span>
                <InfoTooltip text="Upload the IBM Power Virtual Server Price Estimator spreadsheet once per project. The app writes your server data into the yellow input cells only, leaving all pricing formulas intact. Open the downloaded file in Excel to see live pricing." />
              </div>
              <p style={{ fontSize: '0.8125rem', color: '#525252', margin: '0 0 0.75rem 0' }}>
                Upload the IBM Price Estimator .xlsx once, then download a pre-filled copy with your PowerVS servers populated. Open in Excel — pricing recalculates automatically.
              </p>

              {/* Template status */}
              <div style={{ fontSize: '0.8125rem', color: templateStatus?.has_template ? '#198038' : '#6f6f6f', marginBottom: '0.75rem' }}>
                {templateStatus?.has_template
                  ? <>✓ Template on file: <strong>{templateStatus.filename}</strong>{templateStatus.updated_at ? ` — uploaded ${new Date(templateStatus.updated_at).toLocaleDateString()}` : ''}</>
                  : 'No template uploaded yet.'}
              </div>

              {/* Upload + Populate row */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                {/* Upload button — hidden file input + visible trigger */}
                <label style={{ cursor: templateUploading ? 'wait' : 'pointer' }}>
                  <input
                    type="file"
                    accept=".xlsx,.XLSX"
                    style={{ display: 'none' }}
                    disabled={templateUploading}
                    onChange={e => {
                      const f = e.target.files?.[0];
                      if (f) handleTemplateUpload(f);
                      e.target.value = '';   // allow re-upload same file
                    }}
                  />
                  <span
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                      padding: '0.4rem 1rem', border: '1px solid #6929c4', borderRadius: 2,
                      fontSize: '0.875rem', color: '#6929c4',
                      background: templateUploading ? '#f4f4f4' : '#fff',
                      cursor: 'inherit',
                    }}
                  >
                    {templateUploading ? 'Uploading…' : templateStatus?.has_template ? 'Replace template' : 'Upload IBM Price Estimator'}
                  </span>
                </label>

                {/* Populate & Download button */}
                {populateLoading ? (
                  <InlineLoading description="Populating…" />
                ) : (
                  <Button
                    renderIcon={populateDone ? Checkmark : DocumentDownload}
                    kind={populateDone ? 'ghost' : 'primary'}
                    disabled={!templateStatus?.has_template || powervsCount === 0}
                    onClick={handlePopulate}
                    size="md"
                  >
                    {populateDone ? 'Downloaded ✓' : 'Populate & Download'}
                  </Button>
                )}
              </div>

              {/* Export summary card */}
              {populateSummary && (
                <div style={{ marginTop: '1rem', border: '1px solid #e5e7eb', borderRadius: 4, overflow: 'hidden', fontSize: '0.8125rem' }}>
                  <div style={{ background: '#f0fdf4', borderBottom: '1px solid #e5e7eb', padding: '0.5rem 0.75rem', fontWeight: 600, color: '#198038' }}>
                    ✓ {populateSummary.written} LPAR{populateSummary.written !== 1 ? 's' : ''} written to the Price Estimator
                  </div>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: '#f7f8fa' }}>
                        <th style={{ textAlign: 'left', padding: '0.4rem 0.75rem', fontWeight: 600, color: '#525252', borderBottom: '1px solid #e5e7eb' }}>System</th>
                        <th style={{ textAlign: 'right', padding: '0.4rem 0.75rem', fontWeight: 600, color: '#525252', borderBottom: '1px solid #e5e7eb' }}>LPARs</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(populateSummary.machineCounts).sort().map(([machine, count]) => (
                        <tr key={machine} style={{ borderBottom: '1px solid #f0f0f0' }}>
                          <td style={{ padding: '0.4rem 0.75rem', color: '#1f2328' }}>{machine}</td>
                          <td style={{ padding: '0.4rem 0.75rem', textAlign: 'right', color: '#1f2328' }}>{count}</td>
                        </tr>
                      ))}
                      {populateSummary.skipped > 0 && (
                        <tr style={{ background: '#fff8f1' }}>
                          <td style={{ padding: '0.4rem 0.75rem', color: '#da1e28' }}>⚠ Skipped (over 300-row limit)</td>
                          <td style={{ padding: '0.4rem 0.75rem', textAlign: 'right', color: '#da1e28' }}>{populateSummary.skipped}</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}

        {/* ── Activity / Audit Log panel ──────────────────────────────────── */}
        {auditLog.length > 0 && (
          <div style={{ marginBottom: '1.5rem', border: '1px solid #e0e0e0', borderRadius: 4 }}>
            <button
              onClick={() => setAuditOpen(o => !o)}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '0.75rem 1rem', background: '#f4f4f4', border: 'none', cursor: 'pointer',
                fontSize: '0.875rem', fontWeight: 600, color: '#161616',
              }}
            >
              <span>Activity ({auditLog.length})</span>
              <span style={{ fontSize: '0.75rem', color: '#525252' }}>{auditOpen ? '▲ Hide' : '▼ Show'}</span>
            </button>
            {auditOpen && (
              <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                {auditLog.map((entry, i) => {
                  const opLabel: Record<string, string> = {
                    bulk_os_replace:     'OS Replace',
                    bulk_nxf_replace:    'NXF Fix',
                    bulk_exclude:        'Bulk Exclude',
                    export_vpc_calculator: 'Export',
                  };
                  const label = opLabel[entry.operation] ?? entry.operation;
                  const when = new Date(entry.created_at);
                  const timeStr = when.toLocaleString();
                  return (
                    <li key={entry.id} style={{
                      display: 'flex', gap: '0.75rem', alignItems: 'flex-start',
                      padding: '0.6rem 1rem',
                      borderTop: i === 0 ? 'none' : '1px solid #e0e0e0',
                      background: '#fff',
                    }}>
                      <span style={{
                        fontSize: '0.6875rem', fontWeight: 600, padding: '0.1rem 0.4rem',
                        borderRadius: 2, background: '#e0e0e0', color: '#161616',
                        whiteSpace: 'nowrap', marginTop: '0.1rem',
                      }}>
                        {label}
                      </span>
                      <span style={{ flex: 1, fontSize: '0.8125rem', color: '#1f2328' }}>
                        {entry.summary}
                        {entry.record_count != null && (
                          <span style={{ color: '#525252' }}> — {entry.record_count} record{entry.record_count !== 1 ? 's' : ''}</span>
                        )}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: '#6f6f6f', whiteSpace: 'nowrap' }}>{timeStr}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
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

      {/* ── Billing type modal ──────────────────────────────────────────── */}
      <Modal
        open={billingModalOpen}
        modalHeading="Cloud Solution Export — Billing Type"
        primaryButtonText="Download"
        secondaryButtonText="Cancel"
        onRequestSubmit={() => handleCloudSolutionExport(billingType)}
        onRequestClose={() => setBillingModalOpen(false)}
        onSecondarySubmit={() => setBillingModalOpen(false)}
        size="xs"
      >
        <p style={{ fontSize: '0.875rem', color: '#525252', marginBottom: '1rem' }}>
          Select the billing type to use in the IBM Cloud Cost Estimator workbook.
          This applies to every Compute row in the Project Settings sheet.
        </p>
        <RadioButtonGroup
          legendText="Billing type"
          name="billing-type-group"
          valueSelected={billingType}
          onChange={(val) => setBillingType(val as string)}
          orientation="vertical"
        >
          <RadioButton labelText="PAYG" value="PAYG" id="billing-payg" />
          <RadioButton labelText="1 Yr Reserved" value="1 Yr Reserved" id="billing-1yr" />
          <RadioButton labelText="3 Yr Reserved" value="3 Yr Reserved" id="billing-2yr" />
        </RadioButtonGroup>
      </Modal>
    </>
  );
}
