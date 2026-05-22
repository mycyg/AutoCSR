import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  applyCleansing, getAudit, getPipelineYaml, getPreview, listProposals,
  listSnapshots, rollbackSnapshot, updateProposal,
  type ProposalDTO,
} from '@/api/rest'

export const useCleansingStore = defineStore('cleansing', () => {
  const proposalsByFile = ref<Record<string, ProposalDTO[]>>({})
  const selectedFileId = ref<string>('')
  const previewRows = ref<string[][]>([])
  const previewCols = ref<string[]>([])
  const audit = ref<{ timestamp: string; action: string; file_id: string; detail: Record<string, unknown> }[]>([])
  const snapshots = ref<{ id: string; file_id: string; created_at: string; parquet_path: string }[]>([])
  const pipelineYaml = ref<string>('')
  const loadingProposals = ref(false)

  const proposalsForSelected = computed<ProposalDTO[]>(() =>
    selectedFileId.value ? proposalsByFile.value[selectedFileId.value] || [] : [])

  async function loadProposals(pid: string, fileId: string, refresh = false): Promise<void> {
    loadingProposals.value = true
    try {
      const list = await listProposals(pid, fileId, refresh)
      proposalsByFile.value = { ...proposalsByFile.value, [fileId]: list }
    } finally {
      loadingProposals.value = false
    }
  }

  async function patchProposal(pid: string, fileId: string, proposalId: string, patch: Partial<ProposalDTO>): Promise<void> {
    const updated = await updateProposal(pid, proposalId, patch)
    const list = proposalsByFile.value[fileId] || []
    proposalsByFile.value = {
      ...proposalsByFile.value,
      [fileId]: list.map((p) => (p.id === proposalId ? updated : p)),
    }
  }

  async function acceptAll(pid: string, fileId: string): Promise<void> {
    const list = proposalsByFile.value[fileId] || []
    for (const p of list) {
      if (p.status === 'pending') {
        await patchProposal(pid, fileId, p.id, { status: 'accepted' })
      }
    }
  }

  async function apply(pid: string, fileId: string): Promise<{ snapshot_id: string }> {
    const out = await applyCleansing(pid, fileId)
    await loadProposals(pid, fileId)
    await loadAudit(pid)
    await loadSnapshots(pid, fileId)
    await loadPreview(pid, fileId)
    return out
  }

  async function rollback(pid: string, snapshotId: string, fileId: string): Promise<void> {
    await rollbackSnapshot(pid, snapshotId, fileId)
    await loadAudit(pid)
    await loadPreview(pid, fileId)
  }

  async function loadPreview(pid: string, fileId: string): Promise<void> {
    try {
      const r = await getPreview(pid, fileId, 50)
      previewCols.value = r.columns
      previewRows.value = r.rows
    } catch {
      previewCols.value = []
      previewRows.value = []
    }
  }

  async function loadAudit(pid: string): Promise<void> {
    audit.value = await getAudit(pid)
  }
  async function loadSnapshots(pid: string, fileId?: string): Promise<void> {
    snapshots.value = await listSnapshots(pid, fileId)
  }
  async function loadPipelineYaml(pid: string, fileId?: string): Promise<void> {
    pipelineYaml.value = await getPipelineYaml(pid, fileId)
  }

  return {
    proposalsByFile, selectedFileId, previewRows, previewCols, audit,
    snapshots, pipelineYaml, loadingProposals,
    proposalsForSelected,
    loadProposals, patchProposal, acceptAll, apply, rollback,
    loadPreview, loadAudit, loadSnapshots, loadPipelineYaml,
  }
})
