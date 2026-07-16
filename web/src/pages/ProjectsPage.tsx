import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Modal,
  InlineNotification,
  InlineLoading,
  OverflowMenu,
  OverflowMenuItem,
  Breadcrumb,
  BreadcrumbItem,
  TextInput,
} from '@carbon/react';
import {
  Add, Document, Upload, Download,
  FolderAdd, FolderOpen,
} from '@carbon/icons-react';
import { api, Project, Folder as FolderType } from '../api/client';
import BackupModal from '../components/BackupModal';
import FolderCreateModal from '../components/FolderCreateModal';
import MoveProjectModal from '../components/MoveProjectModal';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type BreadcrumbEntry = { id: string; name: string };

export default function ProjectsPage() {
  const navigate          = useNavigate();
  // Current folder context — null = root
  const [currentFolder, setCurrentFolder]   = useState<FolderType | null>(null);
  const [breadcrumbs, setBreadcrumbs]        = useState<BreadcrumbEntry[]>([]);

  const [folders, setFolders]               = useState<FolderType[]>([]);
  const [projects, setProjects]             = useState<Project[]>([]);
  const [loading, setLoading]               = useState(true);
  const [error, setError]                   = useState('');

  // Delete project
  const [deleteTarget, setDeleteTarget]     = useState<Project | null>(null);
  const [deleteLoading, setDeleteLoading]   = useState(false);

  // Delete folder
  const [deleteFolderTarget, setDeleteFolderTarget] = useState<FolderType | null>(null);
  const [deleteFolderLoading, setDeleteFolderLoading] = useState(false);

  // Rename folder
  const [renameFolderTarget, setRenameFolderTarget] = useState<FolderType | null>(null);
  const [renameFolderValue, setRenameFolderValue]   = useState('');
  const [renameFolderLoading, setRenameFolderLoading] = useState(false);

  // Create folder modal
  const [createFolderParent, setCreateFolderParent] = useState<FolderType | null | undefined>(undefined);
  // undefined = modal closed; null = creating root-level; FolderType = creating child

  // Move project modal
  const [moveTarget, setMoveTarget]         = useState<Project | null>(null);

  // Backup
  const [backupTarget, setBackupTarget]     = useState<Project | null>(null);
  const [backupAllOpen, setBackupAllOpen]   = useState(false);

  // Restore
  const restoreInputRef = useRef<HTMLInputElement>(null);
  const [restoring, setRestoring]           = useState(false);
  const [restoreError, setRestoreError]     = useState('');
  const [restoreSuccess, setRestoreSuccess] = useState('');

  // ── Load data ──────────────────────────────────────────────────────────────
  async function load(folder: FolderType | null) {
    setLoading(true);
    try {
      const [folderRes, projectRes] = await Promise.all([
        api.folders.list(folder?.id ?? null),
        api.projects.list(folder?.id ?? null),
      ]);
      setFolders(folderRes.folders);
      setProjects(projectRes.projects);
    } catch {
      setError('Could not load data. Make sure the API is running.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(currentFolder); }, [currentFolder]);

  // ── Folder navigation ──────────────────────────────────────────────────────
  function navigateInto(folder: FolderType) {
    setCurrentFolder(folder);
    setBreadcrumbs(prev => [...prev, { id: folder.id, name: folder.name }]);
  }

  function navigateToRoot() {
    setCurrentFolder(null);
    setBreadcrumbs([]);
  }

  function navigateToBreadcrumb(_entry: BreadcrumbEntry, idx: number) {
    // We only support 2 levels, so idx 0 is always root, idx 1 is a folder
    if (idx === 0) { navigateToRoot(); return; }
    // Reload the folder at that breadcrumb index — keep breadcrumbs up to idx
    setBreadcrumbs(prev => prev.slice(0, idx));
    // currentFolder is already that folder (only 2 levels, idx 1 = current)
  }

  // ── Folder actions ────────────────────────────────────────────────────────
  function handleFolderCreated(folder: FolderType) {
    setCreateFolderParent(undefined);
    // If created at current level, add to list
    const createdAtCurrentLevel =
      (folder.parent_id ?? null) === (currentFolder?.id ?? null);
    if (createdAtCurrentLevel) {
      setFolders(prev => [...prev, folder].sort((a, b) => a.name.localeCompare(b.name)));
    }
  }

  async function handleRenameFolder() {
    if (!renameFolderTarget || !renameFolderValue.trim()) return;
    setRenameFolderLoading(true);
    try {
      const updated = await api.folders.rename(renameFolderTarget.id, renameFolderValue.trim());
      setFolders(prev => prev.map(f => f.id === updated.id ? updated : f));
      if (currentFolder?.id === updated.id) setCurrentFolder(updated);
      setBreadcrumbs(prev => prev.map(b => b.id === updated.id ? { ...b, name: updated.name } : b));
      setRenameFolderTarget(null);
    } catch {
      setError('Failed to rename folder.');
    } finally {
      setRenameFolderLoading(false);
    }
  }

  async function handleDeleteFolder() {
    if (!deleteFolderTarget) return;
    setDeleteFolderLoading(true);
    try {
      await api.folders.delete(deleteFolderTarget.id);
      setFolders(prev => prev.filter(f => f.id !== deleteFolderTarget.id));
      setDeleteFolderTarget(null);
      // If deleting the folder we're currently inside, go back to root
      if (currentFolder?.id === deleteFolderTarget.id) navigateToRoot();
    } catch {
      setError('Failed to delete folder.');
    } finally {
      setDeleteFolderLoading(false);
    }
  }

  // ── Project actions ────────────────────────────────────────────────────────
  async function handleDeleteProject() {
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

  function handleProjectMoved(updated: Project) {
    setMoveTarget(null);
    // Remove from current view if it moved away
    if ((updated.folder_id ?? null) !== (currentFolder?.id ?? null)) {
      setProjects(prev => prev.filter(p => p.id !== updated.id));
    }
  }

  // ── Restore ────────────────────────────────────────────────────────────────
  async function handleRestoreFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    setRestoring(true); setRestoreError(''); setRestoreSuccess('');
    try {
      const result = await api.backup.restore(file);
      const names = result.restored.map(r => r.name).join(', ');
      setRestoreSuccess(
        `${result.count} project${result.count !== 1 ? 's' : ''} restored: ${names}`
      );
      await load(currentFolder);
    } catch (err: any) {
      setRestoreError(`Restore failed: ${(err as any)?.detail || (err as any)?.message || 'Please try again.'}`);
    } finally {
      setRestoring(false);
    }
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  }

  const isEmpty = !loading && folders.length === 0 && projects.length === 0;
  const isAtRoot = currentFolder === null;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <>
      <div className="page-header-band">
        <div
          className="page-header-inner"
          style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}
        >
          <div>
            <h1 className="page-heading">Projects</h1>
            <p className="page-description">
              Organise projects into customer folders and engagement sub-folders.
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <Button
              kind="ghost"
              renderIcon={Upload}
              size="md"
              onClick={() => restoreInputRef.current?.click()}
              disabled={restoring}
            >
              {restoring ? 'Restoring…' : 'Restore from backup'}
            </Button>
            <Button
              kind="tertiary"
              renderIcon={Download}
              size="md"
              onClick={() => setBackupAllOpen(true)}
              disabled={projects.length === 0}
            >
              Backup all
            </Button>
            <Button
              kind="secondary"
              renderIcon={FolderAdd}
              size="md"
              onClick={() => setCreateFolderParent(currentFolder)}
            >
              {isAtRoot ? 'New customer folder' : 'New engagement folder'}
            </Button>
            <Button
              renderIcon={Add}
              onClick={() => navigate(
                currentFolder
                  ? `/projects/new?folder_id=${currentFolder.id}`
                  : '/projects/new'
              )}
            >
              New Project
            </Button>
          </div>
        </div>
      </div>

      {/* Hidden file input for restore */}
      <input
        ref={restoreInputRef}
        type="file"
        accept=".json,.zip"
        style={{ display: 'none' }}
        onChange={handleRestoreFile}
      />

      <div className="page-body">
        {/* Notifications */}
        {error && (
          <InlineNotification kind="error" title={error} lowContrast
            style={{ marginBottom: '1.5rem' }} onCloseButtonClick={() => setError('')} />
        )}
        {restoreError && (
          <InlineNotification kind="error" title="Restore failed" subtitle={restoreError} lowContrast
            style={{ marginBottom: '1.5rem' }} onCloseButtonClick={() => setRestoreError('')} />
        )}
        {restoreSuccess && (
          <InlineNotification kind="success" title="Restore complete" subtitle={restoreSuccess} lowContrast
            style={{ marginBottom: '1.5rem' }} onCloseButtonClick={() => setRestoreSuccess('')} />
        )}
        {restoring && (
          <InlineLoading description="Restoring projects…" style={{ marginBottom: '1.5rem' }} />
        )}

        {/* Breadcrumb trail */}
        {(breadcrumbs.length > 0 || currentFolder) && (
          <Breadcrumb style={{ marginBottom: '1rem' }}>
            <BreadcrumbItem onClick={navigateToRoot} style={{ cursor: 'pointer' }}>
              All folders
            </BreadcrumbItem>
            {breadcrumbs.map((b, idx) => (
              <BreadcrumbItem
                key={b.id}
                isCurrentPage={idx === breadcrumbs.length - 1}
                onClick={() => navigateToBreadcrumb(b, idx + 1)}
                style={{ cursor: idx < breadcrumbs.length - 1 ? 'pointer' : 'default' }}
              >
                {b.name}
              </BreadcrumbItem>
            ))}
          </Breadcrumb>
        )}

        {loading ? (
          <div className="project-list">
            {[1, 2, 3].map(i => (
              <div key={i} className="project-item" style={{ minHeight: 72, cursor: 'default', background: '#f4f4f4' }} />
            ))}
          </div>
        ) : isEmpty ? (
          <div className="empty-state">
            <Document size={48} style={{ color: '#a8a8a8' }} />
            <h2>{isAtRoot ? 'No projects yet' : `"${currentFolder?.name}" is empty`}</h2>
            <p>
              {isAtRoot
                ? 'Create a customer folder to organise projects by account, or create a project directly.'
                : 'Add a project to this folder or create an engagement sub-folder.'}
            </p>
            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', justifyContent: 'center' }}>
              <Button
                kind="secondary"
                renderIcon={FolderAdd}
                onClick={() => setCreateFolderParent(currentFolder)}
              >
                {isAtRoot ? 'New customer folder' : 'New engagement folder'}
              </Button>
              <Button
                renderIcon={Add}
                onClick={() => navigate(
                  currentFolder
                    ? `/projects/new?folder_id=${currentFolder.id}`
                    : '/projects/new'
                )}
              >
                Create project
              </Button>
            </div>
          </div>
        ) : (
          <div className="project-list">

            {/* ── Folder rows ─────────────────────────────────────────── */}
            {folders.map(folder => (
              <div
                key={folder.id}
                className="project-item"
                style={{ background: '#f0f4ff', borderLeft: '3px solid #0043ce' }}
                onClick={() => navigateInto(folder)}
                role="button"
                tabIndex={0}
                onKeyDown={e => e.key === 'Enter' && navigateInto(folder)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
                  <FolderOpen size={20} style={{ color: '#0043ce', flexShrink: 0 }} />
                  <div style={{ minWidth: 0 }}>
                    <p className="project-item-name" style={{ color: '#0043ce' }}>{folder.name}</p>
                    <p className="project-item-meta">
                      {folder.project_count} project{folder.project_count !== 1 ? 's' : ''}
                      {folder.child_count > 0 && ` · ${folder.child_count} sub-folder${folder.child_count !== 1 ? 's' : ''}`}
                    </p>
                  </div>
                </div>
                <div onClick={e => e.stopPropagation()} onKeyDown={e => e.stopPropagation()}>
                  {(() => {
                    const f = folder;
                    return (
                      <OverflowMenu aria-label="Folder actions" size="sm" flipped>
                        <OverflowMenuItem
                          itemText="Rename folder"
                          onClick={() => { setRenameFolderTarget(f); setRenameFolderValue(f.name); }}
                        />
                        {isAtRoot && (
                          <OverflowMenuItem
                            itemText="New engagement sub-folder"
                            onClick={() => setCreateFolderParent(f)}
                          />
                        )}
                        <OverflowMenuItem
                          itemText="Delete folder"
                          isDelete
                          hasDivider
                          onClick={() => setDeleteFolderTarget(f)}
                        />
                      </OverflowMenu>
                    );
                  })()}
                </div>
              </div>
            ))}

            {/* Divider between folders and projects */}
            {folders.length > 0 && projects.length > 0 && (
              <div style={{ borderTop: '1px solid #e0e0e0', margin: '0.25rem 0' }} />
            )}

            {/* ── Project rows ─────────────────────────────────────────── */}
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
                <div onClick={e => e.stopPropagation()} onKeyDown={e => e.stopPropagation()}>
                  {(() => {
                    const p = project;
                    return (
                      <OverflowMenu aria-label="Project actions" size="sm" flipped>
                        <OverflowMenuItem itemText="Move to folder" onClick={() => setMoveTarget(p)} />
                        <OverflowMenuItem itemText="Backup project"  onClick={() => setBackupTarget(p)} />
                        <OverflowMenuItem itemText="Delete project" isDelete hasDivider onClick={() => setDeleteTarget(p)} />
                      </OverflowMenu>
                    );
                  })()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Modals ──────────────────────────────────────────────────────── */}

      {/* Create folder */}
      {createFolderParent !== undefined && (
        <FolderCreateModal
          parentFolder={createFolderParent}
          onClose={() => setCreateFolderParent(undefined)}
          onCreated={handleFolderCreated}
        />
      )}

      {/* Rename folder */}
      <Modal
        open={!!renameFolderTarget}
        modalHeading={`Rename "${renameFolderTarget?.name}"`}
        primaryButtonText={renameFolderLoading ? 'Saving…' : 'Save'}
        secondaryButtonText="Cancel"
        primaryButtonDisabled={renameFolderLoading || !renameFolderValue.trim()}
        onRequestSubmit={handleRenameFolder}
        onRequestClose={() => setRenameFolderTarget(null)}
      >
        <TextInput
          id="rename-folder-input"
          labelText="Folder name"
          value={renameFolderValue}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setRenameFolderValue(e.target.value)}
          autoFocus
        />
      </Modal>

      {/* Delete folder confirmation */}
      <Modal
        open={!!deleteFolderTarget}
        danger
        modalHeading={`Delete folder "${deleteFolderTarget?.name}"?`}
        primaryButtonText={deleteFolderLoading ? 'Deleting…' : 'Delete folder'}
        secondaryButtonText="Cancel"
        primaryButtonDisabled={deleteFolderLoading}
        onRequestSubmit={handleDeleteFolder}
        onRequestClose={() => setDeleteFolderTarget(null)}
      >
        <p style={{ color: '#525252', lineHeight: 1.6 }}>
          The folder will be deleted. Any projects directly inside will be moved to the root level —
          they will <strong>not</strong> be deleted. Sub-folders will be deleted with all their contents.
        </p>
      </Modal>

      {/* Move project */}
      {moveTarget && (
        <MoveProjectModal
          project={moveTarget}
          onClose={() => setMoveTarget(null)}
          onMoved={handleProjectMoved}
        />
      )}

      {/* Backup single project */}
      {backupTarget && (
        <BackupModal mode="project" project={backupTarget} onClose={() => setBackupTarget(null)} />
      )}

      {/* Backup all */}
      {backupAllOpen && (
        <BackupModal mode="all" onClose={() => setBackupAllOpen(false)} />
      )}

      {/* Delete project confirmation */}
      <Modal
        open={!!deleteTarget}
        danger
        modalHeading={`Delete "${deleteTarget?.name}"?`}
        primaryButtonText={deleteLoading ? 'Deleting…' : 'Delete'}
        secondaryButtonText="Cancel"
        onRequestSubmit={handleDeleteProject}
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
