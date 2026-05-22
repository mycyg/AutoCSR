import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60_000,
  headers: { 'Content-Type': 'application/json' },
})

export interface ProjectDTO {
  id: string
  name: string
  principle_id: string | null
  created_at: string
  status: string
}

export interface CreateProjectPayload {
  name: string
  principle_id?: string | null
}

export interface FileEntryDTO {
  file_id: string
  project_id: string
  filename: string
  mime: string | null
  size_bytes: number
  stored_path: string
  uploaded_at: string
  ingest_type: string | null
  ingest_confidence: number | null
  needs_user_confirm: boolean
  status: 'uploaded' | 'routing' | 'running' | 'done' | 'error'
  error: string | null
}

export interface ColumnProfileDTO {
  name: string
  dtype: string
  null_rate: number
  n_unique: number
  sample_values: string[]
  top_freq: [string, number][]
  numeric_min: number | null
  numeric_max: number | null
  numeric_mean: number | null
  numeric_outlier_count: number | null
  suspected_role: string | null
  suspected_pii: boolean
}

export interface DataProfileDTO {
  file_id: string
  sheet: string | null
  n_rows: number
  n_cols: number
  columns: ColumnProfileDTO[]
  encoding_issues: string[]
}

export interface IngestResultDTO {
  file_id: string
  project_id: string
  ingest_type: string
  confidence: number
  artifacts: Record<string, string>
  profiles: DataProfileDTO[]
  corpus_block_ids: string[]
  needs_review: boolean
  notes: string[]
  error: string | null
}

export interface ProposalDTO {
  id: string
  project_id: string
  file_id: string
  sheet: string | null
  type: string
  target_columns: string[]
  parameters: Record<string, unknown>
  rationale: string
  confidence: number
  impact_rows: number
  status: 'pending' | 'accepted' | 'rejected' | 'applied' | 'edited'
  mandatory: boolean
  created_at: string
  edited_at: string | null
}

export async function listProjects(): Promise<ProjectDTO[]> {
  return (await api.get<ProjectDTO[]>('/projects')).data
}
export async function createProject(payload: CreateProjectPayload): Promise<ProjectDTO> {
  return (await api.post<ProjectDTO>('/projects', payload)).data
}
export async function getProject(id: string): Promise<ProjectDTO> {
  return (await api.get<ProjectDTO>(`/projects/${id}`)).data
}

export async function uploadFiles(pid: string, files: File[]): Promise<{ uploaded: { file_id: string; filename: string }[] }> {
  const fd = new FormData()
  for (const f of files) fd.append('files', f, f.name)
  const r = await api.post(`/projects/${pid}/upload`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300_000,
  })
  return r.data
}

export async function triggerIngest(pid: string): Promise<void> {
  await api.post(`/projects/${pid}/ingest`)
}

export async function ingestStatus(pid: string): Promise<{ total: number; by_status: Record<string, number>; all_done: boolean; entries: FileEntryDTO[] }> {
  return (await api.get(`/projects/${pid}/ingest_status`)).data
}

export async function listFiles(pid: string): Promise<FileEntryDTO[]> {
  return (await api.get<FileEntryDTO[]>(`/projects/${pid}/files`)).data
}

export async function getIngestResult(pid: string, fileId: string): Promise<IngestResultDTO> {
  return (await api.get<IngestResultDTO>(`/projects/${pid}/ingest_result/${fileId}`)).data
}

export async function listProposals(pid: string, fileId: string, refresh = false): Promise<ProposalDTO[]> {
  return (await api.get<ProposalDTO[]>(`/projects/${pid}/cleansing/proposals`, {
    params: { file_id: fileId, refresh },
    timeout: 300_000,
  })).data
}

export async function updateProposal(pid: string, proposalId: string, patch: Partial<ProposalDTO>): Promise<ProposalDTO> {
  return (await api.patch<ProposalDTO>(`/projects/${pid}/cleansing/proposals/${proposalId}`, patch)).data
}

export async function applyCleansing(pid: string, fileId: string): Promise<{ snapshot_id: string; processed_path: string; rows_before: number; rows_after: number; applied: unknown[] }> {
  return (await api.post(`/projects/${pid}/cleansing/apply`, { file_id: fileId })).data
}

export async function rollbackSnapshot(pid: string, snapshotId: string, fileId?: string): Promise<{ ok: boolean; restored_to?: string; error?: string }> {
  return (await api.post(`/projects/${pid}/cleansing/rollback`, { snapshot_id: snapshotId, file_id: fileId })).data
}

export async function listSnapshots(pid: string, fileId?: string): Promise<{ id: string; file_id: string; created_at: string; parquet_path: string }[]> {
  return (await api.get(`/projects/${pid}/cleansing/snapshots`, { params: fileId ? { file_id: fileId } : {} })).data
}

export async function getPipelineYaml(pid: string, fileId?: string): Promise<string> {
  const r = await api.get<{ yaml: string }>(`/projects/${pid}/cleansing/pipeline`, { params: fileId ? { file_id: fileId } : {} })
  return r.data.yaml
}

export async function postPipelineYaml(pid: string, yaml: string, targetFileId: string): Promise<{ imported: number }> {
  return (await api.post(`/projects/${pid}/cleansing/pipeline`, { yaml, target_file_id: targetFileId })).data
}

export async function getAudit(pid: string): Promise<{ timestamp: string; action: string; file_id: string; detail: Record<string, unknown> }[]> {
  return (await api.get(`/projects/${pid}/cleansing/audit`)).data
}

export async function getPreview(pid: string, fileId: string, n = 50): Promise<{ columns: string[]; rows: string[][]; n_rows_returned: number }> {
  return (await api.get(`/projects/${pid}/cleansing/preview`, { params: { file_id: fileId, n } })).data
}

export default api
