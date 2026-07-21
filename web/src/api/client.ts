const BASE = '/api';

// ---------------------------------------------------------------------------
// Central fetch helper — throws ApiError for any non-2xx response so
// components always receive either valid data or a typed error.
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function apiFetch<T>(input: string, init?: RequestInit): Promise<T> {
  // Include the API token when one is configured (set VITE_API_TOKEN in the
  // build environment for IBM-facing / shared-network deployments).
  const token = import.meta.env.VITE_API_TOKEN as string | undefined;
  const headers: HeadersInit = { ...(init?.headers ?? {}) };
  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }
  const r = await fetch(input, { ...init, headers });
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try {
      const body = await r.json();
      detail = body?.detail ?? body?.message ?? detail;
    } catch {
      // ignore — detail stays as "HTTP <status>"
    }
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

// IBM Cloud VPC regions and their availability zones
export const IBM_VPC_REGIONS: Record<string, { label: string; geography: string; zones: string[] }> = {
  'us-south':  { label: 'Dallas (us-south)',        geography: 'North America', zones: ['us-south-1', 'us-south-2', 'us-south-3'] },
  'us-east':   { label: 'Washington DC (us-east)',  geography: 'North America', zones: ['us-east-1',  'us-east-2',  'us-east-3']  },
  'ca-tor':    { label: 'Toronto (ca-tor)',          geography: 'North America', zones: ['ca-tor-1',   'ca-tor-2',   'ca-tor-3']   },
  'ca-mon':    { label: 'Montreal (ca-mon)',         geography: 'North America', zones: ['ca-mon-1',   'ca-mon-2',   'ca-mon-3']   },
  'br-sao':    { label: 'São Paulo (br-sao)',        geography: 'South America', zones: ['br-sao-1',   'br-sao-2',   'br-sao-3']   },
  'eu-gb':     { label: 'London (eu-gb)',            geography: 'Europe',        zones: ['eu-gb-1',    'eu-gb-2',    'eu-gb-3']    },
  'eu-de':     { label: 'Frankfurt (eu-de)',         geography: 'Europe',        zones: ['eu-de-1',    'eu-de-2',    'eu-de-3']    },
  'eu-es':     { label: 'Madrid (eu-es)',            geography: 'Europe',        zones: ['eu-es-1',    'eu-es-2',    'eu-es-3']    },
  'eu-fr2':    { label: 'Paris (eu-fr2)',            geography: 'Europe',        zones: ['eu-fr2-1',   'eu-fr2-2',   'eu-fr2-3']   },
  'jp-tok':    { label: 'Tokyo (jp-tok)',            geography: 'Asia Pacific',  zones: ['jp-tok-1',   'jp-tok-2',   'jp-tok-3']   },
  'jp-osa':    { label: 'Osaka (jp-osa)',            geography: 'Asia Pacific',  zones: ['jp-osa-1',   'jp-osa-2',   'jp-osa-3']   },
  'au-syd':    { label: 'Sydney (au-syd)',           geography: 'Asia Pacific',  zones: ['au-syd-1',   'au-syd-2',   'au-syd-3']   },
  'in-che':    { label: 'Chennai (in-che)',          geography: 'Asia Pacific',  zones: ['in-che-1']                               },
  'kr-seo':    { label: 'Seoul (kr-seo)',            geography: 'Asia Pacific',  zones: ['kr-seo-1',   'kr-seo-2']                 },
  'mx-qro':    { label: 'Querétaro (mx-qro)',        geography: 'North America', zones: ['mx-qro-1',   'mx-qro-2',   'mx-qro-3']   },
};

// IBM PowerVS regions and their datacenters (short names like dal10, lon06)
export const IBM_POWERVS_REGIONS: Record<string, { label: string; geography: string; datacenters: string[] }> = {
  'us-south':  { label: 'Dallas (us-south)',        geography: 'North America', datacenters: ['dal10', 'dal12']         },
  'us-east':   { label: 'Washington DC (us-east)',  geography: 'North America', datacenters: ['wdc06', 'wdc07']         },
  'ca-tor':    { label: 'Toronto (ca-tor)',          geography: 'North America', datacenters: ['tor01']                  },
  'eu-de':     { label: 'Frankfurt (eu-de)',         geography: 'Europe',        datacenters: ['fra04', 'fra05']         },
  'eu-gb':     { label: 'London (eu-gb)',            geography: 'Europe',        datacenters: ['lon04', 'lon06']         },
  'jp-tok':    { label: 'Tokyo (jp-tok)',            geography: 'Asia Pacific',  datacenters: ['tok02', 'tok04']         },
  'jp-osa':    { label: 'Osaka (jp-osa)',            geography: 'Asia Pacific',  datacenters: ['osa21']                  },
  'au-syd':    { label: 'Sydney (au-syd)',           geography: 'Asia Pacific',  datacenters: ['syd04', 'syd05']         },
  'in-che':    { label: 'Chennai (in-che)',          geography: 'Asia Pacific',  datacenters: ['che01']                  },
  'br-sao':    { label: 'São Paulo (br-sao)',        geography: 'South America', datacenters: ['sao01', 'sao04']         },
};

export interface Folder {
  id: string;
  name: string;
  parent_id: string | null;
  created_at: string;
  updated_at: string;
  project_count: number;
  child_count: number;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  folder_id: string | null;
  vpc_region: string | null;
  vpc_datacenter: string | null;
  pvs_region: string | null;
  pvs_datacenter: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProcessingStatus {
  total: number;
  pending: number;
  processing: number;
  complete: number;
  error: number;
  is_complete: boolean;
  current_record_name?: string | null;
}

export interface ServerRecord {
  id: string;
  project_id: string;
  status: 'pending' | 'processing' | 'complete' | 'error';
  processing_status: 'pending' | 'processing' | 'complete' | 'error';
  raw_data: any;
  normalized_data: any;
  server_type: string | null;
  error_message: string | null;
  assumptions: Assumption[];
  is_excluded: boolean;
  exclusion_reason: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface Assumption {
  id: string;
  record_id: string;
  field_name: string;
  assumed_value: any;
  original_value: any;
  reasoning: string;
  confidence: 'high' | 'medium' | 'low';
}

export interface ExportRecord {
  id: string;
  project_id: string;
  export_type: string;
  file_path: string;
  created_at: string;
}

export type LLMProvider = 'ollama' | 'watsonx' | 'openai' | 'anthropic' | 'docker_model_runner';

export interface LLMSettingsResponse {
  provider: LLMProvider;
  ollama_base_url: string | null;
  ollama_model: string | null;
  watsonx_api_key_hint: string | null;
  watsonx_project_id: string | null;
  watsonx_url: string | null;
  watsonx_model: string | null;
  openai_api_key_hint: string | null;
  openai_base_url: string | null;
  openai_model: string | null;
  anthropic_api_key_hint: string | null;
  anthropic_model: string | null;
  dmr_base_url: string | null;
  dmr_model: string | null;
  previous_model: string | null;
  updated_at: string;
}

export interface ModelRecommendation {
  provider: string;
  current_model: string;
  recommended_model: string;
  recommended_label: string;
  reason: string;
}

export interface ModelRecommendationCheck {
  recommendation: ModelRecommendation | null;
  snoozed: boolean;
}

export interface LocalAdvisorModel {
  name: string;
  size_gb: number;
  fits_in_ram: boolean;
  task_fit: number;
  recommended: boolean;
}

export interface LocalAdvisorResponse {
  cpu_model: string;
  cpu_arch: string;
  ram_gb: number;
  ollama_reachable: boolean;
  installed_models: LocalAdvisorModel[];
  pull_suggestion: { model: string; label: string } | null;
  current_model: string | null;
}

export interface DiscoveredModel {
  name: string;
  source: 'ollama' | 'huggingface';
  size_gb: number;
  fits_in_ram: boolean;
  task_fit: number;
  description: string;
  pull_count: number;
  pull_command: string;
}

export interface DiscoveryResponse {
  discovered: DiscoveredModel[];
  sources_checked: string[];
  sources_reachable: Record<string, boolean>;
  ram_gb: number;
  current_model: string | null;
  current_task_fit: number | null;
}

export interface LLMSettingsSave {
  provider: LLMProvider;
  ollama_base_url?: string | null;
  ollama_model?: string | null;
  watsonx_api_key?: string | null;
  watsonx_project_id?: string | null;
  watsonx_url?: string | null;
  watsonx_model?: string | null;
  openai_api_key?: string | null;
  openai_base_url?: string | null;
  openai_model?: string | null;
  anthropic_api_key?: string | null;
  anthropic_model?: string | null;
  dmr_base_url?: string | null;
  dmr_model?: string | null;
}

export interface LLMTestResult {
  ok: boolean;
  provider: string;
  latency_ms: number | null;
  preview: string | null;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Model benchmark interfaces
// ---------------------------------------------------------------------------

export type BackendType = 'ollama' | 'docker_model_runner';

export interface BenchmarkRequest {
  model_a: string;
  model_a_backend?: BackendType;
  model_b: string;
  model_b_backend?: BackendType;
}

export interface BenchmarkCaseResult {
  case_id: number;
  description: string;
  valid_json: boolean;
  field_results: Record<string, boolean>;
  passed: number;
  total: number;
  latency_ms: number;
  error: string | null;
}

export interface ModelResult {
  name: string;
  backend: string;
  composite_score: number;
  accuracy_pct: number;
  speed_score: number;
  avg_latency_ms: number;
  reachable: boolean;
  cases: BenchmarkCaseResult[];
}

export interface BenchmarkResult {
  model_a: ModelResult;
  model_b: ModelResult;
  winner: 'model_a' | 'model_b' | 'tie';
  recommendation: string;
}

export const api = {
  folders: {
    list: (parentId?: string | null): Promise<{ folders: Folder[]; total: number }> => {
      // parentId undefined = no filter (all); null = root level (no parent); string = that parent
      // The API expects no param for "all", no param for root (parent_id IS NULL handled server-side),
      // so we only append parent_id when it's a real UUID string.
      const qs = (parentId !== undefined && parentId !== null) ? `?parent_id=${parentId}` : '';
      return apiFetch(`${BASE}/folders${qs}`);
    },
    create: (data: { name: string; parent_id?: string | null }): Promise<Folder> =>
      apiFetch(`${BASE}/folders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    rename: (id: string, name: string): Promise<Folder> =>
      apiFetch(`${BASE}/folders/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      }),
    delete: (id: string): Promise<Response> =>
      fetch(`${BASE}/folders/${id}`, { method: 'DELETE' }),
  },
  projects: {
    list: (folderId?: string | null): Promise<{ projects: Project[]; total: number }> => {
      // folderId undefined = all projects; null = root only; string = that folder
      const qs = folderId !== undefined ? `?folder_id=${folderId ?? 'null'}` : '';
      return apiFetch(`${BASE}/projects${qs}`);
    },
    create: (data: { name: string; description?: string; folder_id?: string | null; vpc_region?: string; vpc_datacenter?: string }): Promise<Project> =>
      apiFetch(`${BASE}/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    get: (id: string): Promise<Project> =>
      apiFetch(`${BASE}/projects/${id}`),
    update: (id: string, data: { name?: string; description?: string; folder_id?: string | null; vpc_region?: string; vpc_datacenter?: string; pvs_region?: string; pvs_datacenter?: string }): Promise<Project> =>
      apiFetch(`${BASE}/projects/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    delete: (id: string): Promise<Response> =>
      fetch(`${BASE}/projects/${id}`, { method: 'DELETE' }),
    duplicate: (id: string, name: string): Promise<Project> =>
      apiFetch(`${BASE}/projects/${id}/duplicate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      }),
  },
  uploads: {
    upload: (projectId: string, file: File): Promise<{ id: string; project_id: string; filename: string; status: string; row_count: number | null; uploaded_at: string; error_message: string | null }> => {
      const form = new FormData();
      form.append('file', file);
      return apiFetch(`${BASE}/projects/${projectId}/uploads`, {
        method: 'POST',
        body: form,
      });
    },
    getRecords: (projectId: string): Promise<{ records: ServerRecord[]; total: number }> =>
      apiFetch(`${BASE}/projects/${projectId}/records`),
    getAssumptions: (projectId: string): Promise<Assumption[]> =>
      apiFetch(`${BASE}/projects/${projectId}/assumptions`),
    patchRecord: (projectId: string, recordId: string, fields: Record<string, unknown>): Promise<ServerRecord> => {
      // Top-level keys (notes) are handled separately from vinfo fields on the backend.
      // We send them merged into a flat dict; the backend pops known top-level keys first.
      const { notes, ...vinfo } = fields;
      const body: Record<string, unknown> = { ...vinfo };
      if (notes !== undefined) body.notes = notes;
      return apiFetch(`${BASE}/projects/${projectId}/records/${recordId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    },
    excludeRecord: (projectId: string, recordId: string, isExcluded: boolean, reason?: string | null): Promise<ServerRecord> =>
      apiFetch(`${BASE}/projects/${projectId}/records/${recordId}/exclude`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_excluded: isExcluded, exclusion_reason: reason ?? null }),
      }),
    bulkOsReplace: (projectId: string, fromOs: string, toOs: string): Promise<{ updated_count: number; from_os: string; to_os: string }> =>
      apiFetch(`${BASE}/projects/${projectId}/bulk-os-replace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_os: fromOs, to_os: toOs }),
      }),
    getNxfUnsupportedCount: (projectId: string): Promise<{ unsupported_count: number; preview_names: string[] }> =>
      apiFetch(`${BASE}/projects/${projectId}/nxf-unsupported-count`),
    bulkNxfReplace: (projectId: string, targetProfile: string): Promise<{ updated_count: number; target_profile: string }> =>
      apiFetch(`${BASE}/projects/${projectId}/bulk-nxf-replace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_profile: targetProfile }),
      }),
    bulkExclude: (projectId: string, filterType: string, filterValue: string, reason?: string): Promise<{ updated_count: number; filter_type: string; filter_value: string }> =>
      apiFetch(`${BASE}/projects/${projectId}/bulk-exclude`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filter_type: filterType, filter_value: filterValue, reason: reason || null }),
      }),
  },
  processing: {
    start: (projectId: string): Promise<{ status: string; record_count: number; message: string }> =>
      apiFetch(`${BASE}/projects/${projectId}/process`, { method: 'POST' }),
    getStatus: (projectId: string): Promise<ProcessingStatus> =>
      apiFetch(`${BASE}/projects/${projectId}/processing-status`),
    retryRecord: (projectId: string, recordId: string): Promise<{ processing_status: string; error_message: string | null }> =>
      apiFetch(`${BASE}/projects/${projectId}/records/${recordId}/process`, { method: 'POST' }),
    resetStuck: (projectId: string): Promise<{ reset_count: number; message: string }> =>
      apiFetch(`${BASE}/projects/${projectId}/processing/reset-stuck`, { method: 'POST' }),
  },
  exports: {
    // RVTools Export — 22-sheet full RVTools format (VCF Migration Lite)
    generateRVToolsPure: (projectId: string): Promise<ExportRecord> =>
      apiFetch(`${BASE}/projects/${projectId}/export/rvtools`, { method: 'POST' }),
    downloadRVToolsPure: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/rvtools/${exportId}/download`),
    generateAssumptions: (projectId: string): Promise<ExportRecord> =>
      apiFetch(`${BASE}/projects/${projectId}/export/assumptions`, { method: 'POST' }),
    downloadAssumptions: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/assumptions/${exportId}/download`),
    generateRVToolsPowerVS: (projectId: string): Promise<ExportRecord> =>
      apiFetch(`${BASE}/projects/${projectId}/export/rvtools-powervs`, { method: 'POST' }),
    downloadRVToolsPowerVS: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/rvtools/${exportId}/download`),
    generateRVToolsPowerVSFull: (projectId: string): Promise<ExportRecord> =>
      apiFetch(`${BASE}/projects/${projectId}/export/rvtools-powervs-full`, { method: 'POST' }),
    downloadRVToolsPowerVSFull: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/rvtools/${exportId}/download`),
    generatePowerVSCalculator: (projectId: string): Promise<ExportRecord> =>
      apiFetch(`${BASE}/projects/${projectId}/export/powervs-calculator`, { method: 'POST' }),
    downloadPowerVSCalculator: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/rvtools/${exportId}/download`),
    generateAssumptionsPowerVS: (projectId: string): Promise<ExportRecord> =>
      apiFetch(`${BASE}/projects/${projectId}/export/assumptions-powervs`, { method: 'POST' }),
    downloadAssumptionsPowerVS: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/assumptions/${exportId}/download`),
    getPowerVSCount: (projectId: string): Promise<{ powervs_count: number }> =>
      apiFetch(`${BASE}/projects/${projectId}/powervs-count`),
    // IBM Cloud VPC Calculator export (3-sheet: Project Settings, Exceptions, Data Domains)
    generateVPCCalculator: (projectId: string): Promise<ExportRecord> =>
      apiFetch(`${BASE}/projects/${projectId}/export/vpc-calculator`, { method: 'POST' }),
    downloadVPCCalculator: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/rvtools/${exportId}/download`),
  },
  backup: {
    downloadProject: (projectId: string, includeFile = false): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/backup?include_file=${includeFile}`),
    downloadAll: (includeFiles = false): Promise<Response> =>
      fetch(`${BASE}/backup/all?include_files=${includeFiles}`),
    restore: (file: File): Promise<{ restored: { id: string; name: string }[]; count: number }> => {
      const form = new FormData();
      form.append('file', file);
      return apiFetch(`${BASE}/restore`, { method: 'POST', body: form });
    },
  },
  settings: {
    get: (): Promise<LLMSettingsResponse> =>
      apiFetch(`${BASE}/settings`),
    save: (data: LLMSettingsSave): Promise<LLMSettingsResponse> =>
      apiFetch(`${BASE}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    test: (data: LLMSettingsSave): Promise<LLMTestResult> =>
      apiFetch(`${BASE}/settings/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    getRecommendation: (): Promise<ModelRecommendationCheck> =>
      apiFetch(`${BASE}/settings/model-recommendation`),
    applyRecommendation: (): Promise<LLMSettingsResponse> =>
      apiFetch(`${BASE}/settings/model-recommendation/apply`, { method: 'POST' }),
    rollbackModel: (): Promise<LLMSettingsResponse> =>
      apiFetch(`${BASE}/settings/model-recommendation/rollback`, { method: 'POST' }),
    snoozeRecommendation: (): Promise<LLMSettingsResponse> =>
      apiFetch(`${BASE}/settings/model-recommendation/snooze`, { method: 'POST' }),
    getLocalAdvisor: (refresh = false): Promise<LocalAdvisorResponse> =>
      apiFetch(`${BASE}/settings/local-advisor${refresh ? '?refresh=true' : ''}`),
    resolveGguf: (model: string): Promise<{ found: boolean; hf_repo: string | null; gguf_file: string | null; pull_command: string | null; size_gb: number | null; error?: string }> =>
      apiFetch(`${BASE}/settings/resolve-gguf?model=${encodeURIComponent(model)}`),
    benchmarkModels: (req: BenchmarkRequest): Promise<BenchmarkResult> =>
      apiFetch(`${BASE}/settings/benchmark-models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    discoverModels: (refresh = false): Promise<DiscoveryResponse> =>
      apiFetch(`${BASE}/settings/discover-models${refresh ? '?refresh=true' : ''}`),
    pullModel: (model: string): EventSource =>
      new EventSource(`${BASE}/settings/pull-model-stream?model=${encodeURIComponent(model)}`),
    pullModelFetch: (model: string): Promise<ReadableStream<Uint8Array> | null> =>
      fetch(`${BASE}/settings/pull-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
      }).then(r => r.body),
  },

  pricingTemplate: {
    getStatus: (projectId: string): Promise<{ has_template: boolean; filename: string | null; updated_at: string | null }> =>
      apiFetch(`${BASE}/projects/${projectId}/pricing-template/status`),
    upload: (projectId: string, file: File): Promise<{ id: string; project_id: string; filename: string; created_at: string; updated_at: string }> => {
      const form = new FormData();
      form.append('file', file);
      return apiFetch(`${BASE}/projects/${projectId}/pricing-template`, { method: 'POST', body: form });
    },
    populate: (projectId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/export/pricing-estimator`, { method: 'POST' }),
  },
};

export async function downloadFile(response: Response, filename: string) {
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
