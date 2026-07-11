import { useState } from 'react';
import { Modal, TextInput, InlineNotification } from '@carbon/react';
import { api, Folder } from '../api/client';

interface Props {
  /** If set, the new folder is created as a child of this folder (engagement level) */
  parentFolder?: Folder | null;
  onClose: () => void;
  onCreated: (folder: Folder) => void;
}

export default function FolderCreateModal({ parentFolder, onClose, onCreated }: Props) {
  const [name, setName]       = useState('');
  const [nameError, setNameError] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState('');

  const isEngagement = !!parentFolder;
  const heading      = isEngagement
    ? `New engagement folder under "${parentFolder!.name}"`
    : 'New customer folder';

  async function handleSubmit() {
    const trimmed = name.trim();
    if (!trimmed) { setNameError('Folder name is required.'); return; }

    setLoading(true); setError('');
    try {
      const folder = await api.folders.create({
        name: trimmed,
        parent_id: parentFolder?.id ?? null,
      });
      onCreated(folder);
    } catch {
      setError('Failed to create folder. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      open
      modalHeading={heading}
      primaryButtonText={loading ? 'Creating…' : 'Create folder'}
      secondaryButtonText="Cancel"
      primaryButtonDisabled={loading}
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
      <TextInput
        id="folder-name-input"
        labelText="Folder name"
        placeholder={isEngagement ? 'e.g. Q3 Migration Wave' : 'e.g. Acme Corp'}
        value={name}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
          setName(e.target.value);
          if (e.target.value.trim()) setNameError('');
        }}
        invalid={!!nameError}
        invalidText={nameError}
        autoFocus
      />
      {isEngagement && (
        <p style={{ fontSize: '0.8125rem', color: '#6f6f6f', marginTop: '0.75rem' }}>
          This will create a sub-folder inside <strong>{parentFolder!.name}</strong> for grouping related projects by engagement or migration wave.
        </p>
      )}
    </Modal>
  );
}
