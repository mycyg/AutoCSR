// WebSocket client for /ws/{pid}. Handlers receive {type, payload} events.
// Auto-reconnects with capped exponential backoff. Safe to call from setup().

export interface WSEvent { type: string; payload?: Record<string, unknown> }
export type WSHandler = (ev: WSEvent) => void

interface Connection {
  socket: WebSocket | null
  closed: boolean
  retries: number
  timer: number | null
}

export function connectProjectWS(projectId: string, handler: WSHandler): () => void {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  // Vite proxies /ws to the backend; in dev the host:port is fine because the
  // backend serves the ws endpoint at /ws/{pid}.
  const conn: Connection = { socket: null, closed: false, retries: 0, timer: null }

  function url(): string {
    const host = window.location.host
    return `${proto}//${host}/ws/${projectId}`
  }

  function open(): void {
    if (conn.closed) return
    try {
      conn.socket = new WebSocket(url())
    } catch {
      schedule()
      return
    }
    conn.socket.onopen = (): void => {
      conn.retries = 0
    }
    conn.socket.onmessage = (e: MessageEvent): void => {
      try {
        const data = JSON.parse(e.data) as WSEvent
        handler(data)
      } catch {
        handler({ type: 'raw', payload: { text: String(e.data) } })
      }
    }
    conn.socket.onclose = schedule
    conn.socket.onerror = (): void => {
      try { conn.socket?.close() } catch { /* ignore */ }
    }
  }

  function schedule(): void {
    if (conn.closed) return
    const delay = Math.min(15_000, 500 * Math.pow(2, conn.retries))
    conn.retries += 1
    conn.timer = window.setTimeout(open, delay)
  }

  open()

  return (): void => {
    conn.closed = true
    if (conn.timer !== null) window.clearTimeout(conn.timer)
    try { conn.socket?.close() } catch { /* ignore */ }
  }
}
