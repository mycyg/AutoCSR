import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  deleteStat, getStat, listStats, runAnalysis, triggerAutoAnalysis,
  type StatBlockDTO, type StatBlockSummaryDTO,
} from '@/api/rest'

export const useAnalysisStore = defineStore('analysis', () => {
  const blocks = ref<StatBlockSummaryDTO[]>([])
  const selected = ref<StatBlockDTO | null>(null)
  const loading = ref(false)
  const autoRunning = ref(false)

  async function refresh(pid: string): Promise<void> {
    loading.value = true
    try {
      blocks.value = await listStats(pid)
    } finally {
      loading.value = false
    }
  }

  async function loadOne(pid: string, statId: string): Promise<void> {
    selected.value = await getStat(pid, statId)
  }

  async function runAuto(pid: string): Promise<void> {
    autoRunning.value = true
    try {
      await triggerAutoAnalysis(pid)
      await refresh(pid)
    } finally {
      autoRunning.value = false
    }
  }

  async function runManual(pid: string, type: string, params: Record<string, unknown>): Promise<StatBlockDTO> {
    const r = await runAnalysis(pid, type, params)
    await refresh(pid)
    return r.block
  }

  async function remove(pid: string, statId: string): Promise<void> {
    await deleteStat(pid, statId)
    if (selected.value?.id === statId) selected.value = null
    await refresh(pid)
  }

  function reset(): void {
    blocks.value = []
    selected.value = null
  }

  return { blocks, selected, loading, autoRunning, refresh, loadOne, runAuto, runManual, remove, reset }
})
