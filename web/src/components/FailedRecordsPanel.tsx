import { useState } from 'react';
import { Button, InlineLoading } from '@carbon/react';
import { Renew, WarningAlt, ChevronDown, ChevronUp, Edit } from '@carbon/icons-react';
import { api, ServerRecord } from '../api/client';
import EditRecordModal from './EditRecordModal';

interface Props {
  projectId: string;
  records: ServerRecord[];                                       // only failed records
  onRecordFixed: (recordId: string, updated: ServerRecord) => void;
  onRecordStillFailed: (recordId: string, errorMsg: string) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

/**
 * Translate a raw Python/server exception message into plain English.
 * The backend stores str(exc) which can contain Python class names and
 * internal details meaningless to a cloud seller.
 */
function translateError(msg: string): { text: string; isTranslated: boolean } {
  const m = msg.toLowerCase();

  if (m.includes("object has no attribute 'get'") || m.includes("'str' object")) {
    return {
      text: "The AI returned data in an unexpected format. Click Retry — if it continues to fail, use Edit to enter the values manually.",
      isTranslated: true,
    };
  }
  if (m.includes('jsondecode') || m.includes('json.decoder') || m.includes('expecting value')) {
    return {
      text: "The AI response could not be parsed as valid data. Click Retry — the AI may succeed on a second attempt.",
      isTranslated: true,
    };
  }
  if (m.includes('timeout') || m.includes('connecterror') || m.includes('connection refused') || m.includes('connectionrefused')) {
    return {
      text: "Could not reach the AI service. Make sure Ollama is running, then click Retry.",
      isTranslated: true,
    };
  }
  if (m.includes('keyerror') || m.includes("key error")) {
    return {
      text: "A required field was missing from the AI response. Click Retry or use Edit to enter values manually.",
      isTranslated: true,
    };
  }
  if (m.includes('valueerror') || m.includes('typeerror')) {
    return {
      text: "The AI returned a value in an unrecognised format. Click Retry or use Edit to enter values manually.",
      isTranslated: true,
    };
  }
  if (m.includes('index out of range') || m.includes('indexerror')) {
    return {
      text: "The AI response was incomplete or truncated. Click Retry — the AI may produce a complete response on a second attempt.",
      isTranslated: true,
    };
  }
  // Unknown — show as plain text (not monospace) so it reads as a sentence
  return { text: msg, isTranslated: false };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function FailedRecordsPanel({ projectId, records, onRecordFixed, onRecordStillFailed }: Props) {
  const [retrying, setRetrying]       = useState<Set<string>>(new Set());
  const [retryErrors, setRetryErrors]   = useState<Record<string, string>>({});
  const [expanded, setExpanded]       = useState<Set<string>>(new Set()); // expanded error text
  const [collapsed, setCollapsed]     = useState(records.length > 3);
  const [retryingAll, setRetryingAll] = useState(false);
  const [editTarget, setEditTarget]   = useState<ServerRecord | null>(null);

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
        const data = await api.uploads.getRecords(projectId);
        const updated = data.records.find(r => r.id === recordId);
        if (updated) onRecordFixed(recordId, updated);
      }
    } catch {
      const msg = 'Retry request failed — check that the API is running.';
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

  function handleEditSaved(updated: ServerRecord) {
    setEditTarget(null);
    onRecordFixed(updated.id, updated);
  }

  const count = records.length;

  return (
    <>
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
            Click to expand — see error details, retry options, and manual edit
          </div>
        )}

        {/* Rows */}
        {!collapsed && (
          <div>
            {records.map((r, idx) => {
              const name       = getDisplayName(r);
              const rowRef     = getRowNumber(r);
              const rawErr     = retryErrors[r.id] ?? r.error_message ?? 'Unknown error';
              const { text: errText, isTranslated } = translateError(rawErr);
              const isRetrying = retrying.has(r.id);
              const isExpanded = expanded.has(r.id);
              // Only truncate un-translated messages (translated ones are already short)
              const truncated  = !isTranslated && rawErr.length > 140 && !isExpanded;

              return (
                <div
                  key={r.id}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: '1rem',
                    padding: '0.875rem 1rem',
                    borderBottom: idx < records.length - 1 ? '1px solid #ffe0e0' : 'none',
                    flexWrap: 'wrap',
                  }}
                >
                  {/* Name + row ref */}
                  <div style={{ flex: '0 0 200px', minWidth: 160 }}>
                    <p style={{ margin: 0, fontWeight: 600, fontSize: '0.875rem', color: '#161616' }}>
                      {name}
                    </p>
                    {rowRef ? (
                      <p style={{ margin: '0.1rem 0 0', fontSize: '0.75rem', color: '#6f6f6f' }}>{rowRef}</p>
                    ) : (
                      <p style={{ margin: '0.1rem 0 0', fontSize: '0.75rem', color: '#a8a8a8', fontStyle: 'italic' }}>
                        Row reference unavailable — re-upload to get row numbers
                      </p>
                    )}
                  </div>

                  {/* Error message */}
                  <div style={{ flex: 1, minWidth: 240 }}>
                    <p style={{
                      margin: 0,
                      fontSize: '0.8125rem',
                      color: '#da1e28',
                      // Monospace only for raw un-translated technical errors
                      fontFamily: isTranslated ? 'inherit' : 'monospace',
                      wordBreak: 'break-word',
                      lineHeight: 1.5,
                    }}>
                      {truncated ? rawErr.slice(0, 140) + '…' : errText}
                    </p>
                    {!isTranslated && rawErr.length > 140 && (
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

                  {/* Actions: Retry + Edit manually */}
                  <div style={{ flexShrink: 0, display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                    {isRetrying ? (
                      <InlineLoading description="Retrying…" style={{ minWidth: 100 }} />
                    ) : (
                      <>
                        <Button
                          kind="danger--ghost"
                          size="sm"
                          renderIcon={Renew}
                          onClick={() => handleRetry(r.id)}
                          disabled={retryingAll}
                        >
                          Retry
                        </Button>
                        <Button
                          kind="ghost"
                          size="sm"
                          renderIcon={Edit}
                          onClick={() => setEditTarget(r)}
                          disabled={retryingAll}
                        >
                          Edit manually
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Edit modal — shown when user clicks "Edit manually" */}
      {editTarget && (
        <EditRecordModal
          open
          projectId={projectId}
          record={editTarget}
          prefillFromRaw
          onClose={() => setEditTarget(null)}
          onSaved={handleEditSaved}
        />
      )}
    </>
  );
}
