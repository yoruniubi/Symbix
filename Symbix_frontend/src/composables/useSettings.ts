import { ref, readonly } from 'vue'

interface Settings {
  apiKey: string
  baseUrl: string
  model: string
}

const settings = ref<Settings>({
  apiKey: '',
  baseUrl: '',
  model: '',
})

export function useSettings() {
  function loadSettings() {
    const saved = localStorage.getItem('symbix_settings')
    if (saved) {
      try {
        Object.assign(settings.value, JSON.parse(saved))
      } catch {}
    }
  }

  function saveSettings(data: Partial<Settings>) {
    Object.assign(settings.value, data)
    localStorage.setItem('symbix_settings', JSON.stringify(settings.value))
  }

  function resetSettings() {
    settings.value = { apiKey: '', baseUrl: '', model: '' }
    localStorage.removeItem('symbix_settings')
  }

  return {
    settings: readonly(settings),
    loadSettings,
    saveSettings,
    resetSettings,
  }
}
