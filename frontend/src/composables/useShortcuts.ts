/**
 * Global keyboard shortcut bus.
 *
 * Components listen by name; `useShortcuts()` registers the global key
 * listener exactly once per app lifetime. Hot-reload safe.
 *
 * Built-in slots:
 *   - save                 (Ctrl/Cmd + S)
 *   - search               (Ctrl/Cmd + K)
 *   - help                 (Shift + ? / ?)
 *   - show_view_shortcuts  (Ctrl/Cmd + /)
 *   - outline_next         (j)
 *   - outline_prev         (k)
 *   - list_up              (ArrowUp inside list focus)
 *   - list_down            (ArrowDown inside list focus)
 *   - close_modal          (Escape — most modal libs handle it natively;
 *                           we still dispatch for custom overlays)
 *   - pane_next            (Tab when not inside an input)
 *   - pane_prev            (Shift+Tab when not inside an input)
 *
 * `Shift+Enter` is intentionally a *no-op global* — components handle it
 * locally in their input boxes.
 */
import { onMounted, onUnmounted } from 'vue'

type Handler = () => void

interface Slot {
  handlers: Set<Handler>
}

export type SlotName =
  | 'save' | 'search' | 'help' | 'show_view_shortcuts'
  | 'outline_next' | 'outline_prev'
  | 'list_up' | 'list_down'
  | 'close_modal'
  | 'pane_next' | 'pane_prev'

const slots: Record<SlotName, Slot> = {
  save: { handlers: new Set() },
  search: { handlers: new Set() },
  help: { handlers: new Set() },
  show_view_shortcuts: { handlers: new Set() },
  outline_next: { handlers: new Set() },
  outline_prev: { handlers: new Set() },
  list_up: { handlers: new Set() },
  list_down: { handlers: new Set() },
  close_modal: { handlers: new Set() },
  pane_next: { handlers: new Set() },
  pane_prev: { handlers: new Set() },
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

function dispatch(name: SlotName): void {
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
  if (meta && key === '/') {
    e.preventDefault()
    dispatch('show_view_shortcuts')
    return
  }
  if (!meta && (e.key === '?' || (e.shiftKey && key === '/'))) {
    if (isEditableTarget(e)) return
    e.preventDefault()
    dispatch('help')
    return
  }
  if (!meta && key === 'escape') {
    // Don't preventDefault — Element Plus modals listen for it too.
    dispatch('close_modal')
    return
  }
  if (isEditableTarget(e)) return
  if (!meta && key === 'j') { dispatch('outline_next'); return }
  if (!meta && key === 'k') { dispatch('outline_prev'); return }
  if (!meta && e.key === 'ArrowDown') { dispatch('list_down'); return }
  if (!meta && e.key === 'ArrowUp')   { dispatch('list_up'); return }
  // Tab pane switching only if the focused element opts in via [data-pane-cycle]
  if (!meta && key === 'tab' && (e.target as HTMLElement | null)?.closest('[data-pane-cycle]')) {
    e.preventDefault()
    dispatch(e.shiftKey ? 'pane_prev' : 'pane_next')
  }
}

function ensureInstalled(): void {
  if (installed) return
  if (typeof window === 'undefined') return
  window.addEventListener('keydown', onKey, true)
  installed = true
}

/** Register handlers for one or more shortcut slots. */
export function useShortcuts(opts: Partial<Record<SlotName, Handler>> = {}): void {
  ensureInstalled()
  const keys = Object.keys(opts) as SlotName[]
  onMounted(() => {
    for (const k of keys) {
      const h = opts[k]
      if (h) slots[k].handlers.add(h)
    }
  })
  onUnmounted(() => {
    for (const k of keys) {
      const h = opts[k]
      if (h) slots[k].handlers.delete(h)
    }
  })
}

/** Imperatively trigger a slot (used by the help modal etc.). */
export function triggerShortcut(name: SlotName): void {
  dispatch(name)
}
