/**
 * Confirmation prompts for destructive operations.
 *
 * Wraps ElMessageBox.confirm() with consistent i18n + a resource_name
 * substitution. Always returns a Promise<boolean> so callers can write:
 *
 *   if (!await confirmAction('projects.delete_confirm',
 *                            { resource_name: row.name })) return
 *
 * The dialog rejects on cancel which we catch and resolve to false.
 */
import { ElMessageBox } from 'element-plus'
import { i18n } from '@/i18n'

export interface ConfirmOptions {
  title?: string
  type?: 'warning' | 'error' | 'info' | 'success'
  resource_name?: string
  confirm_text?: string
  cancel_text?: string
  /** When true, the confirm button uses Element Plus' danger style. */
  danger?: boolean
}

export async function confirmAction(messageOrKey: string,
                                     options: ConfirmOptions = {}): Promise<boolean> {
  const params: Record<string, unknown> = {}
  if (options.resource_name) params.name = options.resource_name
  let message = messageOrKey
  try {
    const translated = i18n.global.t(messageOrKey, params)
    if (translated && translated !== messageOrKey) message = translated
  } catch { /* keep raw string */ }
  let title = options.title
  if (title) {
    try { title = i18n.global.t(title) } catch { /* keep raw */ }
  } else {
    title = i18n.global.t('common.help')
  }
  const confirmText = options.confirm_text
    ? i18n.global.t(options.confirm_text)
    : i18n.global.t('common.ok')
  const cancelText = options.cancel_text
    ? i18n.global.t(options.cancel_text)
    : i18n.global.t('common.cancel')
  try {
    await ElMessageBox.confirm(message, title, {
      type: options.type || 'warning',
      confirmButtonText: confirmText,
      cancelButtonText: cancelText,
      confirmButtonClass: options.danger ? 'el-button--danger' : '',
      autofocus: false,
    })
    return true
  } catch {
    return false
  }
}

export function useConfirm(): { confirmAction: typeof confirmAction } {
  return { confirmAction }
}
