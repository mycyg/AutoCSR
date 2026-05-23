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
  tags?: string[]
  archived?: boolean
  last_opened_at?: string | null
  language?: string
  notes?: string | null
  template_id?: string | null
}

export interface CreateProjectPayload {
  name: string
  principle_id?: string | null
  language?: string | null
  notes?: string | null
  template_id?: string | null
}

export interface ProjectUpdatePayload {
  name?: string
  tags?: string[]
  archived?: boolean
  notes?: string | null
  language?: string | null
  principle_id?: string | null
}

export interface ProjectTemplateDTO {
  id: string
  name: string
  description: string
  principle_id: string | null
  language: string
  tags: string[]
  notes: string | null
  readme: string | null
}

export interface ProjectListQuery {
  search?: string
  tag?: string
  archived?: boolean
  sort?: 'last_opened' | 'created' | 'name'
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

export async function listProjects(q: ProjectListQuery = {}): Promise<ProjectDTO[]> {
  const params: Record<string, string> = {}
  if (q.search) params.search = q.search
  if (q.tag) params.tag = q.tag
  if (q.archived !== undefined) params.archived = String(q.archived)
  if (q.sort) params.sort = q.sort
  return (await api.get<ProjectDTO[]>('/projects', { params })).data
}
export async function createProject(payload: CreateProjectPayload): Promise<ProjectDTO> {
  return (await api.post<ProjectDTO>('/projects', payload)).data
}
export async function createProjectFromTemplate(
  templateId: string, name: string,
): Promise<ProjectDTO> {
  return (await api.post<ProjectDTO>(`/projects/from_template/${templateId}`, { name })).data
}
export async function updateProject(id: string, patch: ProjectUpdatePayload): Promise<ProjectDTO> {
  return (await api.patch<ProjectDTO>(`/projects/${id}`, patch)).data
}
export async function deleteProject(id: string, force = false): Promise<void> {
  await api.delete(`/projects/${id}`, { params: { force: String(force) } })
}
export async function listProjectTemplates(): Promise<ProjectTemplateDTO[]> {
  return (await api.get<ProjectTemplateDTO[]>('/templates')).data
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
  analysis_type:
    | 'descriptive' | 'inferential' | 'survival' | 'safety' | 'custom'
    | 'multitest' | 'subgroup' | 'sensitivity' | 'consort' | 'baseline_balance'
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

// ============================================================================
// V2-C: M10 (plan + review) + M11 (comments + markers + diff + alerts)
// ============================================================================

// ---- Plan ------------------------------------------------------------------

export interface PlanPointDTO {
  id: string
  text: string
  evidence_hints: string[]
  stat_refs_hint: string[]
  status: 'pending' | 'accepted' | 'edited'
}

export interface SectionPlanDTO {
  node_id: string
  title: string
  points: PlanPointDTO[]
  notes: string
  version: number
  created_at: string
  updated_at: string
  llm_meta: { model: string; tokens_in: number; tokens_out: number; via: string }
}

export async function createPlan(pid: string, nodeId: string,
                                  opts: { max_points?: number } = {}): Promise<SectionPlanDTO> {
  return (await api.post(`/projects/${pid}/report/plan/${nodeId}`, opts,
    { timeout: 300_000 })).data
}

export async function getPlan(pid: string, nodeId: string): Promise<SectionPlanDTO | null> {
  try {
    return (await api.get(`/projects/${pid}/report/plan/${nodeId}`)).data
  } catch (e: unknown) {
    const err = e as { response?: { status?: number } }
    if (err?.response?.status === 404) return null
    throw e
  }
}

export async function patchPlan(pid: string, nodeId: string,
                                  body: { points?: PlanPointDTO[]; notes?: string }): Promise<SectionPlanDTO> {
  return (await api.patch(`/projects/${pid}/report/plan/${nodeId}`, body)).data
}

export async function refineFromPlan(pid: string, nodeId: string): Promise<SectionDraftDTO> {
  return (await api.post(`/projects/${pid}/report/refine/${nodeId}`, {},
    { timeout: 300_000 })).data
}

// ---- Review ----------------------------------------------------------------

export interface ReviewIssueDTO {
  id: string
  severity: 'error' | 'warn' | 'info'
  location: { node_id?: string; char_range?: [number, number]; extra?: Record<string, string> }
  message: string
  suggestion: string
  checker: string
  ignored: boolean
}

export interface ReviewCheckerStatusDTO {
  name: string
  ok: boolean
  issues_count: number
  error: string | null
  duration_ms: number
}

export interface ReviewResultDTO {
  project_id: string
  passed: boolean
  issues: ReviewIssueDTO[]
  checkers: ReviewCheckerStatusDTO[]
  created_at: string | null
  ignored_issue_ids: string[]
}

export interface ReviewHistoryDTO {
  created_at: string
  passed: boolean
  n_errors: number
  n_warns: number
  n_infos: number
}

export async function startReview(pid: string): Promise<ReviewResultDTO> {
  return (await api.post(`/projects/${pid}/review`, { sync: true },
    { timeout: 300_000 })).data
}

export async function getReview(pid: string): Promise<ReviewResultDTO> {
  return (await api.get(`/projects/${pid}/review`)).data
}

export async function getReviewHistory(pid: string): Promise<ReviewHistoryDTO[]> {
  return (await api.get(`/projects/${pid}/review/history`)).data
}

export async function patchReviewIssue(pid: string, issueId: string,
                                         ignored: boolean): Promise<ReviewResultDTO> {
  return (await api.patch(`/projects/${pid}/review/issues/${issueId}`, { ignored })).data
}

// ---- Comments --------------------------------------------------------------

export interface CommentDTO {
  id: string
  project_id: string
  node_id: string
  paragraph_idx: number
  char_range: [number, number]
  author: string
  body: string
  status: 'open' | 'resolved' | 'rejected'
  created_at: string
  applied_in_draft_version: number | null
}

export interface CommentApplyResultDTO {
  project_id: string
  applied_count: number
  skipped_count: number
  new_versions: Record<string, number>
  warnings: string[]
}

export async function addComment(pid: string, nodeId: string,
                                   paragraphIdx: number, charRange: [number, number],
                                   body: string): Promise<CommentDTO> {
  return (await api.post(`/projects/${pid}/comments`, {
    node_id: nodeId, paragraph_idx: paragraphIdx, char_range: charRange, body,
  })).data
}

export async function listComments(pid: string,
                                     opts: { node_id?: string; status?: string } = {}): Promise<CommentDTO[]> {
  return (await api.get(`/projects/${pid}/comments`, { params: opts })).data
}

export async function patchComment(pid: string, cid: string,
                                     body: { status?: string; body?: string }): Promise<CommentDTO> {
  return (await api.patch(`/projects/${pid}/comments/${cid}`, body)).data
}

export async function deleteComment(pid: string, cid: string): Promise<{ ok: boolean }> {
  return (await api.delete(`/projects/${pid}/comments/${cid}`)).data
}

export async function applyComments(pid: string): Promise<CommentApplyResultDTO> {
  return (await api.post(`/projects/${pid}/comments/apply`, {}, { timeout: 300_000 })).data
}

// ---- Markers ---------------------------------------------------------------

export interface MarkerDTO {
  id: string
  node_id: string
  type: 'important' | 'todo' | 'question' | 'risk'
  color: string
  range: [number, number]
  note: string
  created_at: string
}

export async function listMarkers(pid: string, nodeId?: string): Promise<MarkerDTO[]> {
  return (await api.get(`/projects/${pid}/markers`,
    { params: nodeId ? { node_id: nodeId } : {} })).data
}

export async function addMarker(pid: string,
                                  nodeId: string,
                                  type: 'important' | 'todo' | 'question' | 'risk',
                                  range: [number, number],
                                  note = ''): Promise<MarkerDTO> {
  return (await api.post(`/projects/${pid}/markers`, {
    node_id: nodeId, type, range, note,
  })).data
}

export async function deleteMarker(pid: string, markerId: string,
                                     nodeId: string): Promise<{ ok: boolean }> {
  return (await api.delete(`/projects/${pid}/markers/${markerId}`,
    { params: { node_id: nodeId } })).data
}

// ---- Diff ------------------------------------------------------------------

export interface DiffBlockDTO {
  op: 'equal' | 'insert' | 'delete' | 'replace'
  v1_range: [number, number]
  v2_range: [number, number]
  v1_text: string
  v2_text: string
}

export interface DiffResultDTO {
  node_id: string
  v1: number | null
  v2: number | null
  blocks: DiffBlockDTO[]
  summary: Record<string, number>
}

export async function getDraftVersions(pid: string, nodeId: string): Promise<number[]> {
  return (await api.get(`/projects/${pid}/drafts/${nodeId}/versions`)).data
}

export async function getDraftDiff(pid: string, nodeId: string,
                                     v1?: number, v2?: number): Promise<DiffResultDTO> {
  const params: Record<string, number> = {}
  if (v1 !== undefined) params.v1 = v1
  if (v2 !== undefined) params.v2 = v2
  return (await api.get(`/projects/${pid}/drafts/${nodeId}/diff`, { params })).data
}

// ---- Alerts ----------------------------------------------------------------

export interface AlertItemDTO {
  severity: 'error' | 'warn' | 'info'
  source: string
  message: string
  link: string
  [k: string]: unknown
}

export interface AlertsPayloadDTO {
  counts: { error: number; warn: number; info: number }
  items: AlertItemDTO[]
}

export async function getAlerts(pid: string): Promise<AlertsPayloadDTO> {
  return (await api.get(`/projects/${pid}/alerts`)).data
}

export async function invalidateAlerts(pid: string): Promise<{ ok: boolean }> {
  return (await api.post(`/projects/${pid}/alerts/invalidate`, {})).data
}

// ---------------------------------------------------------------------------
// M13 — DOCX templates + CSR reverse import + state summary
// ---------------------------------------------------------------------------

export interface DocxTemplateConfigDTO {
  preset: 'standard' | 'pharma' | 'academic' | 'regulatory'
  fonts: { heading: string; body: string; code: string }
  sizes: { h1: number; h2: number; h3: number; body: number }
  colors: { heading: string; body: string; link: string }
  margins: { top: number; bottom: number; left: number; right: number }
  line_spacing: number
  toc_depth: number
  header_text: string
  footer_text: string
  watermark: string
  show_ai_provenance: boolean
  custom_template_id: string | null
}

export interface UploadedTemplateDTO {
  id: string
  filename: string
  path: string
  placeholders: string[]
  size_bytes: number
}

export async function getExportTemplateConfig(pid: string): Promise<DocxTemplateConfigDTO> {
  return (await api.get(`/projects/${pid}/export/template_config`)).data
}
export async function patchExportTemplateConfig(
  pid: string, patch: Partial<DocxTemplateConfigDTO> & { preset_apply?: string },
): Promise<DocxTemplateConfigDTO> {
  return (await api.patch(`/projects/${pid}/export/template_config`, patch)).data
}
export async function listExportTemplates(pid: string): Promise<UploadedTemplateDTO[]> {
  return (await api.get(`/projects/${pid}/export/templates`)).data
}
export async function uploadExportTemplate(pid: string, file: File): Promise<UploadedTemplateDTO> {
  const fd = new FormData()
  fd.append('file', file, file.name)
  const r = await api.post(`/projects/${pid}/export/template_upload`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return r.data
}
export async function listExportPresets(): Promise<(DocxTemplateConfigDTO & { id: string })[]> {
  return (await api.get('/export/presets')).data
}

export interface ImportCsrSectionDTO {
  node_id: string
  title: string
  level: number
  markdown: string
  children: ImportCsrSectionDTO[]
  word_count: number
}
export interface ImportCsrResultDTO {
  import_id: string
  project_id: string
  source_filename: string
  n_headings: number
  n_paragraphs: number
  n_tables: number
  confidence: number
  unmapped_paragraphs: number
  root_sections: ImportCsrSectionDTO[]
}

export async function importCsrDocx(pid: string, file: File): Promise<ImportCsrResultDTO> {
  const fd = new FormData()
  fd.append('file', file, file.name)
  const r = await api.post(`/projects/${pid}/import/csr`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return r.data
}
export async function commitCsrImport(pid: string, importId: string, principleId?: string): Promise<{
  ok: boolean; import_id: string; n_outline_nodes: number; n_drafts: number
}> {
  return (await api.post(`/projects/${pid}/import/csr/commit`, {
    import_id: importId,
    principle_id: principleId || null,
  })).data
}

export interface StateSummaryDTO {
  steps: Record<string, { done?: number; pending?: number; error?: number; info?: number }>
  current_step: string
}
export async function getStateSummary(pid: string): Promise<StateSummaryDTO> {
  return (await api.get(`/projects/${pid}/state_summary`)).data
}

// ---------------------------------------------------------------------------
// V2-E (M14) — coding + advanced analysis + TLF export
// ---------------------------------------------------------------------------

export interface CodingSystemDTO {
  id: string
  name: string
  version: string
  source: string
  license: string
  available: boolean
  n_codes: number
  notes: string
}
export interface CodingCandidateDTO {
  system: string
  code: string
  preferred_term: string
  hierarchy: string[]
  score: number
}
export async function listCodingSystems(): Promise<CodingSystemDTO[]> {
  return (await api.get('/coding/systems')).data
}
export async function lookupCoding(
  system: string, term: string, topK = 5,
): Promise<{ system: string; term: string; candidates: CodingCandidateDTO[] }> {
  return (await api.post('/coding/lookup', { system, term, top_k: topK })).data
}
export async function lookupCodingMany(
  system: string, terms: string[], topK = 3,
): Promise<{ system: string; results: Record<string, CodingCandidateDTO[]> }> {
  return (await api.post('/coding/lookup_many', { system, terms, top_k: topK })).data
}

export interface AdvancedStatBlockDTO {
  id: string
  block?: Record<string, unknown>
}

export async function runMultitest(
  pid: string, pValues: number[], method = 'fdr_bh', labels?: string[],
): Promise<AdvancedStatBlockDTO> {
  return (await api.post(`/projects/${pid}/analysis/multitest`,
    { p_values: pValues, method, labels })).data
}
export async function runSubgroup(
  pid: string, outcomeCol: string, groupCol: string,
  subgroupCols: string[], fileId?: string,
): Promise<AdvancedStatBlockDTO> {
  return (await api.post(`/projects/${pid}/analysis/subgroup`,
    { outcome_col: outcomeCol, group_col: groupCol,
      subgroup_cols: subgroupCols, file_id: fileId })).data
}
export async function runSensitivity(
  pid: string, outcomeCol: string, groupCol: string,
  methods: string[] = ['itt','pp','locf','mmrm'], fileId?: string,
): Promise<{ ids: string[]; n: number }> {
  return (await api.post(`/projects/${pid}/analysis/sensitivity`,
    { outcome_col: outcomeCol, group_col: groupCol,
      methods, file_id: fileId })).data
}
export async function runConsort(pid: string): Promise<AdvancedStatBlockDTO> {
  return (await api.post(`/projects/${pid}/analysis/consort`, {})).data
}
export async function runBaselineBalance(
  pid: string, groupCol: string, vars: string[], fileId?: string,
): Promise<AdvancedStatBlockDTO> {
  return (await api.post(`/projects/${pid}/analysis/baseline_balance`,
    { group_col: groupCol, vars, file_id: fileId })).data
}

export interface TLFExportRecordDTO {
  filename: string
  size_bytes: number
  created_at: string
  path: string
}
export async function runTlfExport(pid: string): Promise<{ filename: string; size_bytes: number }> {
  return (await api.post(`/projects/${pid}/export/tlf`, null, { timeout: 300_000 })).data
}
export async function listTlfExports(pid: string): Promise<TLFExportRecordDTO[]> {
  return (await api.get(`/projects/${pid}/exports/tlf`)).data
}
export function tlfDownloadUrl(pid: string, filename: string): string {
  return `/api/projects/${pid}/exports/tlf/${encodeURIComponent(filename)}`
}

// ---------------------------------------------------------------------------
// V2-F M15 — audit + signature + safety
// ---------------------------------------------------------------------------

export interface AuditEventDTO {
  id: string
  ts: string
  actor: string
  action: string
  resource_type: string
  resource_id: string
  before_hash: string | null
  after_hash: string | null
  reason: string | null
  ip: string | null
  extra: Record<string, unknown>
  prev_event_hash: string
  curr_event_hash: string
}

export interface AuditChainResultDTO {
  verified: boolean
  total: number
  broken_at: string | null
  error: string | null
}

export interface SignatureDTO {
  id: string
  ts: string
  signer: string
  reason: string
  signed_artifact_type: string
  signed_artifact_id: string
  signed_artifact_hash: string
  public_key_id: string
  signature: string
  algorithm: 'ed25519' | 'fallback-hmac'
}

export async function listAuditEvents(pid: string,
                                       params: { actor?: string; action?: string; resource_type?: string; limit?: number } = {}): Promise<AuditEventDTO[]> {
  return (await api.get(`/projects/${pid}/audit`, { params })).data
}
export async function verifyAuditChain(pid: string): Promise<AuditChainResultDTO> {
  return (await api.get(`/projects/${pid}/audit/verify`)).data
}
export async function signArtifact(pid: string, body: {
  artifact_type: string; artifact_id: string; reason?: string; signer?: string
}): Promise<SignatureDTO> {
  return (await api.post(`/projects/${pid}/sign`, body)).data
}
export async function listSignatures(pid: string): Promise<SignatureDTO[]> {
  return (await api.get(`/projects/${pid}/signatures`)).data
}
export async function verifySignature(pid: string, sigId: string): Promise<{ id: string; verified: boolean }> {
  return (await api.get(`/projects/${pid}/signatures/${sigId}/verify`)).data
}

// Blinding + lock
export interface BlindingDTO {
  blinded: boolean
  arm_map: Record<string, string>
  last_changed_at: string | null
  signature_id: string | null
}
export interface LockStateDTO {
  locked: boolean
  reason: string
  ts: string | null
  signature_id: string | null
}
export async function getBlinding(pid: string): Promise<BlindingDTO> {
  return (await api.get(`/projects/${pid}/state/blinding`)).data
}
export async function setBlinding(pid: string, blinded: boolean,
                                    sigId?: string, arms?: string[]): Promise<BlindingDTO> {
  return (await api.patch(`/projects/${pid}/state/blinding`,
                            { blinded, signature_id: sigId, arms })).data
}
export async function getLock(pid: string): Promise<LockStateDTO> {
  return (await api.get(`/projects/${pid}/state/lock`)).data
}
export async function postLock(pid: string, reason: string,
                                 sigId: string): Promise<LockStateDTO> {
  return (await api.post(`/projects/${pid}/state/lock`,
                           { reason, signature_id: sigId })).data
}
export async function deleteLock(pid: string, sigId: string): Promise<LockStateDTO> {
  return (await api.delete(`/projects/${pid}/state/lock`,
                             { headers: { 'X-Signature-Id': sigId } })).data
}

// ---------------------------------------------------------------------------
// V2-F M16 — multi-reviewer + collab + queue
// ---------------------------------------------------------------------------

export interface MultiReviewDTO {
  project_id: string
  statistician: ReviewResultDTO | null
  medical: ReviewResultDTO | null
  regulatory: ReviewResultDTO | null
  combined_count: Record<string, number>
  created_at: string | null
}
export async function runMultiReview(pid: string): Promise<MultiReviewDTO> {
  return (await api.post(`/projects/${pid}/multi_review`, { sync: true },
                          { timeout: 300_000 })).data
}
export async function getMultiReview(pid: string): Promise<MultiReviewDTO> {
  return (await api.get(`/projects/${pid}/multi_review`)).data
}

export interface UserDTO {
  id: string
  name: string
  email: string
  role: 'author' | 'reviewer' | 'approver' | 'admin'
}
export async function listUsers(): Promise<UserDTO[]> {
  return (await api.get(`/users`)).data
}
export async function whoami(asUser?: string): Promise<UserDTO> {
  const headers = asUser ? { 'X-User-Id': asUser } : {}
  return (await api.get(`/users/me`, { headers })).data
}

export interface ReviewTaskCommentDTO {
  id: string
  author: string
  body: string
  ts: string
}
export interface ReviewTaskDTO {
  id: string
  project_id: string
  node_id: string | null
  source: 'manual' | 'issue' | 'comment' | 'multi_review'
  source_ref: string | null
  assignee: string
  creator: string
  due_date: string | null
  status: 'open' | 'in_progress' | 'resolved' | 'wont_fix'
  severity: 'error' | 'warn' | 'info'
  title: string
  body: string
  comments: ReviewTaskCommentDTO[]
  created_at: string
  updated_at: string
}
export async function listTasks(pid: string,
                                 params: { assignee?: string; status?: string; severity?: string; node_id?: string } = {}): Promise<ReviewTaskDTO[]> {
  return (await api.get(`/projects/${pid}/tasks`, { params })).data
}
export async function createTask(pid: string, body: {
  assignee: string; body: string; severity?: string; node_id?: string;
  title?: string; due_date?: string
}, asUser?: string): Promise<ReviewTaskDTO> {
  const headers = asUser ? { 'X-User-Id': asUser } : {}
  return (await api.post(`/projects/${pid}/tasks`, body, { headers })).data
}
export async function patchTask(pid: string, tid: string, patch: {
  status?: string; assignee?: string; body?: string; title?: string;
  severity?: string; comment?: string
}, asUser?: string): Promise<ReviewTaskDTO> {
  const headers = asUser ? { 'X-User-Id': asUser } : {}
  return (await api.patch(`/projects/${pid}/tasks/${tid}`, patch, { headers })).data
}
export async function resolveTask(pid: string, tid: string): Promise<ReviewTaskDTO> {
  return (await api.post(`/projects/${pid}/tasks/${tid}/resolve`)).data
}
export async function reopenTask(pid: string, tid: string): Promise<ReviewTaskDTO> {
  return (await api.post(`/projects/${pid}/tasks/${tid}/reopen`)).data
}
export async function taskFromIssue(pid: string, issueId: string, body: {
  assignee: string; due_date?: string
}): Promise<ReviewTaskDTO> {
  return (await api.post(`/projects/${pid}/tasks/from_issue/${issueId}`, body)).data
}
export async function taskFromComment(pid: string, cid: string, body: {
  assignee: string; due_date?: string
}): Promise<ReviewTaskDTO> {
  return (await api.post(`/projects/${pid}/tasks/from_comment/${cid}`, body)).data
}

// Project compare
export interface DiffResultDTO {
  pid_a: string
  pid_b: string
  mode: 'outline' | 'drafts'
  outline: Array<{ node_id: string; title: string; kind: string; notes: string }>
  drafts: Array<{ node_id: string; title: string; n_added: number; n_removed: number; diff: string }>
  summary: Record<string, number>
}
export async function compareProjects(pidA: string, pidB: string, by: 'outline' | 'drafts'): Promise<DiffResultDTO> {
  return (await api.post(`/projects/compare`, { pid_a: pidA, pid_b: pidB, by })).data
}

// Queue
export interface QueueTaskRecordDTO {
  id: string
  task_type: string
  project_id: string | null
  status: string
  progress: number
  message: string
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  backend: string
}
export async function getQueueTaskStatus(taskId: string): Promise<QueueTaskRecordDTO> {
  return (await api.get(`/tasks/${taskId}/status`)).data
}

export default api
