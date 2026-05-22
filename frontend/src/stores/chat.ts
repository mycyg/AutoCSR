import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  deleteChatMessage, getChatHistory, listSectionVersions, postChat,
  rollbackSection,
  type ChatMessageDTO, type ChatTurnResultDTO, type SectionDraftDTO,
} from '@/api/rest'

export const useChatStore = defineStore('chat', () => {
  // Bucket by node_id
  const historyByNode = ref<Record<string, ChatMessageDTO[]>>({})
  const versionsByNode = ref<Record<string, number[]>>({})
  const thinking = ref<Record<string, boolean>>({})
  const error = ref<string | null>(null)

  async function loadHistory(pid: string, nodeId: string): Promise<void> {
    try {
      historyByNode.value = {
        ...historyByNode.value,
        [nodeId]: await getChatHistory(pid, nodeId),
      }
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  async function loadVersions(pid: string, nodeId: string): Promise<void> {
    try {
      versionsByNode.value = {
        ...versionsByNode.value,
        [nodeId]: await listSectionVersions(pid, nodeId),
      }
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  async function send(pid: string, nodeId: string, message: string): Promise<ChatTurnResultDTO> {
    thinking.value = { ...thinking.value, [nodeId]: true }
    error.value = null
    try {
      const result = await postChat(pid, nodeId, message)
      // Optimistically refresh history + versions
      await loadHistory(pid, nodeId)
      await loadVersions(pid, nodeId)
      return result
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      thinking.value = { ...thinking.value, [nodeId]: false }
    }
  }

  async function removeMessage(pid: string, nodeId: string, msgId: string): Promise<void> {
    await deleteChatMessage(pid, nodeId, msgId)
    await loadHistory(pid, nodeId)
  }

  async function rollback(pid: string, nodeId: string, version: number): Promise<SectionDraftDTO> {
    const d = await rollbackSection(pid, nodeId, version)
    await loadVersions(pid, nodeId)
    return d
  }

  function reset(): void {
    historyByNode.value = {}
    versionsByNode.value = {}
    thinking.value = {}
    error.value = null
  }

  return {
    historyByNode, versionsByNode, thinking, error,
    loadHistory, loadVersions, send, removeMessage, rollback, reset,
  }
})
