import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  deleteExport as apiDeleteExport, exportDocx, listExports,
  type ExportEntryDTO, type ExportOptions, type ExportResultDTO,
} from '@/api/rest'

export const useExportStore = defineStore('export', () => {
  const history = ref<ExportEntryDTO[]>([])
  const phase = ref<string>('idle')
  const last = ref<ExportResultDTO | null>(null)
  const exporting = ref(false)
  const error = ref<string | null>(null)

  async function refresh(pid: string): Promise<void> {
    try {
      history.value = await listExports(pid)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  async function trigger(pid: string, opts: ExportOptions = {}): Promise<ExportResultDTO> {
    exporting.value = true
    error.value = null
    phase.value = 'starting'
    try {
      const r = await exportDocx(pid, opts)
      last.value = r
      phase.value = 'done'
      await refresh(pid)
      return r
    } catch (e: unknown) {
      phase.value = 'error'
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      exporting.value = false
    }
  }

  async function remove(pid: string, filename: string): Promise<void> {
    await apiDeleteExport(pid, filename)
    await refresh(pid)
  }

  function handleWS(event: { type: string; payload?: Record<string, unknown> }): void {
    const t = event.type
    const p = event.payload ?? {}
    if (t === 'export.start') {
      exporting.value = true
      phase.value = 'starting'
    } else if (t === 'export.progress') {
      phase.value = String(p.phase ?? 'progress')
    } else if (t === 'export.done') {
      exporting.value = false
      phase.value = 'done'
    } else if (t === 'export.error') {
      exporting.value = false
      phase.value = 'error'
      error.value = String(p.error ?? 'export failed')
    }
  }

  function reset(): void {
    history.value = []
    phase.value = 'idle'
    last.value = null
    exporting.value = false
    error.value = null
  }

  return {
    history, phase, last, exporting, error,
    refresh, trigger, remove, handleWS, reset,
  }
})
