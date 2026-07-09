import { useState, useEffect, useCallback } from 'react';
import {
  DataTable, DataTableSkeleton, Table, TableHead, TableRow, TableHeader,
  TableBody, TableCell, TableContainer, TableToolbar, TableToolbarContent,
  TableToolbarSearch, TableExpandRow, TableExpandedRow, TableExpandHeader,
  Tag, Pagination, Button, InlineLoading, InlineNotification,
} from '@carbon/react';
import { Renew, WarningAlt, Edit } from '@carbon/icons-react';
import { api, ServerRecord, Assumption } from '../api/client';
import EditRecordModal from './EditRecordModal';

interface Props {
  projectId: string;
  onViewAssumptions: (vmName: string, assumptions: Assumption[]) => void;
}

const headers = [
  { key: 'vm_name',     header: 'Server Name' },
  { key: 'server_type', header: 'Type' },
  { key: 'cpus',        header: 'vCPUs' },
  { key: 'memory_gb',   header: 'RAM (GB)' },
  { key: 'storage_gb',  header: 'Storage (GB)' },
  { key: 'os',          header: 'Operating System' },
  { key: 'status_col',  header: 'Status' },
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

export default function RecordsTable({ projectId, onViewAssumptions }: Props) {
  const [records, setRecords] = useState<ServerRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [filterText, setFilterText] = useState('');
  const [retrying, setRetrying] = useState<Set<string>>(new Set());
  const [retryErrors, setRetryErrors] = useState<Record<string, string>>({});
  const [editTarget, setEditTarget] = useState<ServerRecord | null>(null);

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
      // Reload records to get updated data
      await loadRecords();
    } catch {
      setRetryErrors(prev => ({ ...prev, [recordId]: 'Retry request failed' }));
    } finally {
      setRetrying(prev => { const n = new Set(prev); n.delete(recordId); return n; });
    }
  }

  // Show both complete AND error records
  const visibleRecords = records.filter(
    r => r.processing_status === 'complete' || r.processing_status === 'error'
      || r.status === 'complete' || r.status === 'error'
  );

  const filtered = filterText
    ? visibleRecords.filter(r => {
        const name = safeGet(r.normalized_data, 'vinfo.vm_name')
          ?? safeGet(r.raw_data, 'name', 'Server Name', 'VM', 'vm_name', 'hostname') ?? '';
        return String(name).toLowerCase().includes(filterText.toLowerCase());
      })
    : visibleRecords;

  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);

  const rows = paged.map(r => {
    const isFailed = r.processing_status === 'error' || r.status === 'error';
    const nd = r.normalized_data ?? {};
    const rawName = safeGet(r.raw_data, 'name', 'Server Name', 'VM', 'vm_name', 'hostname') ?? r.id;
    const vmName  = safeGet(nd, 'vinfo.vm_name') ?? rawName;
    const type    = safeGet(nd, 'server_type') ?? 'vm';
    const cpus    = safeGet(nd, 'vinfo.cpus', 'vinfo.cpu_count');
    const memMb   = safeGet(nd, 'vinfo.memory_mb');
    const diskMb  = safeGet(nd, 'vinfo.provisioned_mb');
    const os      = safeGet(nd, 'vinfo.os_config') ?? (isFailed ? '—' : '—');
    const asmCount = (r.assumptions ?? []).length;

    return {
      id: r.id,
      vm_name:     vmName,
      server_type: isFailed ? 'error' : type,
      cpus:        cpus != null ? String(cpus) : '—',
      memory_gb:   mbToGb(memMb),
      storage_gb:  mbToGb(diskMb),
      os:          String(os).replace(/ \(64-bit\)/i, ''),
      status_col:  isFailed ? 'error' : asmCount,
      _record:     r,
      _isFailed:   isFailed,
    };
  });

  if (loading) return <DataTableSkeleton columnCount={7} rowCount={8} />;
  if (visibleRecords.length === 0) return null;

  const failedCount = visibleRecords.filter(r => r.processing_status === 'error' || r.status === 'error').length;

  return (
    <>
      {failedCount > 0 && (
        <InlineNotification
          kind="warning"
          title={`${failedCount} record${failedCount !== 1 ? 's' : ''} failed normalization`}
          subtitle="Use the Retry button on each failed row to reprocess it."
          lowContrast
          style={{ marginBottom: '1rem' }}
        />
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
                  const original = paged.find(r => r.id === row.id)!;
                  const nd = original?.normalized_data ?? {};
                  const isFailed = (original?.processing_status === 'error' || original?.status === 'error');
                  const isRetrying = retrying.has(row.id);
                  const retryError = retryErrors[row.id];

                  return (
                    <>
                      <TableExpandRow
                        {...getRowProps({ row })}
                        key={row.id}
                        style={isFailed ? { background: '#fff8f8' } : undefined}
                      >
                        {row.cells.map((cell: any) => {
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
                                <Tag type={cell.value === 'bare_metal' ? 'teal' : 'blue'} size="sm">
                                  {cell.value === 'bare_metal' ? 'Bare Metal' : 'Virtual'}
                                </Tag>
                              </TableCell>
                            );
                          }
                          if (cell.info.header === 'status_col') {
                            if (cell.value === 'error') {
                              return (
                                <TableCell key={cell.id}>
                                  {isRetrying ? (
                                    <InlineLoading description="Retrying…" />
                                  ) : (
                                    <Button
                                      kind="ghost"
                                      size="sm"
                                      renderIcon={Renew}
                                      onClick={() => handleRetry(row.id)}
                                    >
                                      Retry
                                    </Button>
                                  )}
                                </TableCell>
                              );
                            }
                            const count = cell.value as number;
                            if (count === 0) return <TableCell key={cell.id}><span style={{ color: '#8d8d8d' }}>—</span></TableCell>;
                            return (
                              <TableCell key={cell.id}>
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
                          if (cell.info.header === 'vm_name') {
                            return (
                              <TableCell key={cell.id}>
                                <span className="vm-name-cell">{cell.value}</span>
                              </TableCell>
                            );
                          }
                          return <TableCell key={cell.id}>{cell.value}</TableCell>;
                        })}
                      </TableExpandRow>

                      {/* Expanded detail / error detail */}
                      <TableExpandedRow colSpan={tableHeaders.length + 1} key={`${row.id}-exp`}>
                        {isFailed ? (
                          <div style={{ padding: '1rem 1.25rem', background: '#fff1f1' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                              <WarningAlt size={16} style={{ color: '#da1e28' }} />
                              <strong style={{ fontSize: '0.875rem', color: '#da1e28' }}>Normalization failed</strong>
                            </div>
                            {retryError && (
                              <p style={{ fontSize: '0.8125rem', color: '#da1e28', margin: '0 0 0.5rem' }}>{retryError}</p>
                            )}
                            <p style={{ fontSize: '0.8125rem', color: '#525252', margin: 0 }}>
                              Raw data keys: {Object.keys(original?.raw_data ?? {}).join(', ') || '(empty)'}
                            </p>
                          </div>
                        ) : (
                          <div>
                            <div className="record-detail">
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
                            <div style={{ padding: '0.75rem 1.25rem', borderTop: '1px solid #e0e0e0' }}>
                              <Button
                                kind="ghost"
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
