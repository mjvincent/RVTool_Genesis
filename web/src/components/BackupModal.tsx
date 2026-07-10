import { useState } from 'react';
import { Modal, Checkbox, InlineLoading } from '@carbon/react';
import { api, Project, downloadFile } from '../api/client';

interface BackupModalProps {
  mode: 'project' | 'all';
  project?: Project;
  onClose: () => void;
}

export default function BackupModal({ mode, project, onClose }: BackupModalProps) {
  const [includeFile, setIncludeFile] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const heading =
    mode === 'project' ? `Backup "${project?.name}"` : 'Backup all projects';

  async function handleDownload() {
    setLoading(true);
    setError('');
    try {
      let response: Response;
      let filename: string;
      const date = new Date().toISOString().slice(0, 10).replace(/-/g, '');

      if (mode === 'project' && project) {
        response = await api.backup.downloadProject(project.id, includeFile);
        const slug = project.name.toLowerCase().replace(/\s+/g, '-').slice(0, 40);
        filename = `rvtg-${slug}-${date}.json`;
      } else {
        response = await api.backup.downloadAll(includeFile);
        filename = `rvtoolgenesis-backup-${date}.zip`;
      }

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`);
      }

      // Use server's Content-Disposition filename if present
      const disposition = response.headers.get('Content-Disposition') || '';
      const serverFilename = disposition.match(/filename="([^"]+)"/)?.[1];
      await downloadFile(response, serverFilename ?? filename);
      onClose();
    } catch (err: any) {
      setError(err.message ?? 'Download failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      open
      modalHeading={heading}
      primaryButtonText={loading ? '' : 'Download backup'}
      secondaryButtonText="Cancel"
      onRequestSubmit={handleDownload}
      onRequestClose={onClose}
      primaryButtonDisabled={loading}
      size="sm"
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {mode === 'project' ? (
          <p style={{ color: '#525252', lineHeight: 1.6, margin: 0 }}>
            Downloads a <strong>.json</strong> bundle containing all normalized
            server records and AI assumptions for this project. Generated exports
            are not included — they can be regenerated from the Export page.
          </p>
        ) : (
          <p style={{ color: '#525252', lineHeight: 1.6, margin: 0 }}>
            Downloads a <strong>.zip</strong> archive containing one JSON bundle
            per project. Use this for off-machine backups or sharing with colleagues.
          </p>
        )}

        <Checkbox
          id="backup-include-file"
          labelText="Include original spreadsheet file (larger download)"
          checked={includeFile}
          onChange={(_: any, { checked }: { checked: boolean }) => setIncludeFile(checked)}
        />

        <p style={{ color: '#6f6f6f', fontSize: '0.75rem', lineHeight: 1.5, margin: 0 }}>
          The original spreadsheet file can be large. Leave unchecked unless you
          need the source file archived alongside the normalized data.
        </p>

        {error && (
          <p style={{ color: '#da1e28', fontSize: '0.875rem', margin: 0 }}>{error}</p>
        )}

        {loading && (
          <InlineLoading description="Preparing download…" />
        )}
      </div>
    </Modal>
  );
}
