import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button, TextInput, TextArea, Select, SelectItem, InlineNotification } from '@carbon/react';
import { api, IBM_VPC_REGIONS } from '../api/client';

export default function NewProjectPage() {
  const navigate       = useNavigate();
  const [searchParams] = useSearchParams();
  // Pre-assigned folder from URL: /projects/new?folder_id=<uuid>
  const presetFolderId = searchParams.get('folder_id') ?? null;

  const [name, setName]               = useState('');
  const [description, setDescription] = useState('');
  const [vpcRegion, setVpcRegion]     = useState('us-south');
  const [vpcDc, setVpcDc]             = useState('us-south-1');
  const [nameError, setNameError]     = useState('');
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState('');

  // When region changes, auto-reset datacenter to zone-1 of new region
  useEffect(() => {
    const zones = IBM_VPC_REGIONS[vpcRegion]?.zones ?? [];
    setVpcDc(zones[0] ?? `${vpcRegion}-1`);
  }, [vpcRegion]);

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
        folder_id: presetFolderId,
        vpc_region: vpcRegion,
        vpc_datacenter: vpcDc,
      });
      navigate(`/projects/${project.id}/upload`);
    } catch (err) {
      setLoading(false);
      setError(`Failed to create project: ${(err as any)?.detail || (err as any)?.message || 'Please try again.'}`);
    }
  }

  const regionInfo = IBM_VPC_REGIONS[vpcRegion];
  const zones = regionInfo?.zones ?? [`${vpcRegion}-1`];

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
            style={{ marginBottom: '1.5rem' }}
          />

          {/* Divider */}
          <div style={{ borderTop: '1px solid #e0e0e0', margin: '0.5rem 0 1.5rem' }} />
          <p style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#525252', marginBottom: '0.75rem' }}>
            IBM Cloud VPC Target
            <span style={{ fontWeight: 400, marginLeft: '0.5rem', color: '#6f6f6f' }}>
              — used for the VPC Calculator export
            </span>
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '0.25rem' }}>
            <Select
              id="vpc-region"
              labelText="Target region"
              value={vpcRegion}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setVpcRegion(e.target.value)}
            >
              {Object.entries(IBM_VPC_REGIONS).map(([key, val]) => (
                <SelectItem key={key} value={key} text={val.label} />
              ))}
            </Select>

            <Select
              id="vpc-datacenter"
              labelText="Availability zone"
              value={vpcDc}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setVpcDc(e.target.value)}
            >
              {zones.map(z => (
                <SelectItem key={z} value={z} text={z} />
              ))}
            </Select>
          </div>

          {regionInfo && (
            <p style={{ fontSize: '0.75rem', color: '#6f6f6f', margin: '0.25rem 0 0' }}>
              Geography: <strong>{regionInfo.geography}</strong>
            </p>
          )}
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
