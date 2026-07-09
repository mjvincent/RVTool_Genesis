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
  assumptions: Assumption[];
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
    generateRVTools: (projectId: string): Promise<ExportRecord> =>
      fetch(`${BASE}/projects/${projectId}/export/rvtools`, { method: 'POST' }).then(r => r.json()),
    listRVTools: (projectId: string): Promise<ExportRecord[]> =>
      fetch(`${BASE}/projects/${projectId}/exports/rvtools`).then(r => r.json()),
    downloadRVTools: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/rvtools/${exportId}/download`),
    generateAssumptions: (projectId: string): Promise<ExportRecord> =>
      fetch(`${BASE}/projects/${projectId}/export/assumptions`, { method: 'POST' }).then(r => r.json()),
    downloadAssumptions: (projectId: string, exportId: string): Promise<Response> =>
      fetch(`${BASE}/projects/${projectId}/exports/assumptions/${exportId}/download`),
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
