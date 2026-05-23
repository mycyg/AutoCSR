/**
 * Theme toggling — light / dark.
 *
 * Reads the persisted preference from localStorage (`autocsr_theme`).
 * Falls back to the user's OS preference via `prefers-color-scheme`.
 *
 * Setting the theme writes `data-theme` on <html> (which cascades through
 * tokens.css) AND toggles the `dark` class so Element Plus' dark CSS
 * vars kick in.
 */
import { computed, type ComputedRef, ref, watchEffect } from 'vue'

export type Theme = 'light' | 'dark'

const KEY = 'autocsr_theme'

function detectInitial(): Theme {
  if (typeof window === 'undefined') return 'light'
  try {
    const saved = window.localStorage.getItem(KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch { /* localStorage blocked */ }
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark'
  return 'light'
}

const current = ref<Theme>(detectInitial())

function applyTo(html: HTMLElement | null, theme: Theme): void {
  if (!html) return
  html.setAttribute('data-theme', theme)
  if (theme === 'dark') html.classList.add('dark')
  else html.classList.remove('dark')
}

if (typeof window !== 'undefined') {
  applyTo(document.documentElement, current.value)
  // Persist + re-apply on any change.
  watchEffect(() => {
    applyTo(document.documentElement, current.value)
    try { window.localStorage.setItem(KEY, current.value) } catch { /* ignore */ }
  })
}

export function useTheme(): {
  theme: typeof current
  isDark: ComputedRef<boolean>
  toggleTheme: () => void
  setTheme: (t: Theme) => void
} {
  return {
    theme: current,
    isDark: computed(() => current.value === 'dark'),
    toggleTheme: () => { current.value = current.value === 'dark' ? 'light' : 'dark' },
    setTheme: (t: Theme) => { current.value = t },
  }
}
