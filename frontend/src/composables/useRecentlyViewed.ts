/**
 * Per-project "recently viewed sections" history.
 *
 * Persists to sessionStorage so it resets when the tab closes — long-term
 * recency is shown by the backend in the project sidebar (recent.ts).
 *
 * Schema: sessionStorage[`autocsr_recent_<pid>`] = JSON [{ node_id, title, ts }]
 */
import { ref, watch } from 'vue'

export interface RecentItem {
  node_id: string
  title: string
  ts: number
}

const MAX = 10

function key(pid: string): string { return `autocsr_recent_${pid}` }

function read(pid: string): RecentItem[] {
  try {
    const raw = window.sessionStorage.getItem(key(pid))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(i => i && typeof i.node_id === 'string').slice(0, MAX)
  } catch { return [] }
}

function write(pid: string, list: RecentItem[]): void {
  try {
    window.sessionStorage.setItem(key(pid), JSON.stringify(list.slice(0, MAX)))
  } catch { /* quota / private mode */ }
}

const caches: Record<string, ReturnType<typeof ref<RecentItem[]>>> = {}

export function useRecentlyViewed(pid: string): {
  items: ReturnType<typeof ref<RecentItem[]>>
  track: (node_id: string, title: string) => void
  clear: () => void
} {
  if (!caches[pid]) {
    const items = ref<RecentItem[]>(read(pid))
    watch(items, (v) => write(pid, v || []), { deep: true })
    caches[pid] = items
  }
  const items = caches[pid]
  function track(node_id: string, title: string): void {
    if (!node_id) return
    const list = (items.value || []).filter(i => i.node_id !== node_id)
    list.unshift({ node_id, title, ts: Date.now() })
    items.value = list.slice(0, MAX)
  }
  function clear(): void { items.value = [] }
  return { items, track, clear }
}
