import { useState, useEffect } from 'react';
import { Modal, TextInput, NumberInput, Select, SelectItem, InlineNotification, InlineLoading } from '@carbon/react';
import { api, ServerRecord } from '../api/client';

interface Props {
  open: boolean;
  projectId: string;
  record: ServerRecord;
  onClose: () => void;
  onSaved: (updated: ServerRecord) => void;
}

// Editable vinfo fields with labels and types
const VINFO_FIELDS: Array<{ key: string; label: string; type: 'text' | 'number' | 'select'; options?: string[]; helperText?: string }> = [
  { key: 'vm_name',       label: 'Server Name',             type: 'text' },
  { key: 'cpus',          label: 'vCPUs',                   type: 'number' },
  { key: 'memory_mb',     label: 'RAM (MB)',                 type: 'number' },
  { key: 'provisioned_mb',label: 'Disk Provisioned (MB)',   type: 'number',
    helperText: 'Total allocated disk size. Used as the Data Volume size in the Cloud Solution Export.' },
  { key: 'in_use_mb',     label: 'Disk In Use (MB)',         type: 'number',
    helperText: 'AI-estimated at 60% of provisioned. Override if customer provided actual utilization.' },
  { key: 'datacenter',    label: 'vCenter Datacenter',       type: 'text',
    helperText: 'On-premises VMware datacenter name (RVTools schema). Not the IBM Cloud target zone.' },
  { key: 'cluster',       label: 'vCenter Cluster',          type: 'text' },
  { key: 'os_config',     label: 'OS (Config File)',         type: 'text' },
  { key: 'powerstate',    label: 'Power State',              type: 'select',
    options: ['poweredOn', 'poweredOff', 'suspended'] },
  { key: 'nics',          label: 'NICs',                     type: 'number' },
  { key: 'disks',         label: 'Disk Count',               type: 'number' },
];

function getVinfo(record: ServerRecord): Record<string, any> {
  return record.normalized_data?.vinfo ?? {};
}

export default function EditRecordModal({ open, projectId, record, onClose, onSaved }: Props) {
  const [fields, setFields] = useState<Record<string, any>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) {
      setFields({ ...getVinfo(record) });
      setError('');
    }
  }, [open, record]);

  function handleChange(key: string, value: any) {
    setFields(prev => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    setSaving(true);
    setError('');
    try {
      const updated = await api.uploads.patchRecord(projectId, record.id, fields);
      onSaved(updated);
    } catch {
      setError('Failed to save changes. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  const vmName = getVinfo(record)['vm_name'] ?? record.id;

  return (
    <Modal
      open={open}
      modalHeading={`Edit: ${vmName}`}
      primaryButtonText={saving ? 'Saving…' : 'Save changes'}
      secondaryButtonText="Cancel"
      primaryButtonDisabled={saving}
      onRequestSubmit={handleSave}
      onRequestClose={onClose}
      size="lg"
    >
      {error && (
        <InlineNotification
          kind="error"
          title={error}
          lowContrast
          style={{ marginBottom: '1rem' }}
          onCloseButtonClick={() => setError('')}
        />
      )}

      {saving && <InlineLoading description="Saving…" style={{ marginBottom: '1rem' }} />}

      <p style={{ fontSize: '0.875rem', color: '#525252', marginBottom: '1rem', lineHeight: 1.6 }}>
        Edit normalized vInfo fields. Changes are saved directly — the AI will not re-run.
        Use the Retry button to re-normalize the entire record from scratch.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
        {VINFO_FIELDS.map(f => {
          const val = fields[f.key] ?? '';
          if (f.type === 'select') {
            return (
              <div key={f.key}>
                <Select
                  id={`edit-${f.key}`}
                  labelText={f.label}
                  value={String(val)}
                  onChange={e => handleChange(f.key, e.target.value)}
                >
                  {(f.options ?? []).map(opt => (
                    <SelectItem key={opt} value={opt} text={opt} />
                  ))}
                </Select>
              </div>
            );
          }
          if (f.type === 'number') {
            return (
              <div key={f.key}>
                <NumberInput
                  id={`edit-${f.key}`}
                  label={f.label}
                  value={val === '' || val == null ? 0 : Number(val)}
                  min={0}
                  onChange={(_e: any, { value }: any) => handleChange(f.key, value)}
                  hideSteppers
                />
                {f.helperText && (
                  <p style={{ fontSize: '0.75rem', color: '#6f6f6f', marginTop: '0.25rem' }}>{f.helperText}</p>
                )}
              </div>
            );
          }
          return (
            <div key={f.key}>
              <TextInput
                id={`edit-${f.key}`}
                labelText={f.label}
                value={String(val ?? '')}
                onChange={e => handleChange(f.key, e.target.value)}
              />
              {f.helperText && (
                <p style={{ fontSize: '0.75rem', color: '#6f6f6f', marginTop: '0.25rem' }}>{f.helperText}</p>
              )}
            </div>
          );
        })}
      </div>
    </Modal>
  );
}
