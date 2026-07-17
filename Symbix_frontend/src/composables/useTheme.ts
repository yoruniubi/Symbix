import { ref, computed, readonly } from 'vue'
import { darkTheme, type GlobalTheme } from 'naive-ui'
import {
  type ThemeMode,
  DEFAULT_THEME_MODE,
  injectCssVariables,
  buildThemeOverrides,
} from '@/theme'

const STORAGE_KEY = 'symbix_theme_mode'

const mode = ref<ThemeMode>(loadInitialMode())
let storageListenerBound = false

function loadInitialMode(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {}
  return DEFAULT_THEME_MODE
}

function applyMode(next: ThemeMode, persist = true) {
  mode.value = next
  injectCssVariables(next)
  if (persist) {
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {}
  }
}

/** Listen for theme changes from other Tauri windows */
function bindStorageListener() {
  if (storageListenerBound || typeof window === 'undefined') return
  storageListenerBound = true
  window.addEventListener('storage', (e: StorageEvent) => {
    if (e.key !== STORAGE_KEY) return
    const next = e.newValue
    if (next === 'light' || next === 'dark') {
      // Don't re-write localStorage — another window already did
      applyMode(next, false)
    }
  })
}

export function useTheme() {
  bindStorageListener()

  const isDark = computed(() => mode.value === 'dark')
  const isLight = computed(() => mode.value === 'light')

  /** Naive UI theme object — null = light, darkTheme = dark */
  const naiveTheme = computed<GlobalTheme | null>(() =>
    mode.value === 'dark' ? darkTheme : null,
  )

  /** Naive UI theme overrides for current mode */
  const themeOverrides = computed(() => buildThemeOverrides(mode.value))

  function setMode(next: ThemeMode) {
    if (next === mode.value) return
    applyMode(next)
  }

  function toggleMode() {
    applyMode(mode.value === 'dark' ? 'light' : 'dark')
  }

  /** Call once at app boot so CSS vars + Naive stay in sync with persisted mode */
  function initTheme() {
    applyMode(mode.value)
  }

  return {
    mode: readonly(mode),
    isDark,
    isLight,
    naiveTheme,
    themeOverrides,
    setMode,
    toggleMode,
    initTheme,
  }
}
