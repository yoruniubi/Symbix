import { onBeforeUnmount, onMounted, ref } from 'vue'
import { panelTokens } from '@/theme'

type ResizablePanelOptions = {
  storageKey: string
  defaultWidth?: number
  minWidth?: number
  maxWidth?: number
}

/** Shared right-edge resizing behavior for the chat side panels. */
export function useResizablePanel(options: ResizablePanelOptions) {
  const minWidth = options.minWidth ?? panelTokens.minWidth
  const maxWidth = options.maxWidth ?? panelTokens.maxWidth
  const defaultWidth = options.defaultWidth ?? panelTokens.defaultWidth
  const width = ref(defaultWidth)
  const isResizing = ref(false)
  let startX = 0
  let startWidth = defaultWidth

  const clamp = (value: number) => Math.min(maxWidth, Math.max(minWidth, value))

  onMounted(() => {
    try {
      const saved = localStorage.getItem(options.storageKey)
      if (saved) {
        const parsed = Number.parseInt(saved, 10)
        if (!Number.isNaN(parsed)) width.value = clamp(parsed)
      }
    } catch { /* localStorage may be unavailable */ }
  })

  function startResize(event: MouseEvent) {
    isResizing.value = true
    startX = event.clientX
    startWidth = width.value
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    window.addEventListener('mousemove', onResize)
    window.addEventListener('mouseup', stopResize)
  }

  function onResize(event: MouseEvent) {
    if (isResizing.value) width.value = clamp(startWidth + event.clientX - startX)
  }

  function stopResize() {
    if (!isResizing.value) return
    isResizing.value = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    window.removeEventListener('mousemove', onResize)
    window.removeEventListener('mouseup', stopResize)
    try { localStorage.setItem(options.storageKey, String(width.value)) } catch { /* ignore */ }
  }

  onBeforeUnmount(() => {
    window.removeEventListener('mousemove', onResize)
    window.removeEventListener('mouseup', stopResize)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  })

  return { width, isResizing, startResize }
}