import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  createProject as apiCreate,
  getProject as apiGet,
  listProjects as apiList,
  type CreateProjectPayload,
  type ProjectDTO,
} from '@/api/rest'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<ProjectDTO[]>([])
  const currentProject = ref<ProjectDTO | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function refresh(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      projects.value = await apiList()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function create(payload: CreateProjectPayload): Promise<ProjectDTO> {
    const p = await apiCreate(payload)
    projects.value = [...projects.value, p]
    return p
  }

  async function load(id: string): Promise<ProjectDTO> {
    const p = await apiGet(id)
    currentProject.value = p
    return p
  }

  return { projects, currentProject, loading, error, refresh, create, load }
})
