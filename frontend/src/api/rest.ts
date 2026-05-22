import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

export interface ProjectDTO {
  id: string
  name: string
  principle_id: string | null
  created_at: string
  status: string
}

export interface CreateProjectPayload {
  name: string
  principle_id?: string | null
}

export async function listProjects(): Promise<ProjectDTO[]> {
  const r = await api.get<ProjectDTO[]>('/projects')
  return r.data
}

export async function createProject(payload: CreateProjectPayload): Promise<ProjectDTO> {
  const r = await api.post<ProjectDTO>('/projects', payload)
  return r.data
}

export async function getProject(id: string): Promise<ProjectDTO> {
  const r = await api.get<ProjectDTO>(`/projects/${id}`)
  return r.data
}

export default api
