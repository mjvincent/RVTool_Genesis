import { useState, useMemo } from 'react';
import { Modal, Select, SelectItem, TextInput, InlineNotification } from '@carbon/react';
import { api, ServerRecord } from '../api/client';
import { shortOsLabel } from '../constants/osOptions';

interface Props {
  projectId: string;
  records: ServerRecord[];   // all non-excluded, complete records
  onClose: () => void;
  onApplied: (updatedCount: number, filterType: string, filterValue: string) => void;
}

function getOs(r: ServerRecord): string | null {
  return r.normalized_data?.vinfo?.os_config ?? null;
}
function getName(r: ServerRecord): string {
  return r.normalized_data?.vinfo?.vm_name ?? '';
}

export default function BulkExcludeModal({ projectId, records, onClose, onApplied }: Props) {
  const [filterType, setFilterType] = useState<'name' | 'os'>('name');
  const [filterValue, setFilterValue] = useState('');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Distinct OS values present in this project
  const osOptions = useMemo<string[]>(() => {
    const seen = new Set<string>();
    for (const r of records) {
      const os = getOs(r);
      if (os) seen.add(os);
    }
    return Array.from(seen).sort();
  }, [records]);

  // Live preview count of matching records
  const affectedCount = useMemo(() => {
    if (!filterValue.trim()) return 0;
    return records.filter(r => {
      if (!r.normalized_data) return false;
      if (filterType === 'name') {
        return getName(r).toLowerCase().includes(filterValue.trim().toLowerCase());
      }
      return getOs(r) === filterValue;
    }).length;
  }, [records, filterType, filterValue]);

  async function handleApply() {
    if (!filterValue.trim() || affectedCount === 0) return;
    setSaving(true); setError('');
    try {
      const result = await api.uploads.bulkExclude(
        projectId, filterType, filterValue.trim(), reason.trim() || undefined
      );
      onApplied(result.updated_count, result.filter_type, result.filter_value);
    } catch (err) {
      setError(`Failed to apply bulk exclusion: ${(err as any)?.detail || (err as any)?.message || 'Please try again.'}`);
    } finally {
      setSaving(false);
    }
  }

  const canApply = !saving && filterValue.trim().length > 0 && affectedCount > 0;

  return (
    <Modal
      open
      modalHeading="Bulk Exclude"
      primaryButtonText={saving ? 'Excluding…' : `Exclude ${affectedCount} record${affectedCount !== 1 ? 's' : ''}`}
      secondaryButtonText="Cancel"
      primaryButtonDisabled={!canApply}
      onRequestSubmit={handleApply}
      onRequestClose={onClose}
    >
      {error && (
        <InlineNotification kind="error" title="Error" subtitle={error} lowContrast
          style={{ marginBottom: '1rem' }} onCloseButtonClick={() => setError('')} />
      )}

      <p style={{ fontSize: '0.875rem', color: '#525252', marginBottom: '1.5rem', lineHeight: 1.6 }}>
        Exclude all active records matching a server name substring or OS family in one action.
        Excluded records are removed from all exports and listed in the Excluded Servers audit sheet.
      </p>

      {/* Filter type + value */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '1.25rem' }}>
        <Select
          id="bulk-exclude-filter-type"
          labelText="Filter by"
          value={filterType}
          onChange={(e: React.ChangeEvent<HTMLSelectElement>) => {
            setFilterType(e.target.value as 'name' | 'os');
            setFilterValue('');
          }}
        >
          <SelectItem value="name" text="Server name contains…" />
          <SelectItem value="os"   text="OS equals…" />
        </Select>

        {filterType === 'os' ? (
          <Select
            id="bulk-exclude-os-value"
            labelText="OS to exclude"
            value={filterValue}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setFilterValue(e.target.value)}
          >
            <SelectItem value="" text="— select OS —" />
            {osOptions.map(os => (
              <SelectItem key={os} value={os} text={shortOsLabel(os)} />
            ))}
          </Select>
        ) : (
          <TextInput
            id="bulk-exclude-name-value"
            labelText="Name substring"
            placeholder="e.g.  dev  or  test-"
            value={filterValue}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFilterValue(e.target.value)}
          />
        )}
      </div>

      {/* Optional reason */}
      <TextInput
        id="bulk-exclude-reason"
        labelText="Exclusion reason (optional)"
        placeholder="e.g. Test / dev servers — out of scope"
        value={reason}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setReason(e.target.value)}
        style={{ marginBottom: '1rem' }}
      />

      {/* Live preview */}
      {filterValue.trim().length > 0 && (
        <p style={{
          fontSize: '0.8125rem',
          color: affectedCount > 0 ? '#0043ce' : '#6f6f6f',
          background: affectedCount > 0 ? '#edf5ff' : '#f4f4f4',
          padding: '0.5rem 0.75rem',
          borderRadius: 4,
        }}>
          {affectedCount > 0
            ? <>Will exclude <strong>{affectedCount} record{affectedCount !== 1 ? 's' : ''}</strong> matching "{filterValue.trim()}".</>
            : <>No active records match "{filterValue.trim()}".</>}
        </p>
      )}
    </Modal>
  );
}
