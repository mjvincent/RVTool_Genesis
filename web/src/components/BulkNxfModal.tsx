import { useState } from 'react';
import { Modal, Select, SelectItem, InlineNotification, Accordion, AccordionItem } from '@carbon/react';
import { api } from '../api/client';

interface Props {
  projectId: string;
  unsupportedCount: number;
  previewNames?: string[];
  onClose: () => void;
  onApplied: (updatedCount: number, targetProfile: string) => void;
}

const TARGET_OPTIONS = [
  { value: 'nxf-2x1', label: 'nxf-2x1 — 2 vCPU / 1 GB RAM' },
  { value: 'nxf-2x2', label: 'nxf-2x2 — 2 vCPU / 2 GB RAM' },
];

export default function BulkNxfModal({ projectId, unsupportedCount, onClose, onApplied }: Props) {
  const [targetProfile, setTargetProfile] = useState<string>('nxf-2x1');
  const [saving, setSaving]               = useState(false);
  const [error, setError]                 = useState('');

  async function handleApply() {
    setSaving(true); setError('');
    try {
      const result = await api.uploads.bulkNxfReplace(projectId, targetProfile);
      onApplied(result.updated_count, result.target_profile);
    } catch (err) {
      setError(`Failed to apply profile replacement: ${(err as any)?.detail || (err as any)?.message || 'Please try again.'}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open
      modalHeading="Fix Unsupported Flex-Nano Profiles"
      primaryButtonText={saving ? 'Applying…' : `Replace on ${unsupportedCount} server${unsupportedCount !== 1 ? 's' : ''}`}
      secondaryButtonText="Cancel"
      primaryButtonDisabled={saving}
      onRequestSubmit={handleApply}
      onRequestClose={onClose}
    >
      {error && (
        <InlineNotification kind="error" title="Error" subtitle={error} lowContrast
          style={{ marginBottom: '1rem' }} onCloseButtonClick={() => setError('')} />
      )}

      <p style={{ fontSize: '0.875rem', color: '#525252', marginBottom: '1rem', lineHeight: 1.6 }}>
        The IBM Cloud Solutioning tool only recognises <strong>nxf-2x1</strong> and{' '}
        <strong>nxf-2x2</strong> in its Data Domains sheet. Profiles{' '}
        <strong>nxf-1x1</strong>, <strong>nxf-1x2</strong>, and <strong>nxf-1x4</strong>{' '}
        are absent and will silently fail to populate when you import the Cloud Solution export.
      </p>

      <p style={{ fontSize: '0.875rem', color: '#525252', marginBottom: '1.5rem', lineHeight: 1.6 }}>
        This will upgrade the <strong>{unsupportedCount} affected server{unsupportedCount !== 1 ? 's' : ''}</strong> to
        your chosen target profile by setting <code>num_cpus = 2</code> and the matching RAM.
        The change is logged as an assumption in the AI Assumptions Report.
      </p>

      <Select
        id="bulk-nxf-target"
        labelText="Replace all nxf-1x* servers with"
        value={targetProfile}
        onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setTargetProfile(e.target.value)}
        style={{ marginBottom: '1.25rem' }}
      >
        {TARGET_OPTIONS.map(o => (
          <SelectItem key={o.value} value={o.value} text={o.label} />
        ))}
      </Select>

      <p style={{ fontSize: '0.8125rem', color: '#0043ce', background: '#edf5ff', padding: '0.5rem 0.75rem', borderRadius: 4, marginBottom: previewNames && previewNames.length > 0 ? '0.75rem' : 0 }}>
        <strong>{unsupportedCount} server{unsupportedCount !== 1 ? 's' : ''}</strong>{' '}
        will be updated: <strong>nxf-1x*</strong> → <strong>{targetProfile}</strong>.
      </p>

      {previewNames && previewNames.length > 0 && (
        <Accordion>
          <AccordionItem title={`Show ${unsupportedCount} affected server${unsupportedCount !== 1 ? 's' : ''}`}>
            <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.8125rem', lineHeight: 1.8 }}>
              {previewNames.map(name => <li key={name}>{name}</li>)}
            </ul>
            {unsupportedCount > previewNames.length && (
              <p style={{ fontSize: '0.8125rem', color: '#6f6f6f', marginTop: '0.5rem' }}>
                …and {unsupportedCount - previewNames.length} more
              </p>
            )}
          </AccordionItem>
        </Accordion>
      )}
    </Modal>
  );
}
