import { useState, useEffect } from 'react';
import { Modal, TextInput, NumberInput, Select, SelectItem, InlineNotification, InlineLoading } from '@carbon/react';
import { ChevronDown, ChevronUp } from '@carbon/icons-react';
import { api, ServerRecord } from '../api/client';
import { IBM_OS_OPTIONS } from '../constants/osOptions';

interface Props {
  open: boolean;
  projectId: string;
  record: ServerRecord;
  /**
   * When true AND the record has no normalized_data, pre-populate form fields
   * using a best-effort mapping of raw_data keys. Also expands the raw data
   * panel by default so the user can cross-reference the source spreadsheet.
   */
  prefillFromRaw?: boolean;
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
  severity?: FieldSeverity;
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

// ---------------------------------------------------------------------------
// Raw-data best-effort pre-fill
// ---------------------------------------------------------------------------

/**
 * Priority-ordered synonyms for each vinfo field.
 * First match wins (case-insensitive key comparison).
 */
const RAW_FIELD_SYNONYMS: Record<string, string[]> = {
  vm_name:        ['name', 'server name', 'vm name', 'hostname', 'vm_name', 'server', 'host', 'computername', 'computer name'],
  cpus:           ['cpu', 'vcpu', 'cpus', 'vcpus', 'cores', 'cpu_count', 'num cpu', 'numcpu', 'processors', 'total cpus'],
  memory_mb:      ['memory (mb)', 'memory_mb', 'ram (mb)', 'ram(mb)', 'memory mb', 'mem (mb)', 'mem(mb)', 'memory', 'ram'],
  provisioned_mb: ['provisioned mb', 'provisioned_mb', 'disk (mb)', 'storage (mb)', 'disk mb', 'total disk', 'disk size', 'storage', 'disk', 'provisioned storage'],
  os_config:      ['os', 'operating system', 'guest os', 'os_config', 'os config', 'operating_system', 'guestosname', 'os version', 'os type'],
  datacenter:     ['datacenter', 'data center', 'dc', 'site'],
  cluster:        ['cluster', 'cluster name', 'vmware cluster'],
};

function prefillFromRawData(rawData: Record<string, any>): Record<string, any> {
  const result: Record<string, any> = {};

  // Build a lowercase→original-key lookup for the raw data
  const lowerKeys: Record<string, string> = {};
  for (const k of Object.keys(rawData)) {
    lowerKeys[k.toLowerCase().trim()] = k;
  }

  for (const [vinfoKey, synonyms] of Object.entries(RAW_FIELD_SYNONYMS)) {
    for (const syn of synonyms) {
      const origKey = lowerKeys[syn.toLowerCase()];
      if (origKey != null && rawData[origKey] != null) {
        let val = rawData[origKey];

        // Memory/disk: if the value looks like GB (< 512), convert to MB
        if ((vinfoKey === 'memory_mb' || vinfoKey === 'provisioned_mb') && typeof val === 'number') {
          if (val < 512 && val > 0) val = Math.round(val * 1024);
        }
        result[vinfoKey] = val;
        break;
      }
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
export default function EditRecordModal({ open, projectId, record, prefillFromRaw = false, onClose, onSaved }: Props) {
  const [fields, setFields]           = useState<Record<string, any>>({});
  const [saving, setSaving]           = useState(false);
  const [error, setError]             = useState('');
  const [rawPanelOpen, setRawPanelOpen] = useState(false);

  const isFailed = record.processing_status === 'error' || (record as any).status === 'error';
  const hasNormalized = !!(record.normalized_data && Object.keys(record.normalized_data).length > 0);

  useEffect(() => {
    if (open) {
      setError('');
      if (!hasNormalized && prefillFromRaw) {
        // Failed record — pre-populate from raw_data
        setFields(prefillFromRawData(record.raw_data ?? {}));
        setRawPanelOpen(true);  // Expand raw panel by default for failed records
      } else {
        setFields({ ...getVinfo(record) });
        setRawPanelOpen(false);
      }
    }
  }, [open, record, prefillFromRaw, hasNormalized]);

  function handleChange(key: string, value: any) {
    setFields(prev => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    setSaving(true);
    setError('');
    try {
      const updated = await api.uploads.patchRecord(projectId, record.id, fields);
      onSaved(updated);
    } catch (err) {
      setError(`Failed to save changes: ${(err as any)?.detail || (err as any)?.message || 'Please try again.'}`);
    } finally {
      setSaving(false);
    }
  }

  const vmName = hasNormalized
    ? (getVinfo(record)['vm_name'] ?? record.id)
    : (record.raw_data?.name ?? record.raw_data?.['Server Name'] ?? record.raw_data?.vm_name ?? record.id);
  const rowNum = record.raw_data?._row_number;

  // Warning counts
  const warnings      = VINFO_FIELDS.map(f => getWarning(f, fields[f.key])).filter(Boolean);
  const criticalCount = warnings.filter(w => w === 'critical').length;
  const advisoryCount = warnings.filter(w => w === 'advisory').length;
  const totalWarnings = warnings.length;

  // Raw data entries for the sidebar (exclude internal keys)
  const rawEntries = Object.entries(record.raw_data ?? {})
    .filter(([k]) => k !== '_row_number')
    .sort(([a], [b]) => a.localeCompare(b));

  return (
    <Modal
      open={open}
      modalHeading={isFailed && !hasNormalized ? `Manual entry: ${vmName}` : `Edit: ${vmName}`}
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

      {/* Failed-record context banner */}
      {isFailed && !hasNormalized && (
        <InlineNotification
          kind="info"
          title="AI normalization failed for this record"
          subtitle="Fields below have been pre-filled from your spreadsheet where possible. Review each value, correct anything that looks wrong, and click Save — the record will be promoted to complete status."
          lowContrast
          style={{ marginBottom: '1rem' }}
        />
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
              ? `${criticalCount} critical (red-highlighted) and ${advisoryCount} advisory (yellow-highlighted) field${advisoryCount !== 1 ? 's' : ''} are empty. Refer to your spreadsheet and fill them in.`
              : `${advisoryCount} advisory field${advisoryCount !== 1 ? 's' : ''} are empty — exports will still work but may use defaults.`
          }
          lowContrast
          style={{ marginBottom: '1rem' }}
        />
      )}

      {saving && <InlineLoading description="Saving…" style={{ marginBottom: '1rem' }} />}

      <p style={{ fontSize: '0.875rem', color: '#525252', marginBottom: '1rem', lineHeight: 1.6 }}>
        {isFailed && !hasNormalized
          ? 'Enter the correct values from your spreadsheet. All changes are saved directly — the AI will not re-run.'
          : 'Edit normalized vInfo fields. Changes are saved directly — the AI will not re-run. Use the Retry button on the Review page to re-normalize from scratch.'}
      </p>

      {/* ── vInfo fields grid ─────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
        {VINFO_FIELDS.map(f => {
          const val     = fields[f.key] ?? '';
          const warning = getWarning(f, val);
          const borderLeft = warning === 'critical' ? CRITICAL_BORDER
            : warning === 'advisory' ? ADVISORY_BORDER
            : undefined;

          const wrapStyle: React.CSSProperties = borderLeft
            ? { borderLeft, paddingLeft: '0.5rem' }
            : {};

          if (f.type === 'os-select') {
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

      {/* ── Original spreadsheet data panel ──────────────────────────── */}
      {rawEntries.length > 0 && (
        <div style={{ marginTop: '1.5rem', borderTop: '1px solid #e0e0e0', paddingTop: '1rem' }}>
          <button
            onClick={() => setRawPanelOpen(o => !o)}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.5rem',
              background: 'none', border: 'none', padding: 0,
              fontSize: '0.875rem', fontWeight: 600, color: '#525252',
              cursor: 'pointer', marginBottom: rawPanelOpen ? '0.75rem' : 0,
            }}
          >
            {rawPanelOpen
              ? <ChevronUp size={16} />
              : <ChevronDown size={16} />}
            {rowNum != null
              ? `Original data from Row ${rowNum} in your spreadsheet`
              : 'Original spreadsheet data'}
            <span style={{ fontWeight: 400, color: '#8d8d8d', fontSize: '0.8125rem' }}>
              ({rawEntries.length} columns)
            </span>
          </button>

          {rawPanelOpen && (
            <div style={{
              background: '#f4f4f4',
              border: '1px solid #e0e0e0',
              borderRadius: 4,
              overflow: 'auto',
              maxHeight: 280,
            }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                <thead>
                  <tr style={{ background: '#e0e0e0' }}>
                    <th style={{ padding: '0.4rem 0.75rem', textAlign: 'left', fontWeight: 600, color: '#525252', whiteSpace: 'nowrap' }}>
                      Column
                    </th>
                    <th style={{ padding: '0.4rem 0.75rem', textAlign: 'left', fontWeight: 600, color: '#525252' }}>
                      Value from spreadsheet
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rawEntries.map(([key, value], i) => (
                    <tr
                      key={key}
                      style={{ background: i % 2 === 0 ? '#ffffff' : '#f4f4f4' }}
                    >
                      <td style={{ padding: '0.35rem 0.75rem', color: '#525252', whiteSpace: 'nowrap', verticalAlign: 'top', fontWeight: 500 }}>
                        {key}
                      </td>
                      <td style={{ padding: '0.35rem 0.75rem', color: '#161616', wordBreak: 'break-word' }}>
                        {value == null ? <span style={{ color: '#8d8d8d', fontStyle: 'italic' }}>—</span> : String(value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
