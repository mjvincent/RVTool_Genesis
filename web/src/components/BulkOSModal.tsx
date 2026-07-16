import { useState, useMemo } from 'react';
import { Modal, Select, SelectItem, InlineNotification } from '@carbon/react';
import { api, ServerRecord } from '../api/client';
import { IBM_OS_OPTIONS, shortOsLabel } from '../constants/osOptions';

interface Props {
  projectId: string;
  records: ServerRecord[];     // all non-failed, non-excluded records (used to build source list)
  onClose: () => void;
  onApplied: (updatedCount: number, fromOs: string, toOs: string) => void;
}

function getOs(r: ServerRecord): string | null {
  return r.normalized_data?.vinfo?.os_config ?? null;
}

export default function BulkOSModal({ projectId, records, onClose, onApplied }: Props) {
  // Distinct OS values present in this project's normalized records (sorted)
  const sourceOptions = useMemo<string[]>(() => {
    const seen = new Set<string>();
    for (const r of records) {
      const os = getOs(r);
      if (os) seen.add(os);
    }
    return Array.from(seen).sort();
  }, [records]);

  const [fromOs, setFromOs] = useState<string>(sourceOptions[0] ?? '');
  const [toOs, setToOs]     = useState<string>(IBM_OS_OPTIONS[0]);
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');

  // Count how many records would be affected
  const affectedCount = useMemo(
    () => records.filter(r => getOs(r) === fromOs && !r.is_excluded).length,
    [records, fromOs]
  );

  async function handleApply() {
    if (!fromOs || !toOs || fromOs === toOs) return;
    setSaving(true); setError('');
    try {
      const result = await api.uploads.bulkOsReplace(projectId, fromOs, toOs);
      onApplied(result.updated_count, result.from_os, result.to_os);
    } catch (err) {
      setError(`Failed to apply OS replacement: ${(err as any)?.detail || (err as any)?.message || 'Please try again.'}`);
    } finally {
      setSaving(false);
    }
  }

  if (sourceOptions.length === 0) {
    return (
      <Modal
        open
        modalHeading="Bulk OS Replace"
        primaryButtonText="Close"
        onRequestSubmit={onClose}
        onRequestClose={onClose}
      >
        <p style={{ color: '#525252' }}>
          No normalized OS values found in this project. Run AI normalization first.
        </p>
      </Modal>
    );
  }

  return (
    <Modal
      open
      modalHeading="Bulk OS Replace"
      primaryButtonText={saving ? 'Applying…' : `Replace OS on ${affectedCount} record${affectedCount !== 1 ? 's' : ''}`}
      secondaryButtonText="Cancel"
      primaryButtonDisabled={saving || !fromOs || !toOs || fromOs === toOs || affectedCount === 0}
      onRequestSubmit={handleApply}
      onRequestClose={onClose}
    >
      {error && (
        <InlineNotification kind="error" title="Error" subtitle={error} lowContrast
          style={{ marginBottom: '1rem' }} onCloseButtonClick={() => setError('')} />
      )}

      <p style={{ fontSize: '0.875rem', color: '#525252', marginBottom: '1.5rem', lineHeight: 1.6 }}>
        Replace all records with a matching OS value with a different OS — useful for generating a
        lower-cost pricing estimate (e.g. replacing paid Windows or RHEL licences with free CentOS).
        Changes are permanent but logged as assumptions in the AI Assumptions Report so the
        substitution is clearly documented.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '1rem' }}>
        <Select
          id="bulk-os-from"
          labelText="Replace this OS"
          value={fromOs}
          onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setFromOs(e.target.value)}
        >
          {sourceOptions.map(os => (
            <SelectItem key={os} value={os} text={shortOsLabel(os)} />
          ))}
        </Select>

        <Select
          id="bulk-os-to"
          labelText="With this OS"
          value={toOs}
          onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setToOs(e.target.value)}
        >
          {IBM_OS_OPTIONS.map(os => (
            <SelectItem key={os} value={os} text={shortOsLabel(os)} />
          ))}
        </Select>
      </div>

      {affectedCount > 0 && fromOs !== toOs && (
        <p style={{ fontSize: '0.8125rem', color: '#0043ce', background: '#edf5ff', padding: '0.5rem 0.75rem', borderRadius: 4 }}>
          This will update <strong>{affectedCount} record{affectedCount !== 1 ? 's' : ''}</strong> from{' '}
          <strong>{shortOsLabel(fromOs)}</strong> → <strong>{shortOsLabel(toOs)}</strong>.
        </p>
      )}
      {fromOs === toOs && (
        <p style={{ fontSize: '0.8125rem', color: '#6f6f6f' }}>Source and target OS are the same — nothing to change.</p>
      )}
    </Modal>
  );
}
