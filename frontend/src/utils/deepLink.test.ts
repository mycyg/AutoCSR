import { describe, expect, it } from 'vitest'
import { normalizeNodeQuery, normalizeReportPanel, reportDeepLink } from './deepLink'

describe('report deep links', () => {
  it('builds the canonical node/panel/highlight query', () => {
    expect(reportDeepLink('p 1', '11.4.2', {
      panel: 'comments',
      highlight: 'task:abc',
    })).toBe('/p/p%201/report?node=11.4.2&panel=comments&highlight=task%3Aabc')
  })

  it('keeps reader links compact', () => {
    expect(reportDeepLink('p1', '11.4', { panel: 'reader' }))
      .toBe('/p/p1/report?node=11.4')
  })

  it('accepts legacy node_id while preferring node', () => {
    expect(normalizeNodeQuery({ node_id: 'legacy' })).toBe('legacy')
    expect(normalizeNodeQuery({ node: 'new', node_id: 'legacy' })).toBe('new')
  })

  it('rejects unknown panels', () => {
    expect(normalizeReportPanel('comments')).toBe('comments')
    expect(normalizeReportPanel('unknown')).toBeNull()
  })
})
