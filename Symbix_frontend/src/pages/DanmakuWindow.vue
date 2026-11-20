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
import { startMemorySentinel } from '@/utils/memorySentinel'

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
/** 内存哨兵停止函数 */
let stopMemSentinel: (() => void) | null = null
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

/** 命中测试重入锁:上一轮没跑完就跳过本轮。
 *
 * 必须要有。pollHit 里两个 await 都是跨进程 IPC(cursorPosition 读全局鼠标、
 * setIgnoreCursorEvents 改穿透状态),系统一忙就会变慢;而 setInterval 不看
 * 上一轮是否结束,未完成的轮次会不断堆叠,每个都持有闭包与 DOM 引用 ——
 * 越堆越慢、越慢越堆,长时间运行后渲染进程内存就被吃穿。
 */
let polling = false

/** 鼠标是否压在某个主动搭话气泡上 */
async function pollHit(): Promise<void> {
  if (pollBroken || polling) return
  polling = true
  try {
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
    // cursorPosition 是屏幕物理像素,换算成窗口内的 CSS 像素再和 DOM 矩形比。
    // 矩形只取一次并当场读完四个边:getBoundingClientRect 会强制同步布局,
    // 每 70ms 对每个气泡各调一次纯属浪费。
    const x = (cur.x - winOriginX) / dpr
    const y = (cur.y - winOriginY) / dpr
    let hit = false
    for (const el of Array.from(items)) {
      const r = el.getBoundingClientRect()
      const left = r.left - HIT_MARGIN
      const right = r.right + HIT_MARGIN
      const top = r.top - HIT_MARGIN
      const bottom = r.bottom + HIT_MARGIN
      if (x >= left && x <= right && y >= top && y <= bottom) {
        hit = true
        break
      }
    }
    if (hit === !ignoring) return
    await applyIgnore(!hit)
  } finally {
    polling = false
  }
}

/** 屏幕上有几条主动搭话气泡(不用查 DOM,直接看数据源) */
function proactiveCount(): number {
  return activeDanmaku.value.reduce((n, d) => n + (d.kind === 'proactive' ? 1 : 0), 0)
}

/** 按需启停命中测试:没有可点的气泡就不该每 70ms 扫一遍文档树。 */
function syncHitTest() {
  const need = proactiveCount() > 0
  if (need && pollTimer === null) {
    pollTimer = setInterval(() => { void pollHit() }, POLL_MS)
  } else if (!need && pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
    // 气泡没了就必须恢复穿透,不能停在「吃点击」的状态
    if (!ignoring) void applyIgnore(true)
  }
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
  // 只读一次几何,轮询等真出现主动搭话气泡时再起
  syncHitTest()
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

/** 所有在途的移除定时器:卸载时统一清掉,否则它们会去改已销毁的 ref */
const removeTimers = new Set<ReturnType<typeof setTimeout>>()

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
  if (kind === 'proactive') syncHitTest()
  const timer = setTimeout(() => {
    removeTimers.delete(timer)
    activeDanmaku.value = activeDanmaku.value.filter((d) => d.id !== id)
    // 最后一条主动搭话消失时,轮询该停了(顺带恢复穿透)
    if (kind === 'proactive') syncHitTest()
  }, item.duration + 200)
  removeTimers.add(timer)
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
  syncHitTest()
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
  // 这个窗口是全屏透明的,一旦渲染进程被 OOM 杀掉,透明合成失效就会露出
  // 白底盖满整个屏幕(用户看到的「弹窗覆盖整个界面」)。之前它没上报内存,
  // 日志里只有 home/chat,所以从没被发现过。这里补上,让增长可见。
  stopMemSentinel = startMemorySentinel({
    window: 'danmaku',
    // 弹幕窗没有会话,不自动重载 —— 重载会清屏且用户可能正要点气泡
    autoReload: false,
    warnMB: 800,
    onWarn: (s) => console.warn('[danmaku] 内存偏高:', s.heapMB.toFixed(0), 'MB'),
  })
})

onUnmounted(() => {
  stopMemSentinel?.()
  stopMemSentinel = null
  for (const tid of removeTimers) clearTimeout(tid)
  removeTimers.clear()
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
