// M1 placeholder. The backend WS endpoint /ws/<pid> is wired in M2 when ingestion
// + writer agents need to push progress events. Until then this is a stub so other
// modules can `import { connectProjectWS }` without conditional code.

export type WSEvent = { type: string; payload?: unknown }
export type WSHandler = (ev: WSEvent) => void

export function connectProjectWS(_projectId: string, _handler: WSHandler): () => void {
  // No-op; returns a disconnect function for symmetry with the eventual impl.
  return () => {}
}
