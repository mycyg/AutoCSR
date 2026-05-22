import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  generateReport, getDraft, getReportStatus, getTerminology,
  listDrafts, patchTerminology, regenerateDraft,
  type DraftSummaryDTO, type ReportStatusDTO, type SectionDraftDTO,
} from '@/api/rest'

export const useReportStore = defineStore('report', () => {
  const status = ref<ReportStatusDTO | null>(null)
  const drafts = ref<DraftSummaryDTO[]>([])
  const draftCache = ref<Record<string, SectionDraftDTO>>({})
  const selectedNodeId = ref<string | null>(null)
  const terminology = ref<Record<string, string>>({})
  const generating = ref(false)
  const error = ref<string | null>(null)

  const currentDraft = computed(() => {
    const id = selectedNodeId.value
    if (!id) return null
    return draftCache.value[id] ?? null
  })

  const leavesTotal = computed(() => status.value?.leaves_total ?? 0)
  const leavesDone = computed(() => status.value?.leaves_done ?? 0)
  const leavesErrored = computed(() => status.value?.leaves_errored ?? 0)
  const totalTokens = computed(() => status.value?.total_tokens ?? { input: 0, output: 0 })
  const totalWords = computed(() => status.value?.total_words ?? 0)
  const phase = computed(() => status.value?.current_phase ?? 'idle')

  async function refreshStatus(pid: string): Promise<void> {
    try {
      status.value = await getReportStatus(pid)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  async function refreshDrafts(pid: string): Promise<void> {
    drafts.value = await listDrafts(pid)
  }

  async function loadDraft(pid: string, nodeId: string): Promise<void> {
    try {
      const d = await getDraft(pid, nodeId)
      draftCache.value = { ...draftCache.value, [nodeId]: d }
    } catch {
      // Draft does not yet exist
      delete draftCache.value[nodeId]
      draftCache.value = { ...draftCache.value }
    }
  }

  async function selectNode(pid: string, nodeId: string): Promise<void> {
    selectedNodeId.value = nodeId
    if (!draftCache.value[nodeId]) await loadDraft(pid, nodeId)
  }

  async function generate(pid: string, harmonize = true, leafLimit?: number): Promise<void> {
    generating.value = true
    error.value = null
    try {
      await generateReport(pid, harmonize, leafLimit)
      // Status updates flow via WS; pull immediately too
      await refreshStatus(pid)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      generating.value = false
    }
  }

  async function regenerate(pid: string, nodeId: string, extra?: string): Promise<void> {
    const d = await regenerateDraft(pid, nodeId, extra)
    draftCache.value = { ...draftCache.value, [nodeId]: d }
    await refreshDrafts(pid)
  }

  async function loadTerminology(pid: string): Promise<void> {
    terminology.value = await getTerminology(pid)
  }

  async function saveTerminology(pid: string, terms: Record<string, string>): Promise<void> {
    terminology.value = await patchTerminology(pid, terms)
  }

  function handleWS(pid: string, event: { type: string; payload?: Record<string, unknown> }): void {
    const t = event.type
    const p = event.payload ?? {}
    if (t === 'writer.batch_start' || t === 'writer.batch_done' || t === 'writer.section_start') {
      void refreshStatus(pid)
    } else if (t === 'writer.section_done') {
      void refreshStatus(pid)
      const nodeId = String(p.node_id ?? '')
      if (nodeId && draftCache.value[nodeId]) {
        void loadDraft(pid, nodeId)
      }
      void refreshDrafts(pid)
    } else if (t === 'writer.section_error') {
      void refreshStatus(pid)
    } else if (t === 'writer.report_done' || t === 'writer.report_error'
               || t === 'harmonizer.done' || t === 'harmonizer.start'
               || t === 'harmonizer.progress') {
      void refreshStatus(pid)
      if (t === 'harmonizer.done' || t === 'writer.report_done') {
        void refreshDrafts(pid)
      }
    }
  }

  function reset(): void {
    status.value = null
    drafts.value = []
    draftCache.value = {}
    selectedNodeId.value = null
    terminology.value = {}
    error.value = null
  }

  return {
    status, drafts, draftCache, selectedNodeId, terminology, generating, error,
    currentDraft, leavesTotal, leavesDone, leavesErrored, totalTokens, totalWords, phase,
    refreshStatus, refreshDrafts, loadDraft, selectNode, generate, regenerate,
    loadTerminology, saveTerminology, handleWS, reset,
  }
})
