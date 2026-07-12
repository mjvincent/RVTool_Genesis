import { useState } from 'react';
import { Button, InlineLoading } from '@carbon/react';
import { Renew, WarningAlt, ChevronDown, ChevronUp } from '@carbon/icons-react';
import { api, ServerRecord } from '../api/client';

interface Props {
  projectId: string;
  records: ServerRecord[];                                       // only failed records
  onRecordFixed: (recordId: string, updated: ServerRecord) => void;
  onRecordStillFailed: (recordId: string, errorMsg: string) => void;
}

function getDisplayName(r: ServerRecord): string {
  return (
    r.normalized_data?.vinfo?.vm_name
    ?? r.raw_data?.name
    ?? r.raw_data?.['Server Name']
    ?? r.raw_data?.['VM']
    ?? r.raw_data?.vm_name
    ?? r.raw_data?.hostname
    ?? 'Unknown server'
  );
}

function getRowNumber(r: ServerRecord): string {
  const n = r.raw_data?._row_number;
  return n != null ? `Row ${n} in your spreadsheet` : '';
}

export default function FailedRecordsPanel({ projectId, records, onRecordFixed, onRecordStillFailed }: Props) {
  const [retrying, setRetrying]     = useState<Set<string>>(new Set());
  const [retryErrors, setRetryErrors] = useState<Record<string, string>>({});
  const [expanded, setExpanded]     = useState<Set<string>>(new Set()); // expanded error text
  const [collapsed, setCollapsed]   = useState(records.length > 3);    // panel collapsed

  const [retryingAll, setRetryingAll] = useState(false);

  async function handleRetry(recordId: string) {
    setRetrying(prev => new Set(prev).add(recordId));
    setRetryErrors(prev => { const n = { ...prev }; delete n[recordId]; return n; });
    try {
      const result = await api.processing.retryRecord(projectId, recordId);
      if (result.processing_status === 'error') {
        const msg = result.error_message ?? 'Processing failed';
        setRetryErrors(prev => ({ ...prev, [recordId]: msg }));
        onRecordStillFailed(recordId, msg);
      } else {
        // Fetch updated record and notify parent
        const data = await api.uploads.getRecords(projectId);
        const updated = data.records.find(r => r.id === recordId);
        if (updated) onRecordFixed(recordId, updated);
      }
    } catch {
      const msg = 'Retry request failed';
      setRetryErrors(prev => ({ ...prev, [recordId]: msg }));
      onRecordStillFailed(recordId, msg);
    } finally {
      setRetrying(prev => { const n = new Set(prev); n.delete(recordId); return n; });
    }
  }

  async function handleRetryAll() {
    setRetryingAll(true);
    for (const r of records) {
      if (!retrying.has(r.id)) await handleRetry(r.id);
    }
    setRetryingAll(false);
  }

  function toggleExpand(id: string) {
    setExpanded(prev => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }

  const count = records.length;

  return (
    <div style={{
      background: '#fff8f8',
      border: '1px solid #ffb3b8',
      borderLeft: '4px solid #da1e28',
      borderRadius: 4,
      marginBottom: '1.5rem',
    }}>
      {/* Panel header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.75rem',
        padding: '0.75rem 1rem', borderBottom: collapsed ? 'none' : '1px solid #ffb3b8',
      }}>
        <WarningAlt size={20} style={{ color: '#da1e28', flexShrink: 0 }} />
        <span style={{ fontWeight: 600, fontSize: '0.9375rem', color: '#da1e28', flex: 1 }}>
          {count} record{count !== 1 ? 's' : ''} failed normalization
        </span>
        {!collapsed && (
          <Button
            kind="ghost"
            size="sm"
            renderIcon={retryingAll ? undefined : Renew}
            onClick={handleRetryAll}
            disabled={retryingAll}
            style={{ color: '#da1e28', minWidth: 120 }}
          >
            {retryingAll ? <InlineLoading description="Retrying all…" /> : 'Retry all failed'}
          </Button>
        )}
        <Button
          kind="ghost"
          size="sm"
          renderIcon={collapsed ? ChevronDown : ChevronUp}
          onClick={() => setCollapsed(c => !c)}
          iconDescription={collapsed ? 'Expand' : 'Collapse'}
          hasIconOnly
        />
      </div>

      {/* Collapsed hint */}
      {collapsed && (
        <div
          style={{ padding: '0.5rem 1rem', fontSize: '0.8125rem', color: '#6f6f6f', cursor: 'pointer' }}
          onClick={() => setCollapsed(false)}
        >
          Click to expand and see error details + retry options
        </div>
      )}

      {/* Rows */}
      {!collapsed && (
        <div>
          {records.map((r, idx) => {
            const name     = getDisplayName(r);
            const rowRef   = getRowNumber(r);
            const errMsg   = retryErrors[r.id] ?? r.error_message ?? 'Unknown error';
            const isRetrying = retrying.has(r.id);
            const isExpanded = expanded.has(r.id);
            const truncated  = errMsg.length > 120 && !isExpanded;

            return (
              <div
                key={r.id}
                style={{
                  display: 'flex', alignItems: 'flex-start', gap: '1rem',
                  padding: '0.75rem 1rem',
                  borderBottom: idx < records.length - 1 ? '1px solid #ffe0e0' : 'none',
                  flexWrap: 'wrap',
                }}
              >
                {/* Name + row ref */}
                <div style={{ flex: '0 0 220px', minWidth: 160 }}>
                  <p style={{ margin: 0, fontWeight: 600, fontSize: '0.875rem', color: '#161616' }}>
                    {name}
                  </p>
                  {rowRef && (
                    <p style={{ margin: 0, fontSize: '0.75rem', color: '#6f6f6f' }}>{rowRef}</p>
                  )}
                </div>

                {/* Error message */}
                <div style={{ flex: 1, minWidth: 200 }}>
                  <p style={{
                    margin: 0, fontSize: '0.8125rem', color: '#da1e28',
                    fontFamily: 'monospace', wordBreak: 'break-word',
                  }}>
                    {truncated ? errMsg.slice(0, 120) + '…' : errMsg}
                  </p>
                  {errMsg.length > 120 && (
                    <button
                      onClick={() => toggleExpand(r.id)}
                      style={{
                        background: 'none', border: 'none', padding: 0,
                        fontSize: '0.75rem', color: '#0f62fe', cursor: 'pointer', marginTop: '0.25rem',
                      }}
                    >
                      {isExpanded ? 'Show less' : 'Show full error'}
                    </button>
                  )}
                </div>

                {/* Retry button */}
                <div style={{ flexShrink: 0 }}>
                  {isRetrying ? (
                    <InlineLoading description="Retrying…" style={{ minWidth: 100 }} />
                  ) : (
                    <Button
                      kind="danger--ghost"
                      size="sm"
                      renderIcon={Renew}
                      onClick={() => handleRetry(r.id)}
                    >
                      Retry
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
