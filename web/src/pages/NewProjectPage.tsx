import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, TextInput, TextArea, InlineNotification } from '@carbon/react';
import { api } from '../api/client';

export default function NewProjectPage() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [nameError, setNameError] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

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
      navigate(`/projects/${project.id}/upload`);
    } catch {
      setLoading(false);
      setError('Failed to create project. Please try again.');
    }
  }

  return (
    <>
      <div className="page-header-band">
        <div className="page-header-inner">
          <h1 className="page-heading">New Project</h1>
          <p className="page-description">Create a project to start processing a customer spreadsheet.</p>
        </div>
      </div>

      <div className="page-body" style={{ maxWidth: 640 }}>
        {error && (
          <InlineNotification
            kind="error"
            title="Error"
            subtitle={error}
            lowContrast
            style={{ marginBottom: '1.5rem' }}
            onCloseButtonClick={() => setError('')}
          />
        )}

        <div className="ibm-card">
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
            style={{ marginBottom: '1.5rem' }}
          />
          <TextArea
            id="project-description"
            labelText="Description (optional)"
            placeholder="Brief description of this migration project"
            value={description}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setDescription(e.target.value)}
            rows={3}
          />
        </div>

        <div className="step-actions" style={{ borderTop: 'none', paddingTop: 0, marginTop: '1.5rem' }}>
          <Button onClick={handleSubmit} disabled={loading}>
            {loading ? 'Creating…' : 'Create Project'}
          </Button>
          <Button kind="ghost" onClick={() => navigate('/')}>
            Cancel
          </Button>
        </div>
      </div>
    </>
  );
}
