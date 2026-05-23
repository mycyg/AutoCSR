export type ReportPanel = 'reader' | 'plan' | 'chat' | 'comments' | 'markers' | 'diff' | 'status' | 'terms'

export interface ReportLinkOptions {
  panel?: ReportPanel
  highlight?: string
}

const PANEL_SET = new Set<ReportPanel>([
  'reader', 'plan', 'chat', 'comments', 'markers', 'diff', 'status', 'terms',
])

export function reportDeepLink(pid: string, nodeId: string, opts: ReportLinkOptions = {}): string {
  const params = new URLSearchParams()
  params.set('node', nodeId)
  if (opts.panel && opts.panel !== 'reader') params.set('panel', opts.panel)
  if (opts.highlight) params.set('highlight', opts.highlight)
  return `/p/${encodeURIComponent(pid)}/report?${params.toString()}`
}

export function normalizeReportPanel(value: unknown): ReportPanel | null {
  const raw = Array.isArray(value) ? value[0] : value
  const panel = String(raw || '')
  return PANEL_SET.has(panel as ReportPanel) ? panel as ReportPanel : null
}

export function normalizeNodeQuery(query: Record<string, unknown>): string {
  const raw = query.node ?? query.node_id
  const value = Array.isArray(raw) ? raw[0] : raw
  return value ? String(value) : ''
}
