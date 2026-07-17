const BASE = '/api';

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

export type LLMProvider = 'ollama' | 'watsonx' | 'openai' | 'anthropic';

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
}

export interface LLMTestResult {
  ok: boolean;
  provider: string;
  latency_ms: number | null;
  preview: string | null;
  error: string | null;
}

export const api = {
  folders: {
    list: (parentId?: string | null): Promise<{ folders: Folder[]; total: number }> => {
      // parentId undefined = no filter (all); null = root level (no parent); string = that parent
      // The API expects no param for "all", no param for root (parent_id IS NULL handled server-side),
      // so we only append parent_id when it's a real UUID string.
      const qs = (parentId !== undefined && parentId !== null) ? `?parent_id=${parentId}` : '';
      return fetch(`${BASE}/folders${qs}`).then(r => r.json());
    },
    create: (data: { name: string; parent_id?: string | null }): Promise<Folder> =>
      fetch(`${BASE}/folders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }).then(r => r.json()),
    rename: (id: string, name: string): Promise<Folder> =>
      fetch(`${BASE}/folders/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      }).then(r => r.json()),
    delete: (id: string): Promise<Response> =>
      fetch(`${BASE}/folders/${id}`, { method: 'DELETE' }),
  },
  projects: {
    list: (folderId?: string | null): Promise<{ projects: Project[]; total: number }> => {
      // folderId undefined = all projects; null = root only; string = that folder
      const qs = folderId !== undefined ? `?folder_id=${folderId ?? 'null'}` : '';
      return fetch(`${BASE}/projects${qs}`).then(r => r.json());
    },
    create: (data: { name: string; description?: string; folder_id?: string | null; vpc_region?: string; vpc_datacenter?: string }): Promise<Project> =>
      fetch(`${BASE}/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }).then(r => r.json()),
    get: (id: string): Promise<Project> =>
      fetch(`${BASE}/projects/${id}`).then(r => r.json()),
    update: (id: string, data: { name?: string; description?: string; folder_id?: string | null; vpc_region?: string; vpc_datacenter?: string; pvs_region?: string; pvs_datacenter?: string }): Promise<Project> =>
      fetch(`${BASE}/projects/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }).then(r => r.json()),
    delete: (id: string): Promise<Response> =>
      fetch(`${BASE}/projects/${id}`, { method: 'DELETE' }),
    duplicate: (id: string, name: string): Promise<Project> =>
      fetch(`${BASE}/projects/${id}/duplicate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      }).then(async r => {
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Duplicate failed'); }
        return r.json();
      }),
  },
  uploads: {
    upload: (projectId: string, file: File): Promise<any> => {
      const form = new FormData();
      form.append('file', file);
      return fetch(`${BASE}/projects/${projectId}/uploads`, {
        method: 'POST',
        body: form,
      }).then(r => r.json());
    },
    getRecords: (projectId: string): Promise<{ records: ServerRecord[]; total: number }> =>
      fetch(`${BASE}/projects/${projectId}/records`).then(r => r.json()),
    getAssumptions: (projectId: string): Promise<Assumption[]> =>
      fetch(`${BASE}/projects/${projectId}/assumptions`).then(r => r.json()),
    patchRecord: (projectId: string, recordId: string, vinfo: Record<string, any>): Promise<ServerRecord> =>
      fetch(`${BASE}/projects/${projectId}/records/${recordId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vinfo }),
      }).then(r => r.json()),
    excludeRecord: (projectId: string, recordId: string, isExcluded: boolean, reason?: string | null): Promise<ServerRecord> =>
      fetch(`${BASE}/projects/${projectId}/records/${recordId}/exclude`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_excluded: isExcluded, exclusion_reason: reason ?? null }),
      }).then(r => r.json()),
    bulkOsReplace: (projectId: string, fromOs: string, toOs: string): Promise<{ updated_count: number; from_os: string; to_os: string }> =>
      fetch(`${BASE}/projects/${projectId}/bulk-os-replace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_os: fromOs, to_os: toOs }),
      }).then(r => r.json()),
    getNxfUnsupportedCount: (projectId: string): Promise<{ unsupported_count: number; preview_names: string[] }> =>
      fetch(`${BASE}/projects/${projectId}/nxf-unsupported-count`).then(r => r.json()),
    bulkNxfReplace: (projectId: string, targetProfile: string): Promise<{ updated_count: number; target_profile: string }> =>
      fetch(`${BASE}/projects/${projectId}/bulk-nxf-replace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_profile: targetProfile }),
      }).then(r => r.json()),
    bulkExclude: (projectId: string, filterType: string, filterValue: string, reason?: string): Promise<{ updated_count: number; filter_type: string; filter_value: string }> =>
      fetch(`${BASE}/projects/${projectId}/bulk-exclude`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filter_type: filterType, filter_value: filterValue, reason: reason || null }),
      }).then(r => r.json()),
  },
  processing: {
    start: (projectId: string): Promise<{ status: string; record_count: number; message: string }> =>
      fetch(`${BASE}/projects/${projectId}/process`, { method: 'POST' }).then(r => r.json()),
    getStatus: (projectId: string): Promise<ProcessingStatus> =>
      fetch(`${BASE}/projects/${projectId}/processing-status`).then(r => r.json()),
    retryRecord: (projectId: string, recordId: string): Promise<{ processing_status: string; error_message: string | null }> =>
      fetch(`${BASE}/projects/${projectId}/records/${recordId}/process`, { method: 'POST' }).then(r => r.json()),
    resetStuck: (projectId: string): Promise<{ reset_count: number; message: string }> =>
      fetch(`${BASE}/projects/${projectId}/processing/reset-stuck`, { method: 'POST' }).then(r => r.json()),
  },
  exports: {
    // RVTools Export — 22-sheet full RVTools format (VCF Migration Lite)
    generateRVToolsPure: (projectId: string): Promise<ExportRecord> =>
      fetch(`${BASE}/projects/${projectId}/export/rvtools`, { method: 'POST' }).then(r => r.json()),
    downloadRVToolsPure: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/rvtools/${exportId}/download`),
    generateAssumptions: (projectId: string): Promise<ExportRecord> =>
      fetch(`${BASE}/projects/${projectId}/export/assumptions`, { method: 'POST' }).then(r => r.json()),
    downloadAssumptions: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/assumptions/${exportId}/download`),
    generateRVToolsPowerVS: (projectId: string): Promise<ExportRecord> =>
      fetch(`${BASE}/projects/${projectId}/export/rvtools-powervs`, { method: 'POST' }).then(r => r.json()),
    downloadRVToolsPowerVS: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/rvtools/${exportId}/download`),
    generateRVToolsPowerVSFull: (projectId: string): Promise<ExportRecord> =>
      fetch(`${BASE}/projects/${projectId}/export/rvtools-powervs-full`, { method: 'POST' }).then(r => r.json()),
    downloadRVToolsPowerVSFull: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/rvtools/${exportId}/download`),
    generatePowerVSCalculator: (projectId: string): Promise<ExportRecord> =>
      fetch(`${BASE}/projects/${projectId}/export/powervs-calculator`, { method: 'POST' }).then(r => r.json()),
    downloadPowerVSCalculator: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/rvtools/${exportId}/download`),


    generateAssumptionsPowerVS: (projectId: string): Promise<ExportRecord> =>
      fetch(`${BASE}/projects/${projectId}/export/assumptions-powervs`, { method: 'POST' }).then(r => r.json()),
    downloadAssumptionsPowerVS: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/assumptions/${exportId}/download`),
    getPowerVSCount: (projectId: string): Promise<{ powervs_count: number }> =>
      fetch(`${BASE}/projects/${projectId}/powervs-count`).then(r => r.json()),
    // IBM Cloud VPC Calculator export (3-sheet: Project Settings, Exceptions, Data Domains)
    generateVPCCalculator: (projectId: string): Promise<ExportRecord> =>
      fetch(`${BASE}/projects/${projectId}/export/vpc-calculator`, { method: 'POST' }).then(r => r.json()),
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
      return fetch(`${BASE}/restore`, { method: 'POST', body: form }).then(async r => {
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: 'Restore failed' }));
          throw new Error(err.detail || 'Restore failed');
        }
        return r.json();
      });
    },
  },
  settings: {
    get: (): Promise<LLMSettingsResponse> =>
      fetch(`${BASE}/settings`).then(r => r.json()),
    save: (data: LLMSettingsSave): Promise<LLMSettingsResponse> =>
      fetch(`${BASE}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }).then(r => r.json()),
    test: (data: LLMSettingsSave): Promise<LLMTestResult> =>
      fetch(`${BASE}/settings/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }).then(r => r.json()),
    getRecommendation: (): Promise<ModelRecommendationCheck> =>
      fetch(`${BASE}/settings/model-recommendation`).then(r => r.json()),
    applyRecommendation: (): Promise<LLMSettingsResponse> =>
      fetch(`${BASE}/settings/model-recommendation/apply`, { method: 'POST' }).then(r => r.json()),
    rollbackModel: (): Promise<LLMSettingsResponse> =>
      fetch(`${BASE}/settings/model-recommendation/rollback`, { method: 'POST' }).then(r => r.json()),
    snoozeRecommendation: (): Promise<LLMSettingsResponse> =>
      fetch(`${BASE}/settings/model-recommendation/snooze`, { method: 'POST' }).then(r => r.json()),
  },

  pricingTemplate: {
    getStatus: (projectId: string): Promise<{ has_template: boolean; filename: string | null; updated_at: string | null }> =>
      fetch(`${BASE}/projects/${projectId}/pricing-template/status`).then(r => r.json()),
    upload: (projectId: string, file: File): Promise<{ id: string; project_id: string; filename: string; created_at: string; updated_at: string }> => {
      const form = new FormData();
      form.append('file', file);
      return fetch(`${BASE}/projects/${projectId}/pricing-template`, { method: 'POST', body: form }).then(async r => {
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: 'Upload failed' }));
          throw new Error(err.detail || 'Upload failed');
        }
        return r.json();
      });
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
