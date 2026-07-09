import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, InlineNotification, Breadcrumb, BreadcrumbItem } from '@carbon/react';
import { ChevronRight } from '@carbon/icons-react';
import { api, Project, ProcessingStatus, Assumption } from '../api/client';
import StepProgress from '../components/StepProgress';
import RecordsTable from '../components/RecordsTable';
import AssumptionsPanel from '../components/AssumptionsPanel';

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const projectId = id!;

  const [project, setProject] = useState<Project | null>(null);
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [selectedAssumptions, setSelectedAssumptions] = useState<Assumption[] | null>(null);
  const [selectedVmName, setSelectedVmName] = useState('');
  const [tableKey, setTableKey] = useState(0);

  useEffect(() => {
    api.projects.get(projectId).then(setProject).catch(() => {});
    api.processing.getStatus(projectId).then(s => {
      setStatus(s);
      setTableKey(k => k + 1);
    }).catch(() => {});
  }, [projectId]);

  const isComplete = !!(status?.is_complete && status.total > 0);

  return (
    <>
      <div className="page-header-band">
        <div className="page-header-inner">
          <Breadcrumb style={{ marginBottom: '0.5rem' }}>
            <BreadcrumbItem onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>Projects</BreadcrumbItem>
            {project && <BreadcrumbItem onClick={() => navigate(`/projects/${projectId}/upload`)} style={{ cursor: 'pointer' }}>{project.name}</BreadcrumbItem>}
            <BreadcrumbItem isCurrentPage>Review</BreadcrumbItem>
          </Breadcrumb>
          <h1 className="page-heading">Review Normalized Records</h1>
          <p className="page-description">
            Inspect each record. Click a row to expand details. Click the AI decisions badge to review assumptions.
          </p>
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

        <RecordsTable
          key={tableKey}
          projectId={projectId}
          onViewAssumptions={(vmName, assumptions) => {
            setSelectedVmName(vmName);
            setSelectedAssumptions(assumptions);
          }}
        />

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
    </>
  );
}
