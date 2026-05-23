/**
 * Global keyboard shortcut bus.
 *
 * Components listen by name; `useShortcuts()` registers the global key
 * listener exactly once per app lifetime. Hot-reload safe.
 *
 * Supported names:
 *   - save     (Ctrl/Cmd + S)
 *   - search   (Ctrl/Cmd + K)
 *   - help     (Shift + ? / ?)
 *   - send     (Shift + Enter is intentionally a *no-op global* — components
 *              handle it locally in their input boxes; we don't intercept
 *              keystrokes inside textareas at all.)
 */
import { onMounted, onUnmounted } from 'vue'

type Handler = () => void

interface Slot {
  handlers: Set<Handler>
}

const slots: Record<string, Slot> = {
  save: { handlers: new Set() },
  search: { handlers: new Set() },
  help: { handlers: new Set() },
}

let installed = false

function isEditableTarget(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null
  if (!t) return false
  const tag = (t.tagName || '').toUpperCase()
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (t.isContentEditable) return true
  return false
}

function dispatch(name: keyof typeof slots): void {
  for (const h of slots[name].handlers) {
    try { h() } catch { /* ignore handler errors */ }
  }
}

function onKey(e: KeyboardEvent): void {
  const meta = e.ctrlKey || e.metaKey
  const key = (e.key || '').toLowerCase()
  if (meta && key === 's') {
    e.preventDefault()
    dispatch('save')
    return
  }
  if (meta && key === 'k') {
    e.preventDefault()
    dispatch('search')
    return
  }
  if (!meta && (e.key === '?' || (e.shiftKey && key === '/'))) {
    if (isEditableTarget(e)) return  // don't hijack typing
    e.preventDefault()
    dispatch('help')
  }
}

function ensureInstalled(): void {
  if (installed) return
  if (typeof window === 'undefined') return
  window.addEventListener('keydown', onKey, true)
  installed = true
}

export function useShortcuts(opts: {
  save?: Handler
  search?: Handler
  help?: Handler
} = {}): void {
  ensureInstalled()
  onMounted(() => {
    if (opts.save) slots.save.handlers.add(opts.save)
    if (opts.search) slots.search.handlers.add(opts.search)
    if (opts.help) slots.help.handlers.add(opts.help)
  })
  onUnmounted(() => {
    if (opts.save) slots.save.handlers.delete(opts.save)
    if (opts.search) slots.search.handlers.delete(opts.search)
    if (opts.help) slots.help.handlers.delete(opts.help)
  })
}

/**
 * Imperatively trigger shortcuts (used by the help modal etc.).
 */
export function triggerShortcut(name: 'save' | 'search' | 'help'): void {
  dispatch(name)
}
