<template>
  <div class="danmaku-window">
    <!-- 弹幕容器:透明背景,只有弹幕气泡有颜色 -->
    <div class="danmaku-layer">
      <div
        v-for="d in activeDanmaku"
        :key="d.id"
        class="danmaku-item"
        :class="kindClass(d.kind)"
        :style="itemStyle(d)"
      >
        {{ d.text }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'

// 全屏透明弹幕窗口:鼠标点击穿透(依赖后端已启用 setIgnoreCursorEvents)
interface DanmakuItem {
  id: number
  text: string
  kind: string
  top: number
  duration: number
}

const activeDanmaku = ref<DanmakuItem[]>([])
let nextId = 1
let unlistenSSE: UnlistenFn | null = null
let eventSourceConnected = false

// ---- SSE 连接:订阅后端 /pet/events,收到 type=danmaku 即飘字 ----
const BACKEND_URL = 'http://127.0.0.1:8000'

function connectSSE() {
  if (eventSourceConnected) return
  eventSourceConnected = true
  const es = new EventSource(`${BACKEND_URL}/pet/events`)
  // 后端 format_sse 发的是命名事件(event: danmaku),必须用 addEventListener 接收
  es.addEventListener('danmaku', (ev) => {
    try {
      const data = JSON.parse((ev as MessageEvent).data)
      if (data.text) {
        spawnDanmaku(String(data.text), String(data.kind || 'idle'))
      }
    } catch { /* ignore */ }
  })
  // onmessage 兜底:兼容不带 event 字段的默认消息
  es.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data)
      if (data.type === 'danmaku' && data.text) {
        spawnDanmaku(String(data.text), String(data.kind || 'idle'))
      }
    } catch { /* ignore */ }
  }
  es.onerror = () => {
    eventSourceConnected = false
    try { es.close() } catch { /* ignore */ }
    setTimeout(() => connectSSE(), 3000)
  }
}

function spawnDanmaku(text: string, kind = 'idle') {
  const id = nextId++
  const item: DanmakuItem = {
    id,
    text,
    kind,
    top: 12 + Math.random() * 60, // 12%~72% 高度
    duration: 8000 + Math.random() * 4000, // 8~12s 飘完
  }
  activeDanmaku.value.push(item)
  // 动画结束后移除
  setTimeout(() => {
    activeDanmaku.value = activeDanmaku.value.filter((d) => d.id !== id)
  }, item.duration + 200)
}

/** kind → 样式类:完成 / 出错 / 时段问候 各有强调色,其余走默认柔和 */
function kindClass(kind: string): string {
  if (kind === 'complete') return 'dm-complete'
  if (kind === 'error') return 'dm-error'
  if (['morning', 'afternoon', 'evening', 'night'].includes(kind)) return 'dm-greeting'
  return 'dm-idle'
}

function itemStyle(d: DanmakuItem) {
  return {
    top: `${d.top}%`,
    '--dur': `${d.duration}ms`,
  }
}

onMounted(async () => {
  try {
    const win = getCurrentWindow()
    // 开启鼠标点击穿透(权限已在 capabilities 配置)
    await win.setIgnoreCursorEvents(true)
    await win.setFocusable(false)
  } catch (e) {
    console.warn('[danmaku] setIgnoreCursorEvents failed:', e)
  }
  // 订阅同窗口 Tauri 事件(Home 窗口转发弹幕)
  try {
    unlistenSSE = await listen<{ text: string; kind?: string }>('danmaku-text', (event) => {
      if (event.payload?.text) spawnDanmaku(event.payload.text, event.payload.kind || 'idle')
    })
  } catch (e) {
    console.warn('[danmaku] listen failed:', e)
  }
  // 直接连后端 SSE(与 Home 同一总线)
  connectSSE()
})

onUnmounted(() => {
  if (unlistenSSE) {
    unlistenSSE()
    unlistenSSE = null
  }
})
</script>

<style scoped>
.danmaku-window {
  position: fixed;
  inset: 0;
  background: transparent;
  overflow: hidden;
  pointer-events: none; /* CSS 层也不吃事件,双保险 */
  user-select: none;
}

.danmaku-layer {
  position: absolute;
  inset: 0;
}

/* ── 弹幕气泡:暖色主题胶囊,任何桌面上都可读 ── */
.danmaku-item {
  position: absolute;
  left: 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
  border-radius: var(--radius-full, 999px);
  font-family: var(--font-sans);
  font-size: 19px;
  font-weight: 600;
  letter-spacing: 0.02em;
  white-space: nowrap;
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid var(--accent-border, rgba(239, 107, 110, 0.28));
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.08));
  animation: danmaku-move var(--dur, 10s) linear forwards;
  will-change: transform;
}

/* 左侧小色点:完成 = 联想色 / 出错 = 错误红 / 问候 = 信息蓝,其余柔和灰 */
.danmaku-item::before {
  content: '';
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--gray-300);
}
.dm-complete::before {
  background: var(--accent-500);
  box-shadow: 0 0 6px var(--accent-glow, rgba(239, 107, 110, 0.14));
}
.dm-error::before {
  background: var(--error);
}
.dm-greeting::before {
  background: var(--info);
}

/* 完成 / 出错 气泡边框强调,问候柔和一点 */
.dm-complete {
  border-color: var(--accent-500);
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.88),
    rgba(255, 227, 204, 0.82)
  );
}
.dm-error {
  border-color: var(--error);
}
.dm-greeting {
  border-color: var(--success, #4e9a6e);
}

/* 暗色模式:深色暖炭气泡,保证可读 */
[data-theme='dark'] .danmaku-item {
  background: rgba(30, 25, 22, 0.8);
  border-color: var(--accent-border, rgba(247, 168, 91, 0.38));
  box-shadow: var(--shadow-md, 0 6px 18px rgba(0, 0, 0, 0.36));
}
[data-theme='dark'] .danmaku-item::before {
  background: var(--gray-600);
}
[data-theme='dark'] .dm-complete {
  background: linear-gradient(
    135deg,
    rgba(42, 34, 30, 0.85),
    rgba(247, 168, 91, 0.28)
  );
}
[data-theme='dark'] .dm-error {
  background: rgba(42, 34, 30, 0.85);
}
[data-theme='dark'] .dm-greeting {
  background: rgba(42, 34, 30, 0.85);
}

@keyframes danmaku-move {
  from {
    transform: translateX(-100%);
  }
  to {
    transform: translateX(100vw);
  }
}
</style>