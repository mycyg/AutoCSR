/**
 * Unified API error handling.
 *
 * Backend errors carry HTTP status + optional `{code, params, message}` JSON
 * body. We translate the code to an i18n key and route the resulting toast
 * to the appropriate severity bucket:
 *
 *   - info     → ElMessage info (auto-dismiss)
 *   - warn     → ElMessage warning (auto-dismiss)
 *   - error    → ElMessage error (sticky 8s)
 *   - critical → ElNotification error + console.error
 *
 * Components should call `handleApiError(e)` inside their catch blocks
 * instead of crafting a one-off ElMessage.error string.
 */
import { ElMessage, ElNotification } from 'element-plus'
import { i18n } from '@/i18n'

type Severity = 'info' | 'warn' | 'error' | 'critical'

export interface ErrorInfo {
  code: string
  message: string
  severity: Severity
  status?: number
}

interface CodeSpec { key: string; severity: Severity }

/* Core error code → i18n key mapping. Codes not listed here fall back to
 * the raw `message` value and `error` severity. */
export const ERROR_CODE_MAP: Record<string, CodeSpec> = {
  // Generic
  'unknown':                    { key: 'errors.unknown',                 severity: 'error' },
  'network_error':              { key: 'errors.network',                 severity: 'error' },
  'timeout':                    { key: 'errors.timeout',                 severity: 'warn' },
  'unauthorized':               { key: 'errors.unauthorized',            severity: 'error' },
  'forbidden':                  { key: 'errors.forbidden',               severity: 'error' },
  'not_found':                  { key: 'errors.not_found',               severity: 'warn' },
  'conflict':                   { key: 'errors.conflict',                severity: 'warn' },
  'rate_limited':               { key: 'errors.rate_limited',            severity: 'warn' },
  'server_error':               { key: 'errors.server_error',            severity: 'critical' },
  'validation_failed':          { key: 'errors.validation_failed',       severity: 'warn' },
  // Project
  'project_not_found':          { key: 'errors.project_not_found',       severity: 'error' },
  'project_locked':             { key: 'errors.project_locked',          severity: 'warn' },
  'must_archive_first':         { key: 'errors.must_archive_first',      severity: 'warn' },
  // Ingest
  'ingest_unknown_type':        { key: 'errors.ingest_unknown_type',     severity: 'warn' },
  'ingest_failed':              { key: 'errors.ingest_failed',           severity: 'error' },
  'unsupported_file':           { key: 'errors.unsupported_file',        severity: 'warn' },
  // Cleansing
  'cleansing_no_proposals':     { key: 'errors.cleansing_no_proposals',  severity: 'info' },
  'cleansing_apply_failed':     { key: 'errors.cleansing_apply_failed',  severity: 'error' },
  // Outline / report
  'outline_missing':            { key: 'errors.outline_missing',         severity: 'warn' },
  'report_in_progress':         { key: 'errors.report_in_progress',      severity: 'info' },
  'writer_failed':              { key: 'errors.writer_failed',           severity: 'error' },
  // Analysis
  'analysis_no_data':           { key: 'errors.analysis_no_data',        severity: 'warn' },
  'sandbox_error':              { key: 'errors.sandbox_error',           severity: 'error' },
  // Export
  'export_failed':              { key: 'errors.export_failed',           severity: 'error' },
  'template_invalid':           { key: 'errors.template_invalid',        severity: 'warn' },
  'ectd_missing_outline':       { key: 'errors.ectd_missing_outline',    severity: 'warn' },
  // Review / collab
  'review_already_running':     { key: 'errors.review_already_running',  severity: 'info' },
  'sign_chain_out_of_order':    { key: 'errors.sign_chain_out_of_order', severity: 'warn' },
  'sign_chain_already_done':    { key: 'errors.sign_chain_already_done', severity: 'info' },
  'audit_chain_broken':         { key: 'errors.audit_chain_broken',      severity: 'critical' },
  // Safety
  'hallucination_blocked':      { key: 'errors.hallucination_blocked',   severity: 'warn' },
  'pii_violation':              { key: 'errors.pii_violation',           severity: 'critical' },
}

function statusToCode(status: number | undefined): string {
  if (status === 401) return 'unauthorized'
  if (status === 403) return 'forbidden'
  if (status === 404) return 'not_found'
  if (status === 409) return 'conflict'
  if (status === 422) return 'validation_failed'
  if (status === 429) return 'rate_limited'
  if (status && status >= 500) return 'server_error'
  return 'unknown'
}

export function parseApiError(err: unknown): ErrorInfo {
  /* eslint-disable @typescript-eslint/no-explicit-any */
  const anyErr = err as any
  // Axios shape: err.response.data
  let status: number | undefined
  let body: any
  if (anyErr?.response) {
    status = anyErr.response.status
    body = anyErr.response.data
  } else if (anyErr?.code === 'ECONNABORTED') {
    return { code: 'timeout', message: i18n.global.t('errors.timeout'),
             severity: 'warn' }
  } else if (anyErr?.message === 'Network Error') {
    return { code: 'network_error', message: i18n.global.t('errors.network'),
             severity: 'error' }
  }
  let code: string | undefined
  let params: Record<string, unknown> = {}
  let detailMsg: string | undefined
  if (body && typeof body === 'object') {
    code = body.code || body.error_code
    params = body.params || body.context || {}
    detailMsg = body.message || body.detail || body.error
  }
  if (!code) code = statusToCode(status)
  const spec = ERROR_CODE_MAP[code] || { key: 'errors.unknown', severity: 'error' }
  let translated: string
  try {
    translated = i18n.global.t(spec.key, params)
  } catch {
    translated = detailMsg || code
  }
  if (translated === spec.key) translated = detailMsg || translated
  return { code, message: translated, severity: spec.severity, status }
}

export function handleApiError(err: unknown, fallbackI18nKey?: string): void {
  const info = parseApiError(err)
  let msg = info.message
  if (fallbackI18nKey && (!msg || msg === info.code)) {
    try { msg = i18n.global.t(fallbackI18nKey) } catch { /* keep msg */ }
  }
  if (info.severity === 'critical') {
    ElNotification({ type: 'error', title: i18n.global.t('errors.critical_title'),
                      message: msg, duration: 0 })
    // eslint-disable-next-line no-console
    console.error('[autocsr]', info.code, err)
  } else if (info.severity === 'error') {
    ElMessage({ type: 'error', message: msg, duration: 8000, showClose: true })
  } else if (info.severity === 'warn') {
    ElMessage({ type: 'warning', message: msg, duration: 5000, showClose: true })
  } else {
    ElMessage({ type: 'info', message: msg, duration: 4000 })
  }
}
