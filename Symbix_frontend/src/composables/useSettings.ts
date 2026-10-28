import { ref, readonly } from 'vue'
import { BACKEND_URL } from '@/utils/backend'

interface Settings {
  apiKey: string
  baseUrl: string
  model: string
  systemPrompt: string
  // 子 Agent(delegate_task)专用模型;留空表示与主模型相同
  subModel: string
}

const settings = ref<Settings>({
  apiKey: '',
  baseUrl: '',
  model: '',
  systemPrompt: '',
  subModel: '',
})

/**
 * 后端 providers.json 里是否已有可用密钥。
 *
 * 密钥只在后端保存(前端从不持有),这里只同步一个布尔值,用来避免
 * 「后端明明配好了、界面却警告未配置」的误报。
 */
const backendHasKey = ref(false)

function persist() {
  localStorage.setItem('symbix_settings', JSON.stringify(settings.value))
}

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
    persist()
  }

  /**
   * 从后端 providers.json 补齐前端空缺的 baseUrl / model。
   *
   * 只补空值,不覆盖用户已经填好的内容;密钥不回传,仅更新 backendHasKey。
   * 典型场景:换机器、换 webview origin(dev 与安装版 localStorage 不共享)、
   * 或误清了 localStorage —— 后端配置还在,不该让人重填一遍。
   */
  async function syncFromBackend(): Promise<void> {
    try {
      const res = await fetch(`${BACKEND_URL}/providers`)
      if (!res.ok) return
      const data = await res.json()
      backendHasKey.value = !!data.active_has_key
      const active = data.active ? data.providers?.[data.active] : null
      if (!active) return
      let changed = false
      if (!settings.value.baseUrl && active.api_base) {
        settings.value.baseUrl = active.api_base
        changed = true
      }
      if (!settings.value.model && active.model) {
        settings.value.model = active.model
        changed = true
      }
      if (!settings.value.subModel && active.sub_model) {
        settings.value.subModel = active.sub_model
        changed = true
      }
      if (changed) persist()
    } catch {
      // 后端未就绪时静默跳过,下次进入页面还会再试
    }
  }

  function resetSettings() {
    settings.value = { apiKey: '', baseUrl: '', model: '', systemPrompt: '', subModel: '' }
    localStorage.removeItem('symbix_settings')
  }

  return {
    settings: readonly(settings),
    backendHasKey: readonly(backendHasKey),
    loadSettings,
    saveSettings,
    syncFromBackend,
    resetSettings,
  }
}
