import { Button, InlineNotification } from '@carbon/react';
import { ChevronRight, Renew } from '@carbon/icons-react';

interface MappingPreviewProps {
  fileName: string;
  rowCount: number;
  columns: string[];
  sampleRows: Record<string, unknown>[];
  onConfirm: () => void;
  onReupload: () => void;
}

export default function MappingPreview({
  fileName,
  rowCount,
  columns,
  sampleRows,
  onConfirm,
  onReupload,
}: MappingPreviewProps) {
  const displayCols = columns.slice(0, 12); // cap display at 12 cols to avoid overflow
  const hidden = columns.length - displayCols.length;

  // No records detected at all — likely wrong file or empty sheet
  if (rowCount === 0) {
    return (
      <div style={{ marginTop: '1rem' }}>
        <InlineNotification
          kind="warning"
          title="No records detected"
          subtitle="The file was parsed but no data rows were found. Check that the file contains a header row and data, then try re-uploading."
          lowContrast
          style={{ marginBottom: '1rem' }}
        />
        <Button kind="ghost" renderIcon={Renew} onClick={onReupload}>
          Re-upload different file
        </Button>
      </div>
    );
  }

  // Rows detected but no sample data available (edge case — all rows cleaned away)
  if (sampleRows.length === 0) {
    return (
      <div style={{ marginTop: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.75rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.9375rem', fontWeight: 600, color: '#161616' }}>{fileName}</span>
          <span style={{ fontSize: '0.8125rem', color: '#525252' }}>{rowCount} server record{rowCount !== 1 ? 's' : ''} detected</span>
        </div>
        <InlineNotification
          kind="info"
          title="Preview unavailable"
          subtitle="Records were detected but no sample data could be shown. You can still proceed to normalize."
          lowContrast
          style={{ marginBottom: '1rem' }}
        />
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <Button renderIcon={ChevronRight} onClick={onConfirm}>
            Looks good — proceed to normalize
          </Button>
          <Button kind="ghost" renderIcon={Renew} onClick={onReupload}>
            Re-upload different file
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ marginTop: '1rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.75rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.9375rem', fontWeight: 600, color: '#161616' }}>
          {fileName}
        </span>
        <span style={{ fontSize: '0.8125rem', color: '#525252' }}>
          {rowCount} server record{rowCount !== 1 ? 's' : ''} detected
          {hidden > 0 ? ` · ${columns.length} columns (showing first 12)` : ` · ${columns.length} column${columns.length !== 1 ? 's' : ''}`}
        </span>
      </div>

      {/* Sample rows table */}
      <div style={{ overflowX: 'auto', border: '1px solid #e0e0e0', borderRadius: 2, marginBottom: '1rem' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
          <thead>
            <tr style={{ background: '#f4f4f4' }}>
              {displayCols.map(col => (
                <th
                  key={col}
                  title={col}
                  style={{
                    padding: '0.5rem 0.75rem',
                    textAlign: 'left',
                    fontWeight: 600,
                    color: '#161616',
                    borderBottom: '1px solid #e0e0e0',
                    whiteSpace: 'nowrap',
                    maxWidth: 160,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {col}
                </th>
              ))}
              {hidden > 0 && (
                <th style={{ padding: '0.5rem 0.75rem', color: '#6f6f6f', fontWeight: 400, borderBottom: '1px solid #e0e0e0', whiteSpace: 'nowrap' }}>
                  +{hidden} more…
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {sampleRows.map((row, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #e0e0e0', background: i % 2 === 0 ? '#fff' : '#f9f9f9' }}>
                {displayCols.map(col => {
                  const val = row[col];
                  const display = val === null || val === undefined ? '' : String(val);
                  return (
                    <td
                      key={col}
                      title={display}
                      style={{
                        padding: '0.4rem 0.75rem',
                        color: display ? '#161616' : '#a8a8a8',
                        whiteSpace: 'nowrap',
                        maxWidth: 160,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {display || '—'}
                    </td>
                  );
                })}
                {hidden > 0 && <td style={{ padding: '0.4rem 0.75rem', color: '#a8a8a8' }}>…</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p style={{ fontSize: '0.8125rem', color: '#525252', margin: '0 0 1rem' }}>
        Verify the column names above match your source file, then proceed to normalize.
      </p>

      {/* Actions */}
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
        <Button renderIcon={ChevronRight} onClick={onConfirm}>
          Looks good — proceed to normalize
        </Button>
        <Button kind="ghost" renderIcon={Renew} onClick={onReupload}>
          Re-upload different file
        </Button>
      </div>
    </div>
  );
}
