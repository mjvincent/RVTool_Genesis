import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, InlineNotification, InlineLoading, Breadcrumb, BreadcrumbItem } from '@carbon/react';
import { ChevronRight, Restart } from '@carbon/icons-react';
import { api, Project, ProcessingStatus, Assumption, ServerRecord } from '../api/client';
import StepProgress from '../components/StepProgress';
import RecordsTable from '../components/RecordsTable';
import AssumptionsPanel from '../components/AssumptionsPanel';
import FailedRecordsPanel from '../components/FailedRecordsPanel';
import BulkOSModal from '../components/BulkOSModal';
import BulkNxfModal from '../components/BulkNxfModal';
import BulkExcludeModal from '../components/BulkExcludeModal';

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const projectId = id!;

  const [project, setProject]       = useState<Project | null>(null);
  const [status, setStatus]         = useState<ProcessingStatus | null>(null);
  const [records, setRecords]       = useState<ServerRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(true);
  const [tableKey, setTableKey]     = useState(0);

  const [selectedAssumptions, setSelectedAssumptions] = useState<Assumption[] | null>(null);
  const [selectedVmName, setSelectedVmName]           = useState('');

  const [bulkOsOpen, setBulkOsOpen] = useState(false);
  const [bulkOsSuccess, setBulkOsSuccess] = useState('');

  const [nxfUnsupportedCount, setNxfUnsupportedCount] = useState(0);
  const [bulkNxfOpen, setBulkNxfOpen]   = useState(false);
  const [bulkNxfSuccess, setBulkNxfSuccess] = useState('');

  const [bulkExcludeOpen, setBulkExcludeOpen]     = useState(false);
  const [bulkExcludeSuccess, setBulkExcludeSuccess] = useState('');

  // ---------------------------------------------------------------------------
  // Load
  // ---------------------------------------------------------------------------
  const loadRecords = useCallback(async () => {
    setRecordsLoading(true);
    try {
      const data = await api.uploads.getRecords(projectId);
      setRecords(data.records ?? []);
    } finally {
      setRecordsLoading(false);
    }
  }, [projectId]);

  const checkNxfCount = useCallback(async () => {
    try {
      const data = await api.uploads.getNxfUnsupportedCount(projectId);
      setNxfUnsupportedCount(data.unsupported_count ?? 0);
    } catch {
      // non-critical — silently ignore
    }
  }, [projectId]);

  useEffect(() => {
    api.projects.get(projectId).then(setProject).catch(() => {});
    api.processing.getStatus(projectId).then(s => {
      setStatus(s);
      setTableKey(k => k + 1);
    }).catch(() => {});
    loadRecords();
    checkNxfCount();
  }, [projectId, loadRecords, checkNxfCount]);

  const isComplete = !!(status?.is_complete && status.total > 0);

  // ---------------------------------------------------------------------------
  // Derived record lists
  // ---------------------------------------------------------------------------
  const failedRecords  = records.filter(
    r => r.processing_status === 'error' || (r as any).status === 'error'
  );
  const normalRecords  = records.filter(
    r => r.processing_status === 'complete' && !r.is_excluded
  );

  // ---------------------------------------------------------------------------
  // Failed panel callbacks — real-time updates
  // ---------------------------------------------------------------------------
  function handleRecordFixed(recordId: string, updated: ServerRecord) {
    setRecords(prev => prev.map(r => r.id === recordId ? updated : r));
    // Refresh status counts
    api.processing.getStatus(projectId).then(setStatus).catch(() => {});
  }

  function handleRecordStillFailed(recordId: string, errorMsg: string) {
    setRecords(prev => prev.map(r =>
      r.id === recordId ? { ...r, error_message: errorMsg } : r
    ));
  }

  // ---------------------------------------------------------------------------
  // Bulk OS callbacks
  // ---------------------------------------------------------------------------
  function handleBulkOsApplied(count: number, fromOs: string, toOs: string) {
    setBulkOsOpen(false);
    setBulkOsSuccess(`Replaced OS on ${count} record${count !== 1 ? 's' : ''}: "${fromOs}" → "${toOs}"`);
    loadRecords();
    setTableKey(k => k + 1);
  }

  function handleBulkNxfApplied(count: number, targetProfile: string) {
    setBulkNxfOpen(false);
    setBulkNxfSuccess(`Upgraded ${count} server${count !== 1 ? 's' : ''} to ${targetProfile}`);
    loadRecords();
    checkNxfCount();
    setTableKey(k => k + 1);
  }

  function handleBulkExcludeApplied(count: number, filterType: string, filterValue: string) {
    setBulkExcludeOpen(false);
    setBulkExcludeSuccess(`Excluded ${count} record${count !== 1 ? 's' : ''} where ${filterType} matches "${filterValue}"`);
    loadRecords();
    setTableKey(k => k + 1);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <>
      <div className="page-header-band">
        <div
          className="page-header-inner"
          style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}
        >
          <div>
            <Breadcrumb style={{ marginBottom: '0.5rem' }}>
              <BreadcrumbItem onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>Projects</BreadcrumbItem>
              {project && (
                <BreadcrumbItem onClick={() => navigate(`/projects/${projectId}/upload`)} style={{ cursor: 'pointer' }}>
                  {project.name}
                </BreadcrumbItem>
              )}
              <BreadcrumbItem isCurrentPage>Review</BreadcrumbItem>
            </Breadcrumb>
            <h1 className="page-heading">Review Normalized Records</h1>
            <p className="page-description">
              Inspect each record. Click a row to expand details. Click the AI decisions badge to review assumptions.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            {normalRecords.length > 0 && (
              <Button
                kind="secondary"
                renderIcon={Restart}
                size="md"
                onClick={() => { setBulkOsSuccess(''); setBulkOsOpen(true); }}
              >
                Bulk OS Replace
              </Button>
            )}
            {isComplete && nxfUnsupportedCount > 0 && (
              <Button
                kind="danger--ghost"
                size="md"
                onClick={() => { setBulkNxfSuccess(''); setBulkNxfOpen(true); }}
              >
                ⚠ Fix Nano Profiles ({nxfUnsupportedCount})
              </Button>
            )}
            {normalRecords.length > 0 && (
              <Button
                kind="ghost"
                size="md"
                onClick={() => { setBulkExcludeSuccess(''); setBulkExcludeOpen(true); }}
              >
                Bulk Exclude
              </Button>
            )}
          </div>
        </div>
      </div>

      <StepProgress projectId={projectId} currentStep={3} completedSteps={isComplete ? [1, 2] : [1]} />

      <div className="page-body">
        {!isComplete && (
          <InlineNotification
            kind="warning"
            title="Normalization not complete"
            subtitle="Go back to the Normalize step and run AI normalization first."
            lowContrast
            style={{ marginBottom: '1.5rem' }}
          />
        )}

        {bulkOsSuccess && (
          <InlineNotification
            kind="success"
            title="OS replacement complete"
            subtitle={bulkOsSuccess}
            lowContrast
            style={{ marginBottom: '1.5rem' }}
            onCloseButtonClick={() => setBulkOsSuccess('')}
          />
        )}

        {bulkNxfSuccess && (
          <InlineNotification
            kind="success"
            title="Flex-Nano profiles upgraded"
            subtitle={bulkNxfSuccess}
            lowContrast
            style={{ marginBottom: '1.5rem' }}
            onCloseButtonClick={() => setBulkNxfSuccess('')}
          />
        )}

        {bulkExcludeSuccess && (
          <InlineNotification
            kind="success"
            title="Bulk exclusion complete"
            subtitle={bulkExcludeSuccess}
            lowContrast
            style={{ marginBottom: '1.5rem' }}
            onCloseButtonClick={() => setBulkExcludeSuccess('')}
          />
        )}

        {isComplete && nxfUnsupportedCount > 0 && (
          <InlineNotification
            kind="warning"
            title="Unsupported Flex-Nano profiles detected"
            subtitle={`${nxfUnsupportedCount} server${nxfUnsupportedCount !== 1 ? 's are' : ' is'} assigned nxf-1x1, nxf-1x2, or nxf-1x4 — profiles the IBM Cloud Solutioning tool does not recognise. Use "Fix Nano Profiles" to upgrade them before exporting.`}
            lowContrast
            style={{ marginBottom: '1.5rem' }}
          />
        )}

        {/* ── Failed Records Panel — pinned above the table ─────────────── */}
        {failedRecords.length > 0 && (
          <FailedRecordsPanel
            projectId={projectId}
            records={failedRecords}
            onRecordFixed={handleRecordFixed}
            onRecordStillFailed={handleRecordStillFailed}
          />
        )}

        {recordsLoading ? (
          <InlineLoading description="Loading records…" style={{ marginBottom: '1rem' }} />
        ) : (
          <RecordsTable
            key={tableKey}
            projectId={projectId}
            onViewAssumptions={(vmName, assumptions) => {
              setSelectedVmName(vmName);
              setSelectedAssumptions(assumptions);
            }}
          />
        )}

        <div className="step-actions">
          <Button
            renderIcon={ChevronRight}
            onClick={() => navigate(`/projects/${projectId}/export`)}
            disabled={!isComplete}
          >
            Continue to Export
          </Button>
          <Button kind="ghost" onClick={() => navigate(`/projects/${projectId}/normalize`)}>
            ← Back to Normalize
          </Button>
        </div>
      </div>

      {selectedAssumptions && (
        <AssumptionsPanel
          open
          onClose={() => setSelectedAssumptions(null)}
          vmName={selectedVmName}
          assumptions={selectedAssumptions}
        />
      )}

      {bulkOsOpen && (
        <BulkOSModal
          projectId={projectId}
          records={normalRecords}
          onClose={() => setBulkOsOpen(false)}
          onApplied={handleBulkOsApplied}
        />
      )}

      {bulkNxfOpen && (
        <BulkNxfModal
          projectId={projectId}
          unsupportedCount={nxfUnsupportedCount}
          onClose={() => setBulkNxfOpen(false)}
          onApplied={handleBulkNxfApplied}
        />
      )}

      {bulkExcludeOpen && (
        <BulkExcludeModal
          projectId={projectId}
          records={normalRecords}
          onClose={() => setBulkExcludeOpen(false)}
          onApplied={handleBulkExcludeApplied}
        />
      )}
    </>
  );
}
