import { useState, useEffect, useCallback } from 'react';
import {
  DataTable, DataTableSkeleton, Table, TableHead, TableRow, TableHeader,
  TableBody, TableCell, TableContainer, TableToolbar, TableToolbarContent,
  TableToolbarSearch, TableExpandRow, TableExpandedRow, TableExpandHeader,
  Tag, Pagination, Button, InlineLoading, Checkbox, TextInput,
} from '@carbon/react';
import { Renew, WarningAlt, Edit } from '@carbon/icons-react';
import { api, ServerRecord, Assumption } from '../api/client';
import EditRecordModal from './EditRecordModal';

export type FilterPreset = 'attention' | 'errors' | 'excluded' | 'all';

interface Props {
  projectId: string;
  onViewAssumptions: (vmName: string, assumptions: Assumption[]) => void;
  filterPreset?: FilterPreset;
}

const headers = [
  { key: 'vm_name',     header: 'Server Name' },
  { key: 'server_type', header: 'Type' },
  { key: 'cpus',        header: 'vCPUs' },
  { key: 'memory_gb',   header: 'RAM (GB)' },
  { key: 'storage_gb',  header: 'Storage (GB)' },
  { key: 'os',          header: 'Operating System' },
  { key: 'exclude_col', header: 'Exclude' },
  { key: 'status_col',  header: 'AI Decisions' },
];

function safeGet(obj: any, ...paths: string[]): any {
  for (const path of paths) {
    const val = path.split('.').reduce((cur: any, k) => cur?.[k], obj);
    if (val !== undefined && val !== null) return val;
  }
  return null;
}

function mbToGb(mb: any): string {
  const n = Number(mb);
  if (!mb || isNaN(n) || n === 0) return '—';
  return n >= 1024 ? (n / 1024).toFixed(0) : (n / 1024).toFixed(1);
}

function typeTag(serverType: string | null | undefined) {
  if (!serverType || serverType === 'vm')
    return <Tag type="blue" size="sm">Virtual</Tag>;
  if (serverType === 'bare_metal')
    return <Tag type="teal" size="sm">Bare Metal</Tag>;
  if (serverType === 'powervs')
    return <Tag type="purple" size="sm">PowerVS</Tag>;
  return <Tag type="gray" size="sm">{serverType}</Tag>;
}

function isMissingCpuOrRam(r: ServerRecord): boolean {
  const nd = r.normalized_data ?? {};
  const cpus  = safeGet(nd, 'vinfo.cpus', 'vinfo.cpu_count', 'vinfo.num_cpus');
  const memMb = safeGet(nd, 'vinfo.memory_mb');
  const cpuMissing = cpus == null || cpus === '' || Number(cpus) === 0;
  const ramMissing = memMb == null || memMb === '' || Number(memMb) === 0;
  return (cpuMissing || ramMissing) && r.processing_status !== 'error' && r.status !== 'error';
}

function isMissingKeyField(r: ServerRecord): boolean {
  const nd = r.normalized_data ?? {};
  const cpuCount = safeGet(nd, 'vinfo.cpus', 'vinfo.cpu_count', 'vinfo.num_cpus');
  const ramMb    = safeGet(nd, 'vinfo.memory_mb');
  const osName   = safeGet(nd, 'vinfo.os_config');
  return (
    (cpuCount == null || cpuCount === '' || Number(cpuCount) === 0) ||
    (ramMb    == null || ramMb    === '' || Number(ramMb)    === 0) ||
    (osName   == null || osName   === '')
  );
}

function hasFallbackOrLowConfidence(r: ServerRecord): boolean {
  const assumptions = r.assumptions ?? [];
  return assumptions.some(
    a => a.confidence === 'low' ||
         a.reasoning?.includes('Python synthesizer') ||
         a.reasoning?.toLowerCase().includes('fallback')
  );
}

export default function RecordsTable({ projectId, onViewAssumptions, filterPreset = 'all' }: Props) {
  const [records, setRecords] = useState<ServerRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [filterText, setFilterText] = useState('');
  const [retrying, setRetrying] = useState<Set<string>>(new Set());
  const [retryErrors, setRetryErrors] = useState<Record<string, string>>({});
  const [editTarget, setEditTarget] = useState<ServerRecord | null>(null);
  // exclusion reason drafts — keyed by record id
  const [reasonDraft, setReasonDraft] = useState<Record<string, string>>({});
  const [excludeLoading, setExcludeLoading] = useState<Set<string>>(new Set());

  const loadRecords = useCallback(async () => {
    try {
      const data = await api.uploads.getRecords(projectId);
      setRecords(data.records ?? []);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { loadRecords(); }, [loadRecords]);

  async function handleRetry(recordId: string) {
    setRetrying(prev => new Set(prev).add(recordId));
    setRetryErrors(prev => { const n = { ...prev }; delete n[recordId]; return n; });
    try {
      const result = await api.processing.retryRecord(projectId, recordId);
      if (result.processing_status === 'error') {
        setRetryErrors(prev => ({ ...prev, [recordId]: result.error_message ?? 'Processing failed' }));
      }
      await loadRecords();
    } catch {
      setRetryErrors(prev => ({ ...prev, [recordId]: 'Retry request failed' }));
    } finally {
      setRetrying(prev => { const n = new Set(prev); n.delete(recordId); return n; });
    }
  }

  async function handleExclude(recordId: string, isExcluded: boolean, reason?: string | null) {
    setExcludeLoading(prev => new Set(prev).add(recordId));
    try {
      const updated = await api.uploads.excludeRecord(projectId, recordId, isExcluded, reason);
      setRecords(prev => prev.map(r => r.id === updated.id ? updated : r));
    } catch (e) {
      console.error('Failed to update exclusion', e);
    } finally {
      setExcludeLoading(prev => { const n = new Set(prev); n.delete(recordId); return n; });
    }
  }

  async function handleReasonSave(recordId: string, isExcluded: boolean) {
    const reason = reasonDraft[recordId] ?? '';
    await handleExclude(recordId, isExcluded, reason || null);
  }

  // Show both complete AND error records
  const visibleRecords = records.filter(
    r => r.processing_status === 'complete' || r.processing_status === 'error'
      || r.status === 'complete' || r.status === 'error'
  );

  // Apply filter preset before the existing search filter.
  const presetFiltered: ServerRecord[] = (() => {
    if (filterPreset === 'errors') {
      return visibleRecords.filter(
        r => r.processing_status === 'error' || (r as any).status === 'error'
      );
    }
    if (filterPreset === 'excluded') {
      return visibleRecords.filter(r => r.is_excluded);
    }
    if (filterPreset === 'attention') {
      const errorRecs   = visibleRecords.filter(r => r.processing_status === 'error' || (r as any).status === 'error');
      const errorIds    = new Set(errorRecs.map(r => r.id));
      const lowConfRecs = visibleRecords.filter(r => !errorIds.has(r.id) && !r.is_excluded && hasFallbackOrLowConfidence(r));
      const lowConfIds  = new Set(lowConfRecs.map(r => r.id));
      const missingRecs = visibleRecords.filter(r => !errorIds.has(r.id) && !lowConfIds.has(r.id) && !r.is_excluded && isMissingKeyField(r));
      return [...errorRecs, ...lowConfRecs, ...missingRecs];
    }
    // 'all' — no preset filter
    return visibleRecords;
  })();

  // Sort: servers missing CPU or RAM data float to top for human intervention.
  // Within each group, preserve original order.
  // (Skip default sort when a preset with its own ordering is active.)
  const sortedVisible = filterPreset === 'attention'
    ? presetFiltered
    : [...presetFiltered].sort((a, b) => {
        const missingA = isMissingCpuOrRam(a);
        const missingB = isMissingCpuOrRam(b);
        if (missingA && !missingB) return -1;
        if (!missingA && missingB) return 1;
        return 0;
      });

  const filtered = filterText
    ? sortedVisible.filter(r => {
        const name = safeGet(r.normalized_data, 'vinfo.vm_name')
          ?? safeGet(r.raw_data, 'name', 'Server Name', 'VM', 'vm_name', 'hostname') ?? '';
        return String(name).toLowerCase().includes(filterText.toLowerCase());
      })
    : sortedVisible;

  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);

  // Build a stable lookup map from ALL visible records so that the Carbon DataTable
  // render callback (which may lag one render behind the paged slice) can always
  // resolve a row.id → ServerRecord without returning undefined.  This fixes the
  // blank-second-page bug: paged.find(r => r.id === row.id) returns undefined when
  // Carbon's internal tableRows still references the previous page's IDs during the
  // transition render, causing isMissingCpuOrRam(undefined) to crash the render.
  const recordById = new Map<string, ServerRecord>(
    visibleRecords.map(r => [r.id, r])
  );

  const rows = paged.map(r => {
    const isFailed = r.processing_status === 'error' || r.status === 'error';
    const nd = r.normalized_data ?? {};
    const rawName = safeGet(r.raw_data, 'name', 'Server Name', 'VM', 'vm_name', 'hostname') ?? r.id;
    const vmName  = safeGet(nd, 'vinfo.vm_name') ?? rawName;
    const type    = r.server_type ?? safeGet(nd, 'server_type') ?? 'vm';
    const cpus    = safeGet(nd, 'vinfo.cpus', 'vinfo.cpu_count');
    const memMb   = safeGet(nd, 'vinfo.memory_mb');
    const diskMb  = safeGet(nd, 'vinfo.provisioned_mb');
    const os      = safeGet(nd, 'vinfo.os_config') ?? '';
    const asmCount = (r.assumptions ?? []).length;

    // Count missing critical fields for non-failed complete records
    const missingCount = isFailed ? 0 : [
      safeGet(nd, 'vinfo.vm_name'),
      safeGet(nd, 'vinfo.cpus'),
      safeGet(nd, 'vinfo.memory_mb'),
      safeGet(nd, 'vinfo.provisioned_mb'),
      safeGet(nd, 'vinfo.os_config'),
    ].filter(v => v == null || v === '' || v === 0).length;

    return {
      id: r.id,
      vm_name:        vmName,
      server_type:    isFailed ? 'error' : type,
      cpus:           cpus != null ? String(cpus) : '—',
      memory_gb:      mbToGb(memMb),
      storage_gb:     mbToGb(diskMb),
      os:             os ? String(os).replace(/ \(64-bit\)/i, '') : '—',
      exclude_col:    r.is_excluded ? 'excluded' : 'active',
      status_col:     isFailed ? 'error' : asmCount,
      _record:        r,
      _isFailed:      isFailed,
      _missingCount:  missingCount,
    };
  });

  if (loading) return <DataTableSkeleton columnCount={8} rowCount={8} />;
  if (visibleRecords.length === 0) return null;

  const powervsCount = visibleRecords.filter(r => (r.server_type ?? safeGet(r.normalized_data, 'server_type')) === 'powervs').length;
  const excludedCount = visibleRecords.filter(r => r.is_excluded).length;
  const missingDataCount = visibleRecords.filter(r => isMissingCpuOrRam(r)).length;

  return (
    <>
      {/* Warning banner — servers missing CPU or RAM (pinned above table) */}
      {missingDataCount > 0 && (
        <div style={{
          background: '#fff3cd', border: '1px solid #ffc107', borderRadius: 4,
          padding: '0.6rem 1rem', marginBottom: '0.75rem',
          display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8125rem',
        }}>
          <WarningAlt size={16} style={{ color: '#b45309', flexShrink: 0 }} />
          <span>
            <strong>{missingDataCount} server{missingDataCount !== 1 ? 's' : ''}</strong> {missingDataCount === 1 ? 'is' : 'are'} missing CPU or RAM data and {missingDataCount === 1 ? 'has' : 'have'} been moved to the top of this list.
            Review and edit or exclude {missingDataCount === 1 ? 'it' : 'them'} before exporting.
          </span>
        </div>
      )}

      {/* Summary bar — PowerVS + Excluded counts */}
      {(powervsCount > 0 || excludedCount > 0) && (
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
          {powervsCount > 0 && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.875rem', color: '#6929c4' }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#6929c4', display: 'inline-block' }} />
              <strong>{powervsCount}</strong> PowerVS (AIX/IBM i) — will export separately
            </span>
          )}
          {excludedCount > 0 && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.875rem', color: '#6f6f6f' }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#8d8d8d', display: 'inline-block' }} />
              <strong>{excludedCount}</strong> excluded from exports
            </span>
          )}
        </div>
      )}

      <DataTable rows={rows} headers={headers} isSortable>
        {({ rows: tableRows, headers: tableHeaders, getTableProps, getHeaderProps, getRowProps, getToolbarProps, onInputChange }: any) => (
          <TableContainer>
            <TableToolbar {...getToolbarProps()}>
              <TableToolbarContent>
                <TableToolbarSearch
                  placeholder="Find a server…"
                  onChange={(e: any) => {
                    setFilterText(e?.target?.value ?? '');
                    onInputChange(e);
                    setPage(1);
                  }}
                />
              </TableToolbarContent>
            </TableToolbar>

            <Table {...getTableProps()} size="md">
              <TableHead>
                <TableRow>
                  <TableExpandHeader />
                  {tableHeaders.map((h: any) => (
                    <TableHeader {...getHeaderProps({ header: h })} key={h.key}>
                      {h.header}
                    </TableHeader>
                  ))}
                </TableRow>
              </TableHead>

              <TableBody>
                {tableRows.map((row: any) => {
                  const original = recordById.get(row.id) ?? paged.find(r => r.id === row.id);
                  if (!original) return null; // guard against stale Carbon render during page transition
                  const nd = original?.normalized_data ?? {};
                  const isFailed = (original?.processing_status === 'error' || original?.status === 'error');
                  const isRetrying = retrying.has(row.id);
                  const retryError = retryErrors[row.id];
                  const isExcluded = original?.is_excluded ?? false;
                  const currentReason = reasonDraft[row.id] ?? (original?.exclusion_reason ?? '');
                  const serverType = original?.server_type ?? safeGet(nd, 'server_type') ?? 'vm';
                  const isExcluding = excludeLoading.has(row.id);

                  const rowStyle: React.CSSProperties = isExcluded
                    ? { opacity: 0.5 }
                    : undefined as any;

                  return (
                    <>
                      <TableExpandRow
                         {...getRowProps({ row })}
                         key={row.id}
                         style={{
                           ...(isFailed ? { background: '#fff8f8' } : {}),
                           ...(isMissingCpuOrRam(original) ? { background: '#fffbe6', borderLeft: '3px solid #ffc107' } : {}),
                           ...rowStyle,
                         }}
                       >
                         {row.cells.map((cell: any) => {
                           // ── Type column ──────────────────────────────────
                          if (cell.info.header === 'server_type') {
                            if (cell.value === 'error') {
                              return (
                                <TableCell key={cell.id}>
                                  <Tag type="red" size="sm">Failed</Tag>
                                </TableCell>
                              );
                            }
                            return (
                              <TableCell key={cell.id}>
                                {typeTag(serverType)}
                              </TableCell>
                            );
                          }

                          // ── Exclude column ───────────────────────────────
                          if (cell.info.header === 'exclude_col') {
                            return (
                              <TableCell key={cell.id} style={{ verticalAlign: 'middle' }}>
                                {isExcluding ? (
                                  <InlineLoading style={{ minHeight: 'unset', height: 20 }} />
                                ) : (
                                  <Checkbox
                                    id={`exclude-${row.id}`}
                                    labelText=""
                                    hideLabel
                                    aria-label={`Exclude ${row.cells.find((c: any) => c.info.header === 'vm_name')?.value ?? 'this server'} from exports`}
                                    checked={isExcluded}
                                    onChange={(_: any, { checked }: { checked: boolean }) => {
                                      handleExclude(row.id, checked, checked ? (currentReason || null) : null);
                                    }}
                                  />
                                )}
                              </TableCell>
                            );
                          }

                          // ── Server Name column ───────────────────────────
                         if (cell.info.header === 'vm_name') {
                           const missingCpu = !safeGet(original?.normalized_data ?? {}, 'vinfo.cpus', 'vinfo.cpu_count', 'vinfo.num_cpus');
                           const missingRam = !safeGet(original?.normalized_data ?? {}, 'vinfo.memory_mb');
                           return (
                             <TableCell key={cell.id}>
                               <span
                                 className="vm-name-cell"
                                 style={isExcluded ? { textDecoration: 'line-through', color: '#8d8d8d' } : undefined}
                               >
                                 {cell.value}
                               </span>
                               {missingCpu && !isFailed && (
                                 <Tag type="red" size="sm" style={{ marginLeft: '0.4rem' }}>⚠ Missing CPU</Tag>
                               )}
                               {missingRam && !isFailed && (
                                 <Tag type="red" size="sm" style={{ marginLeft: '0.25rem' }}>⚠ Missing RAM</Tag>
                               )}
                             </TableCell>
                           );
                         }

                          // ── AI Decisions column ──────────────────────────
                          if (cell.info.header === 'status_col') {
                            const missingCount = (row as any)._missingCount ?? 0;
                            if (cell.value === 'error') {
                              return (
                                <TableCell key={cell.id}>
                                  <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
                                    {isRetrying ? (
                                      <InlineLoading description="Retrying…" />
                                    ) : (
                                      <>
                                        <Button kind="ghost" size="sm" renderIcon={Renew} onClick={() => handleRetry(row.id)}>
                                          Retry
                                        </Button>
                                        <Button kind="ghost" size="sm" renderIcon={Edit} onClick={() => setEditTarget(original)}>
                                          Edit
                                        </Button>
                                      </>
                                    )}
                                  </div>
                                </TableCell>
                              );
                            }
                            // Amber "N missing" badge for incomplete normalized records
                            const missingBadge = missingCount > 0 ? (
                              <span style={{
                                display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                fontSize: '0.75rem', color: '#8a3800',
                                background: '#fff8e1', border: '1px solid #f1c21b',
                                borderRadius: 12, padding: '0.1rem 0.5rem', marginRight: '0.4rem',
                              }}>
                                ⚠ {missingCount} missing
                              </span>
                            ) : null;

                            const count = cell.value as number;
                            if (count === 0) return (
                              <TableCell key={cell.id}>
                                {missingBadge ?? <span style={{ color: '#8d8d8d' }}>—</span>}
                              </TableCell>
                            );
                            return (
                              <TableCell key={cell.id}>
                                {missingBadge}
                                <button
                                  className="assumption-badge"
                                  onClick={() => onViewAssumptions(
                                    String(row.cells.find((c: any) => c.info.header === 'vm_name')?.value ?? ''),
                                    original?.assumptions ?? []
                                  )}
                                >
                                  <span className="assumption-badge-dot" />
                                  {count} decision{count !== 1 ? 's' : ''}
                                </button>
                              </TableCell>
                            );
                          }

                          return <TableCell key={cell.id}>{cell.value}</TableCell>;
                        })}
                      </TableExpandRow>

                      {/* Expanded detail */}
                      <TableExpandedRow colSpan={tableHeaders.length + 1} key={`${row.id}-exp`}>
                        {isFailed ? (
                          <div style={{ padding: '1rem 1.25rem', background: '#fff1f1' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                              <WarningAlt size={16} style={{ color: '#da1e28' }} />
                              <strong style={{ fontSize: '0.875rem', color: '#da1e28' }}>Normalization failed</strong>
                              {original?.raw_data?._row_number != null && (
                                <span style={{ fontSize: '0.75rem', color: '#6f6f6f', marginLeft: '0.5rem' }}>
                                  Source: Row {original.raw_data._row_number} in your spreadsheet
                                </span>
                              )}
                            </div>
                            {retryError && (
                              <p style={{ fontSize: '0.8125rem', color: '#da1e28', margin: '0 0 0.5rem' }}>{retryError}</p>
                            )}
                            <p style={{ fontSize: '0.8125rem', color: '#525252', margin: '0 0 0.75rem' }}>
                              Use Retry to let the AI try again, or click Edit to enter the values manually.
                            </p>
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                              <Button kind="danger--ghost" size="sm" renderIcon={Renew} onClick={() => handleRetry(row.id)}>
                                Retry normalization
                              </Button>
                              <Button kind="primary" size="sm" renderIcon={Edit} onClick={() => setEditTarget(original)}>
                                Edit manually
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <div>
                            {/* Missing-fields call-to-action */}
                            {((row as any)._missingCount > 0) && (
                              <div style={{
                                padding: '0.75rem 1.25rem',
                                background: '#fff8e1',
                                borderBottom: '1px solid #f1c21b',
                                display: 'flex', alignItems: 'flex-start', gap: '0.75rem', flexWrap: 'wrap',
                              }}>
                                <WarningAlt size={16} style={{ color: '#8a3800', flexShrink: 0, marginTop: 2 }} />
                                <div style={{ flex: 1 }}>
                                  <p style={{ margin: 0, fontSize: '0.8125rem', fontWeight: 600, color: '#8a3800' }}>
                                    {(row as any)._missingCount} critical field{(row as any)._missingCount !== 1 ? 's' : ''} could not be determined
                                  </p>
                                  <p style={{ margin: '0.25rem 0 0', fontSize: '0.8125rem', color: '#525252' }}>
                                    {original?.raw_data?._row_number != null
                                      ? `Refer to Row ${original.raw_data._row_number} in your spreadsheet and click "Edit this record" to fill in the missing values.`
                                      : 'Open the original spreadsheet and click "Edit this record" to fill in the missing values.'
                                    }
                                  </p>
                                </div>
                              </div>
                            )}

                            <div className="record-detail">
                              {/* Source row number */}
                              {original?.raw_data?._row_number != null && (
                                <div className="record-detail-field">
                                  <label>Source Row</label>
                                  <span style={{ color: '#0043ce' }}>Row {original.raw_data._row_number} in your spreadsheet</span>
                                </div>
                              )}
                              {[
                                ['Datacenter',  safeGet(nd, 'vinfo.datacenter')],
                                ['Cluster',     safeGet(nd, 'vinfo.cluster')],
                                ['Host',        safeGet(nd, 'vinfo.host')],
                                ['Power State', safeGet(nd, 'vinfo.powerstate')],
                                ['IP Address',  safeGet(nd, 'vnetwork.0.ipv4_address')],
                                ['NIC Adapter', safeGet(nd, 'vnetwork.0.adapter')],
                                ['Network',     safeGet(nd, 'vnetwork.0.network')],
                                ['Disk Label',  safeGet(nd, 'vpartition.0.disk_label')],
                                ['OS (Tools)',  safeGet(nd, 'vinfo.os_vmware_tools')],
                                ['ESX Version', safeGet(nd, 'vhost.esx_version')],
                              ].filter(([, v]) => v != null).map(([label, value]) => (
                                <div key={label as string} className="record-detail-field">
                                  <label>{label as string}</label>
                                  <span>{String(value)}</span>
                                </div>
                              ))}
                            </div>

                            {/* Notes — shown when set */}
                            {original?.notes && (
                              <div style={{ padding: '0.5rem 1.25rem', borderTop: '1px solid #e0e0e0', display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#525252', minWidth: 60, paddingTop: 2 }}>Notes</span>
                                <span style={{ fontSize: '0.8125rem', color: '#161616', whiteSpace: 'pre-wrap' }}>{original.notes}</span>
                              </div>
                            )}

                            {/* Exclusion reason input — visible only when row is excluded */}
                            {isExcluded && (
                              <div style={{ padding: '0.75rem 1.25rem', borderTop: '1px solid #e0e0e0', background: '#f9f3ff' }}>
                                <p style={{ fontSize: '0.8125rem', color: '#6929c4', margin: '0 0 0.5rem', fontWeight: 500 }}>
                                  This server is excluded from all exports.
                                </p>
                                <TextInput
                                  id={`reason-${row.id}`}
                                  labelText="Exclusion reason (optional)"
                                  size="sm"
                                  value={currentReason}
                                  placeholder="e.g. Decommissioned, out of scope, migrated already…"
                                  onChange={(e: any) => setReasonDraft(prev => ({ ...prev, [row.id]: e.target.value }))}
                                  onBlur={() => handleReasonSave(row.id, true)}
                                  onKeyDown={(e: any) => { if (e.key === 'Enter') handleReasonSave(row.id, true); }}
                                  style={{ maxWidth: 480 }}
                                />
                              </div>
                            )}

                            <div style={{ padding: '0.75rem 1.25rem', borderTop: '1px solid #e0e0e0' }}>
                              <Button
                                kind={(row as any)._missingCount > 0 ? 'primary' : 'ghost'}
                                size="sm"
                                renderIcon={Edit}
                                onClick={() => setEditTarget(original)}
                              >
                                Edit this record
                              </Button>
                            </div>
                          </div>
                        )}
                      </TableExpandedRow>
                    </>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </DataTable>

      {filtered.length > pageSize && (
        <Pagination
          totalItems={filtered.length}
          pageSize={pageSize}
          page={page}
          pageSizes={[10, 20, 50]}
          onChange={({ page: p, pageSize: ps }: any) => { setPage(p); setPageSize(ps); }}
        />
      )}

      {editTarget && (
        <EditRecordModal
          open
          projectId={projectId}
          record={editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={(updated) => {
            setRecords(prev => prev.map(r => r.id === updated.id ? updated : r));
            setEditTarget(null);
          }}
        />
      )}
    </>
  );
}
