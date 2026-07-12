import { useState, useEffect } from 'react';
import { Modal, TextInput, NumberInput, Select, SelectItem, InlineNotification, InlineLoading } from '@carbon/react';
import { api, ServerRecord } from '../api/client';
import { IBM_OS_OPTIONS } from '../constants/osOptions';

interface Props {
  open: boolean;
  projectId: string;
  record: ServerRecord;
  onClose: () => void;
  onSaved: (updated: ServerRecord) => void;
}

// ---------------------------------------------------------------------------
// Field definitions
// ---------------------------------------------------------------------------
type FieldSeverity = 'critical' | 'advisory';

interface VinfoField {
  key: string;
  label: string;
  type: 'text' | 'number' | 'select' | 'os-select';
  options?: string[];
  helperText?: string;
  severity?: FieldSeverity;   // missing = no warning
}

const VINFO_FIELDS: VinfoField[] = [
  { key: 'vm_name',        label: 'Server Name',           type: 'text',      severity: 'critical' },
  { key: 'cpus',           label: 'vCPUs',                 type: 'number',    severity: 'critical' },
  { key: 'memory_mb',      label: 'RAM (MB)',              type: 'number',    severity: 'critical' },
  { key: 'provisioned_mb', label: 'Disk Provisioned (MB)', type: 'number',    severity: 'critical',
    helperText: 'Total allocated disk size. Used as the Data Volume size in the Cloud Solution Export.' },
  { key: 'in_use_mb',      label: 'Disk In Use (MB)',      type: 'number',    severity: 'advisory',
    helperText: 'AI-estimated at 60% of provisioned. Override if customer provided actual utilization.' },
  { key: 'os_config',      label: 'OS (Config File)',      type: 'os-select', severity: 'critical' },
  { key: 'datacenter',     label: 'vCenter Datacenter',    type: 'text',      severity: 'advisory',
    helperText: 'On-premises VMware datacenter name (RVTools schema). Not the IBM Cloud target zone.' },
  { key: 'cluster',        label: 'vCenter Cluster',       type: 'text',      severity: 'advisory' },
  { key: 'powerstate',     label: 'Power State',           type: 'select',
    options: ['poweredOn', 'poweredOff', 'suspended'] },
  { key: 'nics',           label: 'NICs',                  type: 'number',    severity: 'advisory' },
  { key: 'disks',          label: 'Disk Count',            type: 'number',    severity: 'advisory' },
];

const CRITICAL_BORDER = '3px solid #da1e28';
const ADVISORY_BORDER = '3px solid #f1c21b';

function getVinfo(record: ServerRecord): Record<string, any> {
  return record.normalized_data?.vinfo ?? {};
}

function isEmpty(val: any): boolean {
  if (val === null || val === undefined || val === '') return true;
  if (typeof val === 'number' && val === 0) return true;
  return false;
}

function getWarning(field: VinfoField, val: any): FieldSeverity | null {
  if (!field.severity) return null;
  return isEmpty(val) ? field.severity : null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function EditRecordModal({ open, projectId, record, onClose, onSaved }: Props) {
  const [fields, setFields] = useState<Record<string, any>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');

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

  const vmName  = getVinfo(record)['vm_name'] ?? record.id;
  const rowNum  = record.raw_data?._row_number;

  // Compute warning counts
  const warnings = VINFO_FIELDS.map(f => getWarning(f, fields[f.key])).filter(Boolean);
  const criticalCount = warnings.filter(w => w === 'critical').length;
  const advisoryCount = warnings.filter(w => w === 'advisory').length;
  const totalWarnings = warnings.length;

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
      {/* Source row reference */}
      {rowNum != null && (
        <p style={{ fontSize: '0.75rem', color: '#6f6f6f', marginBottom: '0.5rem', marginTop: '-0.25rem' }}>
          Source: <strong>Row {rowNum}</strong> in your spreadsheet
        </p>
      )}

      {error && (
        <InlineNotification kind="error" title={error} lowContrast
          style={{ marginBottom: '1rem' }} onCloseButtonClick={() => setError('')} />
      )}

      {totalWarnings > 0 && (
        <InlineNotification
          kind="warning"
          title={`${totalWarnings} field${totalWarnings !== 1 ? 's' : ''} need${totalWarnings === 1 ? 's' : ''} attention`}
          subtitle={
            criticalCount > 0
              ? `${criticalCount} critical (red) and ${advisoryCount} advisory (yellow) field${advisoryCount !== 1 ? 's' : ''} are empty. Review the original spreadsheet and fill them in.`
              : `${advisoryCount} advisory field${advisoryCount !== 1 ? 's' : ''} are empty — exports will still work but may use defaults.`
          }
          lowContrast
          style={{ marginBottom: '1rem' }}
        />
      )}

      {saving && <InlineLoading description="Saving…" style={{ marginBottom: '1rem' }} />}

      <p style={{ fontSize: '0.875rem', color: '#525252', marginBottom: '1rem', lineHeight: 1.6 }}>
        Edit normalized vInfo fields. Changes are saved directly — the AI will not re-run.
        Use the Retry button on the Review page to re-normalize the entire record from scratch.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
        {VINFO_FIELDS.map(f => {
          const val     = fields[f.key] ?? '';
          const warning = getWarning(f, val);
          const borderLeft = warning === 'critical' ? CRITICAL_BORDER
            : warning === 'advisory' ? ADVISORY_BORDER
            : undefined;
          const labelColor = warning === 'critical' ? '#da1e28' : undefined;

          const wrapStyle: React.CSSProperties = borderLeft
            ? { borderLeft, paddingLeft: '0.5rem' }
            : {};

          if (f.type === 'os-select') {
            // OS field: Carbon Select from IBM_OS_OPTIONS
            // If current value isn't in the list, add it as the first option
            const currentOs = String(val ?? '');
            const options = IBM_OS_OPTIONS.includes(currentOs) || !currentOs
              ? IBM_OS_OPTIONS
              : [currentOs, ...IBM_OS_OPTIONS];
            return (
              <div key={f.key} style={wrapStyle}>
                <Select
                  id={`edit-${f.key}`}
                  labelText={f.label}
                  value={currentOs}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => handleChange(f.key, e.target.value)}
                >
                  {!currentOs && <SelectItem value="" text="— Select an OS —" />}
                  {options.map(opt => (
                    <SelectItem key={opt} value={opt} text={opt} />
                  ))}
                </Select>
                {warning === 'critical' && (
                  <p style={{ fontSize: '0.75rem', color: '#da1e28', marginTop: '0.2rem' }}>
                    Required for export — please select an OS.
                  </p>
                )}
              </div>
            );
          }

          if (f.type === 'select') {
            return (
              <div key={f.key} style={wrapStyle}>
                <Select
                  id={`edit-${f.key}`}
                  labelText={f.label}
                  value={String(val)}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => handleChange(f.key, e.target.value)}
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
              <div key={f.key} style={wrapStyle}>
                <NumberInput
                  id={`edit-${f.key}`}
                  label={f.label}
                  value={val === '' || val == null ? 0 : Number(val)}
                  min={0}
                  onChange={(_e: any, { value }: any) => handleChange(f.key, value)}
                  hideSteppers
                  style={labelColor ? { '--cds-text-primary': labelColor } as React.CSSProperties : undefined}
                />
                {f.helperText && (
                  <p style={{ fontSize: '0.75rem', color: '#6f6f6f', marginTop: '0.25rem' }}>{f.helperText}</p>
                )}
                {warning === 'critical' && (
                  <p style={{ fontSize: '0.75rem', color: '#da1e28', marginTop: '0.2rem' }}>Required for export.</p>
                )}
              </div>
            );
          }

          // text
          return (
            <div key={f.key} style={wrapStyle}>
              <TextInput
                id={`edit-${f.key}`}
                labelText={f.label}
                value={String(val ?? '')}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleChange(f.key, e.target.value)}
              />
              {f.helperText && (
                <p style={{ fontSize: '0.75rem', color: '#6f6f6f', marginTop: '0.25rem' }}>{f.helperText}</p>
              )}
              {warning === 'critical' && (
                <p style={{ fontSize: '0.75rem', color: '#da1e28', marginTop: '0.2rem' }}>Required for export.</p>
              )}
            </div>
          );
        })}
      </div>
    </Modal>
  );
}
