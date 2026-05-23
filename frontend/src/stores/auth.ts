import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import api from '@/api/rest'

export interface AuthUser {
  id: string
  email: string
  display_name: string
  role: 'admin' | 'user'
  tenant_id: string
  created_at?: string
  last_login_at?: string | null
}

export interface AuthTenant {
  id: string
  name: string
  plan: 'free' | 'pro' | 'enterprise'
  created_at?: string
  settings?: Record<string, unknown>
}

const LS_ACCESS = 'autocsr.access_token'
const LS_REFRESH = 'autocsr.refresh_token'
const LS_USER = 'autocsr.me'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)
  const tenant = ref<AuthTenant | null>(null)
  const accessToken = ref<string>(localStorage.getItem(LS_ACCESS) || '')
  const refreshToken = ref<string>(localStorage.getItem(LS_REFRESH) || '')
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Hydrate cached user/tenant so the navbar doesn't flash empty on reload.
  try {
    const raw = localStorage.getItem(LS_USER)
    if (raw) {
      const parsed = JSON.parse(raw)
      user.value = parsed.user || null
      tenant.value = parsed.tenant || null
    }
  } catch {
    /* ignore */
  }

  const isAuthenticated = computed(() => !!accessToken.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  function _persist(): void {
    if (accessToken.value) localStorage.setItem(LS_ACCESS, accessToken.value)
    else localStorage.removeItem(LS_ACCESS)
    if (refreshToken.value) localStorage.setItem(LS_REFRESH, refreshToken.value)
    else localStorage.removeItem(LS_REFRESH)
    if (user.value || tenant.value) {
      localStorage.setItem(
        LS_USER,
        JSON.stringify({ user: user.value, tenant: tenant.value }),
      )
    } else {
      localStorage.removeItem(LS_USER)
    }
  }

  async function login(email: string, password: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const r = await api.post<{
        user: AuthUser; tenant: AuthTenant;
        access_token: string; refresh_token: string
      }>('/auth/login', { email, password })
      user.value = r.data.user
      tenant.value = r.data.tenant
      accessToken.value = r.data.access_token
      refreshToken.value = r.data.refresh_token
      _persist()
    } catch (e: any) {
      error.value = e?.response?.data?.detail || e?.message || 'login failed'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function register(payload: {
    email: string; password: string; display_name?: string; tenant_name?: string
  }): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const r = await api.post<{
        user: AuthUser; tenant: AuthTenant;
        access_token: string; refresh_token: string
      }>('/auth/register', payload)
      user.value = r.data.user
      tenant.value = r.data.tenant
      accessToken.value = r.data.access_token
      refreshToken.value = r.data.refresh_token
      _persist()
    } catch (e: any) {
      error.value = e?.response?.data?.detail || e?.message || 'register failed'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchMe(): Promise<void> {
    if (!accessToken.value) return
    try {
      const r = await api.get<{ user: AuthUser; tenant: AuthTenant }>('/auth/me')
      user.value = r.data.user
      tenant.value = r.data.tenant
      _persist()
    } catch {
      /* swallow — interceptor handles 401 */
    }
  }

  async function refresh(): Promise<boolean> {
    if (!refreshToken.value) return false
    try {
      const r = await api.post<{ access_token: string }>('/auth/refresh', {
        refresh_token: refreshToken.value,
      })
      accessToken.value = r.data.access_token
      _persist()
      return true
    } catch {
      return false
    }
  }

  async function logout(): Promise<void> {
    const rt = refreshToken.value
    user.value = null
    tenant.value = null
    accessToken.value = ''
    refreshToken.value = ''
    _persist()
    if (rt) {
      try {
        await api.post('/auth/logout', { refresh_token: rt })
      } catch {
        /* ignore */
      }
    }
  }

  async function updateMe(patch: { display_name?: string; password?: string }): Promise<void> {
    const r = await api.patch<AuthUser>('/auth/me', patch)
    user.value = r.data
    _persist()
  }

  return {
    user, tenant, accessToken, refreshToken,
    loading, error, isAuthenticated, isAdmin,
    login, register, fetchMe, refresh, logout, updateMe,
  }
})
