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

// -- M3: analysis & outline --------------------------------------------------

export interface StatBlockSummaryDTO {
  id: string
  project_id: string
  analysis_type: 'descriptive' | 'inferential' | 'survival' | 'safety' | 'custom'
  title: string
  source_files: string[]
  created_at: string
  ref_code: string
  n_rows: number | null
  n_cols: number | null
}

export interface StatBlockDTO extends StatBlockSummaryDTO {
  params: Record<string, unknown>
  result_json: Record<string, unknown>
  markdown_table: string
  notes: string[]
}

export async function triggerAutoAnalysis(pid: string): Promise<{ started: boolean; status: string; blocks?: StatBlockSummaryDTO[] }> {
  return (await api.post(`/projects/${pid}/analysis/auto`, {}, { timeout: 300_000 })).data
}

export async function runAnalysis(pid: string, type: string, params: Record<string, unknown>): Promise<{ id: string; block: StatBlockDTO }> {
  return (await api.post(`/projects/${pid}/analysis/run`, { type, params }, { timeout: 180_000 })).data
}

export async function listStats(pid: string, analysisType?: string, q?: string): Promise<StatBlockSummaryDTO[]> {
  return (await api.get(`/projects/${pid}/stats`, { params: { analysis_type: analysisType, q } })).data
}

export async function getStat(pid: string, statId: string): Promise<StatBlockDTO> {
  return (await api.get(`/projects/${pid}/stats/${statId}`)).data
}

export async function deleteStat(pid: string, statId: string): Promise<{ ok: boolean }> {
  return (await api.delete(`/projects/${pid}/stats/${statId}`)).data
}

// -- M8: data ask (analyst agent) -------------------------------------------

export interface AskResponseDTO {
  stat_block: StatBlockDTO
  sandbox_run_id: string
  llm_meta: LLMMetaDTO
}

export interface AskHistoryEntryDTO {
  stat_id: string
  ts: number
  query: string
  scope: string
  sandbox_run_id: string
  expected_output_type: string
  ok: boolean
}

export async function askData(
  pid: string, query: string, scope: string = 'all',
): Promise<AskResponseDTO> {
  return (await api.post(`/projects/${pid}/ask`,
    { query, scope }, { timeout: 240_000 })).data
}

export async function getAskHistory(pid: string): Promise<AskHistoryEntryDTO[]> {
  return (await api.get(`/projects/${pid}/ask/history`)).data
}

export interface OutlineNodeDTO {
  id: string
  title: string
  principle_ref: string
  level: number
  status: 'pending' | 'writing' | 'done' | 'editing'
  stat_hints: string[]
  stat_refs: string[]
  literature_refs: string[]
  notes: string
  project_specific: boolean
  children: OutlineNodeDTO[]
}

export interface OutlineDTO {
  project_id: string
  principle_id: string
  version: number
  root_sections: OutlineNodeDTO[]
  created_at: string
  updated_at: string
  notes: string[]
}

export async function buildOutline(pid: string, principleId: string): Promise<{ started: boolean; status: string; version: number | null; n_nodes: number }> {
  return (await api.post(`/projects/${pid}/outline/build`, { principle_id: principleId }, { timeout: 600_000 })).data
}

export async function getOutline(pid: string): Promise<OutlineDTO> {
  return (await api.get(`/projects/${pid}/outline`)).data
}

export async function patchOutlineNode(pid: string, nodeId: string, patch: Partial<OutlineNodeDTO>): Promise<OutlineNodeDTO> {
  return (await api.patch(`/projects/${pid}/outline/nodes/${nodeId}`, patch)).data
}

export async function addOutlineChild(pid: string, parentId: string, title: string, notes?: string): Promise<OutlineNodeDTO> {
  return (await api.post(`/projects/${pid}/outline/nodes/${parentId}/children`, { title, notes })).data
}

export async function deleteOutlineNode(pid: string, nodeId: string): Promise<{ ok: boolean }> {
  return (await api.delete(`/projects/${pid}/outline/nodes/${nodeId}`)).data
}

export async function listOutlineVersions(pid: string): Promise<number[]> {
  return (await api.get(`/projects/${pid}/outline/versions`)).data
}

export async function restoreOutlineVersion(pid: string, version: number): Promise<{ ok: boolean; version: number }> {
  return (await api.post(`/projects/${pid}/outline/restore/${version}`)).data
}

// -- M4: report writers ------------------------------------------------------

export interface CitationRefDTO {
  ref_code: string
  type: 'literature' | 'stat' | 'principle' | 'note'
  locator: string
  snippet: string
}

export interface LLMMetaDTO {
  model: string
  tokens_in: number
  tokens_out: number
  latency_ms: number
  via: string
}

export interface SectionDraftDTO {
  node_id: string
  title: string
  markdown: string
  citations: CitationRefDTO[]
  word_count: number
  generated_at: string
  llm_meta: LLMMetaDTO
  warnings: string[]
  status: 'draft' | 'harmonized' | 'error'
}

export interface DraftSummaryDTO {
  node_id: string
  title: string
  status: 'draft' | 'harmonized' | 'error'
  word_count: number
  n_citations: number
  generated_at: string | null
  warnings: string[]
}

export interface ReportStatusDTO {
  project_id: string
  outline_version: number | null
  leaves_total: number
  leaves_done: number
  leaves_errored: number
  current_phase: 'idle' | 'background' | 'results' | 'discussion' | 'harmonize' | 'done' | 'error'
  harmonized: boolean
  total_tokens: { input: number; output: number }
  total_words: number
  last_event_at: string | null
  error: string | null
  sections: { node_id: string; title: string; status: string; words: number; error?: string }[]
}

export async function generateReport(pid: string, harmonize = true, leafLimit?: number): Promise<{ started: boolean }> {
  return (await api.post(`/projects/${pid}/report/generate`, {
    harmonize, leaf_limit: leafLimit,
  })).data
}

export async function getReportStatus(pid: string): Promise<ReportStatusDTO> {
  return (await api.get(`/projects/${pid}/report/status`)).data
}

export async function listDrafts(pid: string): Promise<DraftSummaryDTO[]> {
  return (await api.get(`/projects/${pid}/report/drafts`)).data
}

export async function getDraft(pid: string, nodeId: string): Promise<SectionDraftDTO> {
  return (await api.get(`/projects/${pid}/report/drafts/${nodeId}`)).data
}

export async function regenerateDraft(pid: string, nodeId: string, extra?: string): Promise<SectionDraftDTO> {
  return (await api.post(`/projects/${pid}/report/regenerate/${nodeId}`, { extra_instructions: extra ?? '' }, { timeout: 300_000 })).data
}

export async function getTerminology(pid: string): Promise<Record<string, string>> {
  return (await api.get(`/projects/${pid}/terminology`)).data
}

export async function patchTerminology(pid: string, terms: Record<string, string>): Promise<Record<string, string>> {
  return (await api.patch(`/projects/${pid}/terminology`, terms)).data
}

// -- M5: chat editor + version rollback --------------------------------------

export interface PatchDTO {
  op: 'replace_section' | 'insert_paragraph' | 'replace_paragraph' | 'patch_field'
  target: number | string | null
  before: string
  after: string
  applied: boolean
  note: string
}

export interface ChatMessageDTO {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  patches: PatchDTO[]
  ts: string
  meta?: Record<string, unknown>
}

export interface ChatTurnResultDTO {
  assistant_message: ChatMessageDTO
  patches: PatchDTO[]
  new_version: number | null
  new_warnings: string[]
}

export async function postChat(pid: string, nodeId: string, message: string): Promise<ChatTurnResultDTO> {
  return (await api.post(`/projects/${pid}/chapters/${nodeId}/chat`,
    { message }, { timeout: 300_000 })).data
}

export async function getChatHistory(pid: string, nodeId: string): Promise<ChatMessageDTO[]> {
  return (await api.get(`/projects/${pid}/chapters/${nodeId}/chat`)).data
}

export async function deleteChatMessage(pid: string, nodeId: string, msgId: string): Promise<{ ok: boolean }> {
  return (await api.delete(`/projects/${pid}/chapters/${nodeId}/chat/${msgId}`)).data
}

export async function listSectionVersions(pid: string, nodeId: string): Promise<number[]> {
  return (await api.get(`/projects/${pid}/report/drafts/${nodeId}/versions`)).data
}

export async function rollbackSection(pid: string, nodeId: string, version: number): Promise<SectionDraftDTO> {
  return (await api.post(`/projects/${pid}/report/drafts/${nodeId}/rollback/${version}`)).data
}

// -- M5: DOCX export ---------------------------------------------------------

export interface ExportOptions {
  include_compliance_note?: boolean
  include_toc?: boolean
  include_appendix_cleansing?: boolean
  include_appendix_analysis?: boolean
}

export interface ExportResultDTO {
  ok: boolean
  filename: string
  size_bytes: number
  n_sections: number
  n_citations: number
  generated_at: string
}

export interface ExportEntryDTO {
  filename: string
  path: string
  size_bytes: number
  n_sections?: number
  n_citations?: number
  created_at: string
}

export async function exportDocx(pid: string, opts: ExportOptions = {}): Promise<ExportResultDTO> {
  return (await api.post(`/projects/${pid}/export/docx`, opts, { timeout: 600_000 })).data
}

export async function listExports(pid: string): Promise<ExportEntryDTO[]> {
  return (await api.get(`/projects/${pid}/exports`)).data
}

export async function deleteExport(pid: string, filename: string): Promise<{ ok: boolean }> {
  return (await api.delete(`/projects/${pid}/export/docx/${encodeURIComponent(filename)}`)).data
}

export function exportDownloadUrl(pid: string, filename: string): string {
  return `/api/projects/${pid}/export/docx/${encodeURIComponent(filename)}`
}

export async function updateDraftMarkdown(pid: string, nodeId: string, markdown: string): Promise<{ draft: SectionDraftDTO; version: number }> {
  return (await api.put(`/projects/${pid}/report/drafts/${nodeId}/markdown`, { markdown },
    { timeout: 60_000 })).data
}

export default api
