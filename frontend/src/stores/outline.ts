import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  addOutlineChild, buildOutline, deleteOutlineNode, getOutline,
  listOutlineVersions, patchOutlineNode, restoreOutlineVersion,
  type OutlineDTO, type OutlineNodeDTO,
} from '@/api/rest'

export const useOutlineStore = defineStore('outline', () => {
  const outline = ref<OutlineDTO | null>(null)
  const versions = ref<number[]>([])
  const selectedNodeId = ref<string | null>(null)
  const loading = ref(false)
  const building = ref(false)

  async function load(pid: string): Promise<void> {
    loading.value = true
    try {
      outline.value = await getOutline(pid)
      versions.value = await listOutlineVersions(pid)
    } catch (e: unknown) {
      outline.value = null
      throw e
    } finally {
      loading.value = false
    }
  }

  async function build(pid: string, principleId: string): Promise<void> {
    building.value = true
    try {
      await buildOutline(pid, principleId)
      await load(pid)
    } finally {
      building.value = false
    }
  }

  async function patchNode(pid: string, nodeId: string, patch: Partial<OutlineNodeDTO>): Promise<void> {
    const updated = await patchOutlineNode(pid, nodeId, patch)
    _mergeNode(updated)
  }

  async function addChild(pid: string, parentId: string, title: string, notes?: string): Promise<void> {
    await addOutlineChild(pid, parentId, title, notes)
    await load(pid)
  }

  async function removeNode(pid: string, nodeId: string): Promise<void> {
    await deleteOutlineNode(pid, nodeId)
    if (selectedNodeId.value === nodeId) selectedNodeId.value = null
    await load(pid)
  }

  async function restore(pid: string, version: number): Promise<void> {
    await restoreOutlineVersion(pid, version)
    await load(pid)
  }

  function findNode(nodeId: string | null): OutlineNodeDTO | null {
    if (!nodeId || !outline.value) return null
    const stack: OutlineNodeDTO[] = [...outline.value.root_sections]
    while (stack.length) {
      const n = stack.pop()!
      if (n.id === nodeId) return n
      stack.push(...n.children)
    }
    return null
  }

  function _mergeNode(updated: OutlineNodeDTO): void {
    if (!outline.value) return
    const walk = (nodes: OutlineNodeDTO[]): OutlineNodeDTO[] =>
      nodes.map((n) => {
        if (n.id === updated.id) {
          // preserve children — the patch endpoint doesn't return them
          return { ...updated, children: n.children }
        }
        return { ...n, children: walk(n.children) }
      })
    outline.value = { ...outline.value, root_sections: walk(outline.value.root_sections) }
  }

  function reset(): void {
    outline.value = null
    versions.value = []
    selectedNodeId.value = null
  }

  return {
    outline, versions, selectedNodeId, loading, building,
    load, build, patchNode, addChild, removeNode, restore,
    findNode, reset,
  }
})
