import { useState } from 'react';
import { Modal, TextInput, TextArea, InlineNotification } from '@carbon/react';
import { api, Project } from '../api/client';

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess: (project: Project) => void;
}

export default function CreateProjectModal({ open, onClose, onSuccess }: Props) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [nameError, setNameError] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  function handleClose() {
    setName('');
    setDescription('');
    setNameError('');
    setError('');
    onClose();
  }

  async function handleSubmit() {
    if (!name.trim()) {
      setNameError('Project name is required.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const project = await api.projects.create({
        name: name.trim(),
        description: description.trim() || undefined,
      });
      setLoading(false);
      setName('');
      setDescription('');
      onSuccess(project);
    } catch {
      setLoading(false);
      setError('Failed to create project. Please try again.');
    }
  }

  return (
    <Modal
      open={open}
      modalHeading="New Project"
      primaryButtonText={loading ? 'Creating…' : 'Create'}
      secondaryButtonText="Cancel"
      onRequestSubmit={handleSubmit}
      onRequestClose={handleClose}
      primaryButtonDisabled={loading}
    >
      {error && (
        <InlineNotification
          kind="error"
          title="Error"
          subtitle={error}
          lowContrast
          style={{ marginBottom: '1rem' }}
        />
      )}
      <TextInput
        id="project-name"
        labelText="Project name *"
        placeholder="e.g. Acme Corp Migration Q1"
        value={name}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
          setName(e.target.value);
          if (e.target.value.trim()) setNameError('');
        }}
        invalid={!!nameError}
        invalidText={nameError}
        style={{ marginBottom: '1rem' }}
      />
      <TextArea
        id="project-description"
        labelText="Description (optional)"
        placeholder="Brief description of this migration project"
        value={description}
        onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setDescription(e.target.value)}
        rows={3}
      />
    </Modal>
  );
}
