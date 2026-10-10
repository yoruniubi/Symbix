import { ref } from 'vue'
import { stopSpeak } from '@/utils/backend'

const KEY = 'symbix_read_aloud'
const readAloud = ref(localStorage.getItem(KEY) === '1')
let synced = false

/** 聊天窗口与桌宠窗口是两个 webview:靠 storage 事件让开关保持一致 */
function syncFromStorage(e: StorageEvent) {
  if (e.key !== KEY) return
  readAloud.value = e.newValue === '1'
  if (!readAloud.value) stopSpeak()
}

export function useReadAloud() {
  if (!synced) {
    synced = true
    window.addEventListener('storage', syncFromStorage)
  }

  function setReadAloud(on: boolean) {
    readAloud.value = on
    localStorage.setItem(KEY, on ? '1' : '0')
    if (!on) stopSpeak()
  }

  return { readAloud, setReadAloud }
}
