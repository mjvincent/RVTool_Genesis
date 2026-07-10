const BASE = '/api';

export interface Project {
  id: string;
  name: string;
  description: string | null;
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
}

export interface ServerRecord {
  id: string;
  project_id: string;
  status: 'pending' | 'processing' | 'complete' | 'error';
  processing_status: 'pending' | 'processing' | 'complete' | 'error';
  raw_data: any;
  normalized_data: any;
  server_type: string | null;
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
  updated_at: string;
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
  projects: {
    list: (): Promise<{ projects: Project[]; total: number }> =>
      fetch(`${BASE}/projects`).then(r => r.json()),
    create: (data: { name: string; description?: string }): Promise<Project> =>
      fetch(`${BASE}/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }).then(r => r.json()),
    get: (id: string): Promise<Project> =>
      fetch(`${BASE}/projects/${id}`).then(r => r.json()),
    delete: (id: string): Promise<Response> =>
      fetch(`${BASE}/projects/${id}`, { method: 'DELETE' }),
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
    // Cloud Solutioning Tool export (IBM Cool / VCF Migration Lite) — 22 sheets
    generateRVTools: (projectId: string): Promise<ExportRecord> =>
      fetch(`${BASE}/projects/${projectId}/export/rvtools`, { method: 'POST' }).then(r => r.json()),
    listRVTools: (projectId: string): Promise<ExportRecord[]> =>
      fetch(`${BASE}/projects/${projectId}/exports/rvtools`).then(r => r.json()),
    downloadRVTools: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/rvtools/${exportId}/download`),
    // Pure RVTools export — 4 sheets (vInfo, vNetwork, vPartition, vHost)
    generateRVToolsPure: (projectId: string): Promise<ExportRecord> =>
      fetch(`${BASE}/projects/${projectId}/export/rvtools-pure`, { method: 'POST' }).then(r => r.json()),
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
    generateAssumptionsPowerVS: (projectId: string): Promise<ExportRecord> =>
      fetch(`${BASE}/projects/${projectId}/export/assumptions-powervs`, { method: 'POST' }).then(r => r.json()),
    downloadAssumptionsPowerVS: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/assumptions/${exportId}/download`),
    getPowerVSCount: (projectId: string): Promise<{ powervs_count: number }> =>
      fetch(`${BASE}/projects/${projectId}/powervs-count`).then(r => r.json()),
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
