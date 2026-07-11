import { useState, useEffect } from 'react';
import { Modal, Select, SelectItem, InlineNotification, InlineLoading } from '@carbon/react';
import { api, Project } from '../api/client';

interface Props {
  project: Project;
  onClose: () => void;
  onMoved: (updated: Project) => void;
}

interface FolderOption {
  id: string | null;
  label: string;
  indent: boolean;
}

export default function MoveProjectModal({ project, onClose, onMoved }: Props) {
  const [options, setOptions]     = useState<FolderOption[]>([]);
  const [loadingFolders, setLoadingFolders] = useState(true);
  const [selected, setSelected]   = useState<string>(project.folder_id ?? '__root__');
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState('');

  useEffect(() => {
    async function loadFolders() {
      try {
        // Load root-level folders
        const rootRes = await api.folders.list(null);
        const opts: FolderOption[] = [
          { id: null, label: '— No folder (root)', indent: false },
        ];
        for (const rf of rootRes.folders) {
          opts.push({ id: rf.id, label: rf.name, indent: false });
          // Load children of this root folder
          if (rf.child_count > 0) {
            const childRes = await api.folders.list(rf.id);
            for (const cf of childRes.folders) {
              opts.push({ id: cf.id, label: `  ↳ ${cf.name}`, indent: true });
            }
          }
        }
        setOptions(opts);
      } catch {
        setError('Could not load folders.');
      } finally {
        setLoadingFolders(false);
      }
    }
    loadFolders();
  }, []);

  async function handleSubmit() {
    const newFolderId = selected === '__root__' ? null : selected;
    // No-op if unchanged
    if ((newFolderId ?? null) === (project.folder_id ?? null)) { onClose(); return; }

    setSaving(true); setError('');
    try {
      const updated = await api.projects.update(project.id, { folder_id: newFolderId });
      onMoved(updated);
    } catch {
      setError('Failed to move project. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open
      modalHeading={`Move "${project.name}"`}
      primaryButtonText={saving ? 'Moving…' : 'Move project'}
      secondaryButtonText="Cancel"
      primaryButtonDisabled={saving || loadingFolders}
      onRequestSubmit={handleSubmit}
      onRequestClose={onClose}
    >
      {error && (
        <InlineNotification
          kind="error"
          title="Error"
          subtitle={error}
          lowContrast
          style={{ marginBottom: '1rem' }}
          onCloseButtonClick={() => setError('')}
        />
      )}
      {loadingFolders ? (
        <InlineLoading description="Loading folders…" />
      ) : (
        <Select
          id="move-folder-select"
          labelText="Destination folder"
          value={selected}
          onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setSelected(e.target.value)}
        >
          {options.map(opt => (
            <SelectItem
              key={opt.id ?? '__root__'}
              value={opt.id ?? '__root__'}
              text={opt.label}
            />
          ))}
        </Select>
      )}
    </Modal>
  );
}
