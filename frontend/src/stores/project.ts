import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  createProject as apiCreate,
  createProjectFromTemplate as apiCreateFromTemplate,
  deleteProject as apiDelete,
  getProject as apiGet,
  listProjects as apiList,
  listProjectTemplates as apiListTemplates,
  updateProject as apiUpdate,
  type CreateProjectPayload,
  type ProjectDTO,
  type ProjectListQuery,
  type ProjectTemplateDTO,
  type ProjectUpdatePayload,
} from '@/api/rest'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<ProjectDTO[]>([])
  const templates = ref<ProjectTemplateDTO[]>([])
  const currentProject = ref<ProjectDTO | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const query = ref<ProjectListQuery>({ archived: false, sort: 'last_opened' })

  async function refresh(q?: ProjectListQuery): Promise<void> {
    if (q) query.value = { ...query.value, ...q }
    loading.value = true
    error.value = null
    try {
      projects.value = await apiList(query.value)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function loadTemplates(): Promise<void> {
    try {
      templates.value = await apiListTemplates()
    } catch (e) {
      templates.value = []
    }
  }

  async function create(payload: CreateProjectPayload): Promise<ProjectDTO> {
    const p = await apiCreate(payload)
    projects.value = [p, ...projects.value]
    return p
  }

  async function createFromTemplate(templateId: string, name: string): Promise<ProjectDTO> {
    const p = await apiCreateFromTemplate(templateId, name)
    projects.value = [p, ...projects.value]
    return p
  }

  async function update(id: string, patch: ProjectUpdatePayload): Promise<ProjectDTO> {
    const p = await apiUpdate(id, patch)
    projects.value = projects.value.map((x) => (x.id === id ? p : x))
    if (currentProject.value?.id === id) currentProject.value = p
    return p
  }

  async function remove(id: string, force = false): Promise<void> {
    await apiDelete(id, force)
    projects.value = projects.value.filter((x) => x.id !== id)
  }

  async function load(id: string): Promise<ProjectDTO> {
    const p = await apiGet(id)
    currentProject.value = p
    return p
  }

  const allTags = computed<string[]>(() => {
    const s = new Set<string>()
    for (const p of projects.value) {
      for (const t of (p.tags || [])) s.add(t)
    }
    return Array.from(s).sort()
  })

  const recent = computed<ProjectDTO[]>(() => {
    const items = projects.value.filter((p) => !p.archived)
    items.sort((a, b) => {
      const aT = a.last_opened_at || a.created_at || ''
      const bT = b.last_opened_at || b.created_at || ''
      return bT.localeCompare(aT)
    })
    return items.slice(0, 5)
  })

  return {
    projects, templates, currentProject, loading, error, query, allTags, recent,
    refresh, loadTemplates, create, createFromTemplate, update, remove, load,
  }
})
