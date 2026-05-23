import { createI18n } from 'vue-i18n'
import zh from './zh.json'
import en from './en.json'

const STORAGE_KEY = 'autocsr.locale'

export type Locale = 'zh' | 'en'

function detectInitial(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY) as Locale | null
    if (stored === 'zh' || stored === 'en') return stored
  } catch {
    /* localStorage unavailable */
  }
  const nav = (typeof navigator !== 'undefined' && navigator.language) || 'zh'
  return nav.toLowerCase().startsWith('en') ? 'en' : 'zh'
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: detectInitial(),
  fallbackLocale: 'zh',
  messages: { zh, en },
  silentTranslationWarn: true,
  silentFallbackWarn: true,
})

export function setLocale(locale: Locale): void {
  i18n.global.locale.value = locale
  try {
    window.localStorage.setItem(STORAGE_KEY, locale)
  } catch {
    /* ignore */
  }
  try {
    document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en'
  } catch {
    /* ignore */
  }
}

export function currentLocale(): Locale {
  return i18n.global.locale.value as Locale
}
