import { computed, readonly, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  setLocale as applyI18nLocale,
  getInitialLocale,
  type AppLocale,
} from '@/i18n'
import { locale as getSystemLocaleTag } from '@tauri-apps/plugin-os'
import { emit } from '@tauri-apps/api/event'
export type { AppLocale }

const STORAGE_KEY = 'symbix_locale'
const supportedLocales: AppLocale[] = ['zh-CN', 'en']
/** Module-level state so all windows / components share the same locale */
const localeRef = ref<AppLocale>(normalizeLocale(getInitialLocale()))
let storageListenerBound = false


async function getSystemLocale(): Promise<AppLocale> {
  const raw = await getSystemLocaleTag() // 例如 "zh-Hans-CN"、"en-US"、null
  if (!raw) return 'zh-CN'
  const lang = raw.toLowerCase()
  if (lang.startsWith('zh')) return 'zh-CN'
  if (lang.startsWith('en')) return 'en'
  return 'zh-CN'
}
function normalizeLocale(value: unknown): AppLocale {
  if (value === 'zh-CN' || value === 'en') return value
  return 'zh-CN'
}

function applyLocaleChange(next: AppLocale, persist = true) {
  localeRef.value = next
  applyI18nLocale(next)
  if (persist) {
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {}
    emit('locale-changed', next) // 广播给所有窗口，不再依赖 storage 事件
  }
}

/** Listen for locale changes from other Tauri windows */
function bindStorageListener() {
  if (storageListenerBound || typeof window === 'undefined') return
  storageListenerBound = true
  window.addEventListener('storage', (e: StorageEvent) => {
    if (e.key !== STORAGE_KEY) return
    const next = normalizeLocale(e.newValue)
    // Don't re-write localStorage — another window already did
    applyLocaleChange(next, false)
  })
}

export function useLocale() {
  bindStorageListener()

  // 必须在 setup 顶层调用，以拿到当前 vue-i18n 实例
  const i18n = useI18n()
  const { t } = i18n
  // Keep vue-i18n in sync if this composable is used after i18n boot
  if (i18n.locale.value !== localeRef.value) {
    i18n.locale.value = localeRef.value
  }

  const localeOptions = computed(() => [
    { label: t('setting.systemLocale'), value: 'system' as const },
    { label: '简体中文', value: 'zh-CN' as AppLocale },
    { label: 'English', value: 'en' as AppLocale },
  ])

  function setLocale(next: string) {
    const normalized = normalizeLocale(next)
    if (normalized === localeRef.value) return
    applyLocaleChange(normalized)
  }

  function toggleLocale() {
    setLocale(localeRef.value === 'zh-CN' ? 'en' : 'zh-CN')
  }

  return {
    locale: readonly(localeRef),
    localeOptions,
    supportedLocales,
    setLocale,
    toggleLocale,
  }
}
