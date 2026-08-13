import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import en from './locales/en'

export type AppLocale = 'zh-CN' | 'en'

const STORAGE_KEY = 'symbix_locale'

/** 获取用户语言，优先级：localStorage > 浏览器语言 */
export function getInitialLocale(): AppLocale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'zh-CN' || saved === 'en') return saved
  } catch {}
  const browser = (navigator.language || '').toLowerCase()
  if (browser.startsWith('zh')) return 'zh-CN'
  return 'en'
}

const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: getInitialLocale(),
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': zhCN,
    en,
  },
})

/** 切换语言（不写 localStorage，由 useLocale 统一持久化） */
export function setLocale(locale: AppLocale) {
  ;(i18n.global.locale as { value: string }).value = locale
}

export default i18n
