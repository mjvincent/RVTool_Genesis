import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, InlineNotification, InlineLoading, Breadcrumb, BreadcrumbItem } from '@carbon/react';
import { Upload, Checkmark, ChevronRight } from '@carbon/icons-react';
import { api, Project } from '../api/client';
import StepProgress from '../components/StepProgress';

export default function UploadPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const projectId = id!;

  const [project, setProject] = useState<Project | null>(null);
  const [uploadedFile, setUploadedFile] = useState<{ name: string; count: number } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [existingCount, setExistingCount] = useState(0);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.projects.get(projectId).then(setProject).catch(() => {});
    api.uploads.getRecords(projectId).then(data => {
      const count = data.records?.length ?? 0;
      if (count > 0) setExistingCount(count);
    }).catch(() => {});
    return () => { setUploadError(''); };
  }, [projectId]);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDrag(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = '';
  }

  async function handleFile(file: File) {
    setUploading(true);
    setUploadError('');
    setUploadedFile(null);
    try {
      const result = await api.uploads.upload(projectId, file);
      if (result.error) throw new Error(result.error);
      const count = result.row_count ?? result.record_count ?? result.records_created ?? 0;
      setUploadedFile({ name: file.name, count });
      setExistingCount(count);
    } catch (err: any) {
      setUploadError(`Upload failed: ${(err as any)?.detail || (err as any)?.message || 'Please try again.'}`);
    } finally {
      setUploading(false);
    }
  }

  const hasRecords = uploadedFile !== null || existingCount > 0;
  const displayCount = uploadedFile?.count ?? existingCount;
  const displayName  = uploadedFile?.name ?? 'Previously uploaded';

  return (
    <>
      <div className="page-header-band">
        <div className="page-header-inner">
          <Breadcrumb style={{ marginBottom: '0.5rem' }}>
            <BreadcrumbItem onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>Projects</BreadcrumbItem>
            {project && <BreadcrumbItem onClick={() => navigate(`/projects/${projectId}/upload`)} style={{ cursor: 'pointer' }}>{project.name}</BreadcrumbItem>}
            <BreadcrumbItem isCurrentPage>Upload</BreadcrumbItem>
          </Breadcrumb>
          <h1 className="page-heading">Upload Spreadsheet</h1>
          <p className="page-description">Upload the customer server inventory. Any .xlsx, .xls, or .csv layout — no template required.</p>
        </div>
      </div>

      <StepProgress projectId={projectId} currentStep={1} completedSteps={[]} />

      <div className="page-body">
        {uploadError && (
          <InlineNotification
            kind="error"
            title="Upload failed"
            subtitle={uploadError}
            lowContrast
            style={{ marginBottom: '1rem' }}
            onCloseButtonClick={() => setUploadError('')}
          />
        )}

        <div className="ibm-card">
          <h2 style={{ fontSize: '1rem', fontWeight: 600, margin: '0 0 1rem', color: '#161616' }}>
            Customer spreadsheet
          </h2>

          {uploading ? (
            <div className="drop-zone" style={{ cursor: 'default' }}>
              <InlineLoading description="Parsing file…" />
            </div>
          ) : hasRecords ? (
            <div className="file-uploaded">
              <Checkmark size={20} style={{ color: '#24a148', flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <strong style={{ display: 'block', fontSize: '0.9375rem', color: '#161616' }}>{displayName}</strong>
                <span style={{ fontSize: '0.875rem', color: '#525252' }}>
                  {displayCount} server record{displayCount !== 1 ? 's' : ''} parsed and ready to normalize
                </span>
              </div>
              <button
                style={{ background: 'none', border: 'none', color: '#0f62fe', fontSize: '0.875rem', cursor: 'pointer', textDecoration: 'underline', whiteSpace: 'nowrap', padding: 0 }}
                onClick={() => { setUploadedFile(null); setExistingCount(0); }}
              >
                Replace file
              </button>
            </div>
          ) : (
            <>
              <input ref={inputRef} type="file" accept=".xlsx,.xls,.csv" onChange={handleChange} style={{ display: 'none' }} />
              <div
                className={`drop-zone${drag ? ' dz-active' : ''}`}
                onClick={() => inputRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setDrag(true); }}
                onDragLeave={() => setDrag(false)}
                onDrop={handleDrop}
              >
                <Upload size={36} style={{ color: '#6f6f6f' }} />
                <h3>Drop your spreadsheet here</h3>
                <p>or <span style={{ color: '#0f62fe', textDecoration: 'underline' }}>click to browse</span></p>
                <p style={{ marginTop: '0.5rem', fontSize: '0.8125rem', color: '#a8a8a8' }}>Accepts .xlsx · .xls · .csv</p>
              </div>
            </>
          )}
        </div>

        <div className="step-actions">
          <Button
            renderIcon={ChevronRight}
            onClick={() => navigate(`/projects/${projectId}/normalize`)}
            disabled={!hasRecords}
          >
            Continue to Normalize
          </Button>
          <Button kind="ghost" onClick={() => navigate('/')}>
            ← Back to Projects
          </Button>
        </div>
      </div>
    </>
  );
}
