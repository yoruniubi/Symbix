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
        @click="onDanmakuClick(d)"
      >
        {{ d.text }}
        <!-- 主动搭话气泡带「点击开聊」提示 -->
        <span v-if="d.kind === 'proactive'" class="dm-hint">{{ t('chat.tapToChat') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { getCurrentWindow, cursorPosition } from '@tauri-apps/api/window'
import { useI18n } from 'vue-i18n'
// 后端端口是动态的,SSE(EventSource)不走 fetch 改写,必须直接引用
import { BACKEND_URL } from '@/utils/backend'

// 全屏透明弹幕窗口。
// 主动搭话要能点,但整窗一旦不穿透就会吃掉**整块屏幕**的点击,所以做法是:
// 平时保持穿透,只在鼠标压在主动搭话气泡上时(轮询命中测试)临时解除,移开立刻恢复。
// 气泡本身仍用 CSS 动画飘(和普通弹幕同一套 keyframes),所以方向和速度天然一致。

const { t } = useI18n()

interface DanmakuItem {
  id: number
  text: string
  kind: string
  top: number
  duration: number
  memory?: string
}

const activeDanmaku = ref<DanmakuItem[]>([])
let nextId = 1
let es: EventSource | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
/** 已处理过的事件 id:防同一条事件插两次(SSE 重连/多连接时最容易发生) */
const seenEventIds = new Set<string>()

// ---- 命中测试:决定这一刻要不要解除穿透 ----
const POLL_MS = 70
/** 命中框外扩几个像素,避免边缘疯狂抖动 */
const HIT_MARGIN = 6
let pollTimer: ReturnType<typeof setInterval> | null = null
/** 当前窗口是否处于穿透状态 */
let ignoring = true
/** cursorPosition 不可用(权限/平台问题)时置位:退化成「只显示不可点」,绝不能锁屏 */
let pollBroken = false
let winOriginX = 0
let winOriginY = 0
let dpr = 1

async function applyIgnore(through: boolean) {
  ignoring = through
  try {
    await getCurrentWindow().setIgnoreCursorEvents(through)
  } catch (e) {
    console.warn('[danmaku] setIgnoreCursorEvents failed:', e)
  }
}

/** 鼠标是否压在某个主动搭话气泡上 */
async function pollHit(): Promise<void> {
  if (pollBroken) return
  const items = document.querySelectorAll<HTMLElement>('.danmaku-item.dm-proactive')
  if (!items.length) {
    // 屏上没有可点的气泡 → 必须穿透
    if (!ignoring) await applyIgnore(true)
    return
  }
  let cur: { x: number; y: number }
  try {
    cur = await cursorPosition()
  } catch (e) {
    pollBroken = true
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = null
    console.warn('[danmaku] cursorPosition 不可用,主动搭话气泡改为只展示不响应点击:', e)
    await applyIgnore(true)
    return
  }
  // cursorPosition 是屏幕物理像素,换算成窗口内的 CSS 像素再和 DOM 矩形比
  const x = (cur.x - winOriginX) / dpr
  const y = (cur.y - winOriginY) / dpr
  let hit = false
  items.forEach((el) => {
    if (hit) return
    const r = el.getBoundingClientRect()
    if (
      x >= r.left - HIT_MARGIN && x <= r.right + HIT_MARGIN
      && y >= r.top - HIT_MARGIN && y <= r.bottom + HIT_MARGIN
    ) {
      hit = true
    }
  })
  if (hit === !ignoring) return
  await applyIgnore(!hit)
}

async function startHitTest() {
  try {
    const win = getCurrentWindow()
    dpr = (await win.scaleFactor()) || 1
    const pos = await win.outerPosition()
    winOriginX = pos.x
    winOriginY = pos.y
  } catch (e) {
    console.warn('[danmaku] hit test init failed:', e)
  }
  pollTimer = setInterval(() => { void pollHit() }, POLL_MS)
}

// ---- SSE 连接:订阅后端 /pet/events ----
function connectSSE() {
  if (es) return
  es = new EventSource(`${BACKEND_URL}/pet/events`)
  // 后端 format_sse 发的是命名事件(event: danmaku / proactive),必须用 addEventListener
  es.addEventListener('danmaku', (ev) => {
    handleEvent((ev as MessageEvent).data)
  })
  es.addEventListener('proactive', (ev) => {
    handleEvent((ev as MessageEvent).data)
  })
  // onmessage 兜底:兼容不带 event 字段的默认消息
  es.onmessage = (ev) => handleEvent(ev.data)
  es.onerror = () => {
    es?.close()
    es = null
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(() => connectSSE(), 3000)
  }
}

/** 统一入口:去重后按 type 分派 */
function handleEvent(raw: string) {
  let data: any
  try {
    data = JSON.parse(raw)
  } catch {
    return
  }
  if (!data?.text) return
  // 同一条事件只认一次(后端每条事件都带 id;老版本没有就退化成 ts+text)
  const key = String(data.id || `${data.ts ?? ''}|${data.text}`)
  if (seenEventIds.has(key)) return
  seenEventIds.add(key)
  if (seenEventIds.size > 200) {
    // 只保留最近的一段,避免长跑期间无限增长
    const keep = Array.from(seenEventIds).slice(-100)
    seenEventIds.clear()
    keep.forEach((k) => seenEventIds.add(k))
  }
  const kind = String(data.type === 'proactive' ? 'proactive' : data.kind || 'idle')
  spawnDanmaku(String(data.text), kind, data.memory ? String(data.memory) : undefined)
}

function spawnDanmaku(text: string, kind = 'idle', memory?: string) {
  const id = nextId++
  const item: DanmakuItem = {
    id,
    text,
    kind,
    memory,
    top: 12 + Math.random() * 60, // 12%~72% 高度
    duration: kind === 'proactive' ? 16000 : 8000 + Math.random() * 4000,
  }
  activeDanmaku.value.push(item)
  setTimeout(() => {
    activeDanmaku.value = activeDanmaku.value.filter((d) => d.id !== id)
  }, item.duration + 200)
}

/** 点击主动搭话气泡 → 广播给 Home 窗打开聊天窗并带入上下文 */
function onDanmakuClick(d: DanmakuItem) {
  if (d.kind !== 'proactive') return
  import('@tauri-apps/api/event').then(({ emit }) => {
    emit('proactive-open-chat', { text: d.text, memory: d.memory || '' }).catch(() => undefined)
  })
  activeDanmaku.value = activeDanmaku.value.filter((x) => x.id !== d.id)
  // 点完立刻恢复穿透,不等下一轮轮询
  void applyIgnore(true)
}

/** kind → 样式类:完成 / 出错 / 时段问候 / 主动搭话 各有强调,其余走默认柔和 */
function kindClass(kind: string): string {
  if (kind === 'complete') return 'dm-complete'
  if (kind === 'error') return 'dm-error'
  if (['morning', 'afternoon', 'evening', 'night'].includes(kind)) return 'dm-greeting'
  if (kind === 'proactive') return 'dm-proactive'
  return 'dm-idle'
}

function itemStyle(d: DanmakuItem) {
  return {
    top: `${d.top}%`,
    '--dur': `${d.duration}ms`,
  }
}

onMounted(async () => {
  const win = getCurrentWindow()
  try {
    // 默认穿透 + 不可聚焦(权限已在 capabilities 配置)
    await win.setIgnoreCursorEvents(true)
    await win.setFocusable(false)
  } catch (e) {
    console.warn('[danmaku] window init failed:', e)
  }
  connectSSE()
  await startHitTest()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
  if (reconnectTimer) clearTimeout(reconnectTimer)
  reconnectTimer = null
  // 断开 SSE:否则重挂载后会有两条连接,同一条事件被处理两次(气泡会重复)
  if (es) {
    try { es.close() } catch { /* ignore */ }
    es = null
  }
  // 离场前确保恢复穿透
  void applyIgnore(true)
})
</script>

<style scoped>
.danmaku-window {
  position: fixed;
  inset: 0;
  background: transparent;
  overflow: hidden;
  pointer-events: none; /* CSS 层默认不吃事件;主动搭话气泡单独放行 */
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

/* 主动搭话:强调色 + 可点(鼠标压上来时窗才会临时解除穿透) */
.dm-proactive {
  cursor: pointer;
  pointer-events: auto; /* 父层 none,气泡自身要能接住点击 */
  border-color: var(--accent-500);
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.92),
    rgba(255, 214, 224, 0.86)
  );
  animation: danmaku-move var(--dur, 16s) linear forwards,
    proactive-pulse 2.4s ease-in-out infinite;
}
.dm-proactive::before {
  background: var(--accent-500);
}
.dm-proactive:hover {
  filter: brightness(1.05);
  /* 鼠标压上来就暂停飘动,方便对准点击(此时窗已由命中测试解除穿透) */
  animation-play-state: paused;
}
.dm-hint {
  font-size: 13px;
  font-weight: 500;
  opacity: 0.65;
}
@keyframes proactive-pulse {
  0%,
  100% {
    box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.08));
  }
  50% {
    box-shadow:
      0 0 0 6px var(--accent-glow, rgba(239, 107, 110, 0.14)),
      var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.08));
  }
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
[data-theme='dark'] .dm-proactive {
  background: linear-gradient(
    135deg,
    rgba(42, 34, 30, 0.88),
    rgba(233, 92, 122, 0.3)
  );
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
