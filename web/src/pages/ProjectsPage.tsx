import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Modal, InlineNotification, OverflowMenu, OverflowMenuItem } from '@carbon/react';
import { Add, Document } from '@carbon/icons-react';
import { api, Project } from '../api/client';

export default function ProjectsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try {
      const data = await api.projects.list();
      setProjects(data.projects);
    } catch {
      setError('Could not load projects. Make sure the API is running.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    try {
      await api.projects.delete(deleteTarget.id);
      setProjects(prev => prev.filter(p => p.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch {
      setError('Failed to delete project.');
    } finally {
      setDeleteLoading(false);
    }
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  }

  return (
    <>
      <div className="page-header-band">
        <div className="page-header-inner" style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
          <div>
            <h1 className="page-heading">Projects</h1>
            <p className="page-description">
              Each project converts one customer spreadsheet into an IBM Cool-ready RVTools file.
            </p>
          </div>
          <Button renderIcon={Add} onClick={() => navigate('/projects/new')}>
            New Project
          </Button>
        </div>
      </div>

      <div className="page-body">
        {error && (
          <InlineNotification
            kind="error"
            title={error}
            lowContrast
            style={{ marginBottom: '1.5rem' }}
            onCloseButtonClick={() => setError('')}
          />
        )}

        {loading ? (
          <div className="project-list">
            {[1, 2, 3].map(i => (
              <div key={i} className="project-item" style={{ minHeight: 72, cursor: 'default', background: '#f4f4f4' }} />
            ))}
          </div>
        ) : projects.length === 0 ? (
          <div className="empty-state">
            <Document size={48} style={{ color: '#a8a8a8' }} />
            <h2>No projects yet</h2>
            <p>
              Create a project, upload a customer server inventory spreadsheet,
              and get an IBM Cool-ready RVTools export in minutes.
            </p>
            <Button renderIcon={Add} onClick={() => navigate('/projects/new')}>
              Create your first project
            </Button>
          </div>
        ) : (
          <div className="project-list">
            {projects.map(project => (
              <div
                key={project.id}
                className="project-item"
                onClick={() => navigate(`/projects/${project.id}/upload`)}
                role="button"
                tabIndex={0}
                onKeyDown={e => e.key === 'Enter' && navigate(`/projects/${project.id}/upload`)}
              >
                <div>
                  <p className="project-item-name">{project.name}</p>
                  <p className="project-item-meta">Created {formatDate(project.created_at)}</p>
                </div>
                <div
                  onClick={e => e.stopPropagation()}
                  onKeyDown={e => e.stopPropagation()}
                >
                  {/* Capture project in a const so the closure is unambiguous */}
                  {(() => {
                    const p = project;
                    return (
                      <OverflowMenu aria-label="Project actions" size="sm" flipped>
                        <OverflowMenuItem
                          itemText="Delete project"
                          isDelete
                          hasDivider
                          onClick={() => setDeleteTarget(p)}
                        />
                      </OverflowMenu>
                    );
                  })()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Modal
        open={!!deleteTarget}
        danger
        modalHeading={`Delete "${deleteTarget?.name}"?`}
        primaryButtonText={deleteLoading ? 'Deleting…' : 'Delete'}
        secondaryButtonText="Cancel"
        onRequestSubmit={handleDelete}
        onRequestClose={() => setDeleteTarget(null)}
        primaryButtonDisabled={deleteLoading}
      >
        <p style={{ color: '#525252', lineHeight: 1.6 }}>
          This will permanently remove the project and all its records, assumptions, and exports.
          This cannot be undone.
        </p>
      </Modal>
    </>
  );
}
