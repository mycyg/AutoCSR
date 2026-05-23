import { createI18n } from 'vue-i18n'
import zh from './zh.json'
import en from './en.json'
import ja from './ja.json'

const STORAGE_KEY = 'autocsr.locale'

export type Locale = 'zh' | 'en' | 'ja'

function detectInitial(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY) as Locale | null
    if (stored === 'zh' || stored === 'en' || stored === 'ja') return stored
  } catch {
    /* localStorage unavailable */
  }
  const nav = (typeof navigator !== 'undefined' && navigator.language) || 'zh'
  const lower = nav.toLowerCase()
  if (lower.startsWith('ja')) return 'ja'
  if (lower.startsWith('en')) return 'en'
  return 'zh'
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: detectInitial(),
  fallbackLocale: 'zh',
  messages: { zh, en, ja },
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
    document.documentElement.lang =
      locale === 'zh' ? 'zh-CN' : locale === 'ja' ? 'ja' : 'en'
  } catch {
    /* ignore */
  }
}

export function currentLocale(): Locale {
  return i18n.global.locale.value as Locale
}
