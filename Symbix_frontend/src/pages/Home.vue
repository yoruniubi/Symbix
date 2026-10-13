<template>
  <div class="pet-root">
    <div class="pet-container">
      <canvas
        ref="canvasRef"
        class="pet-canvas"
        @click="handlePetClick"
        @mousedown="onCanvasMousedown"
        @mouseenter="onPetMouseEnter"
      />
      <div class="btn-col">
        <n-tooltip placement="right" trigger="hover">
            <template #trigger>
              <button class="icon-btn" @click="openChatWindow" :aria-label="$t('home.chat')">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
              </button>
            </template>
            {{ $t('home.chat') }}
          </n-tooltip>

        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <button class="icon-btn" @click="openSkinWindow" :aria-label="$t('home.skin')">
              <svg width="18" height="18" viewBox="0 0 1024 1024" fill="currentColor">
                <path d="M752.8 143.2c3.2 0 6.3 1.3 8.5 3.5L955.6 341c5.5 5.5 5.5 14.3 0 19.8L864 452.5l-96-96V895H448v1H256V357.5l-96 96-91.6-91.6c-5.5-5.5-5.5-14.3 0-19.8L263 147.5c2.3-2.3 5.3-3.5 8.5-3.5H351c33.4 26.9 92.6 64 164.6 64 72.1 0 131.4-37.2 164.8-64.2l72.3-0.6h0.1z m0-64h-0.6l-83.8 0.7c-7.6 0.1-15 2.8-20.7 7.8-19.6 17-71.3 56.3-132.1 56.3-60.6 0-112.3-39.1-132-56.2-5.8-5.1-13.3-7.8-21-7.8h-91c-20.2 0-39.5 8-53.7 22.3L23.1 296.8c-30.5 30.5-30.5 79.8 0 110.3L128 512c8.8 8.8 20.4 13.3 32 13.3s23.2-4.4 32-13.3v416c0 17.7 14.3 32 32 32h288v-1h288c17.7 0 32-14.3 32-32V511c8.8 8.8 20.4 13.3 32 13.3s23.2-4.4 32-13.3l104.8-104.8c30.5-30.5 30.5-79.8 0-110.3L806.5 101.5c-14.2-14.2-33.6-22.3-53.7-22.3z"/>
              </svg>
            </button>
          </template>
          {{ $t('home.skin') }}
        </n-tooltip>

        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <button class="icon-btn" @click="openJournalWindow" :aria-label="$t('home.journal')">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
                <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
              </svg>
            </button>
          </template>
          {{ $t('home.journal') }}
        </n-tooltip>

        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <button class="icon-btn" @click="openSettingWindow" :aria-label="$t('home.settings')">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
            </button>
          </template>
          {{ $t('home.settings') }}
        </n-tooltip>
      </div>
    </div>

    <!-- 对话气泡 -->
    <Transition name="bubble">
      <div v-if="bubbleText" class="speech-bubble">{{ bubbleText }}</div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { WebviewWindow } from '@tauri-apps/api/webviewWindow'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import { Application, Texture, AnimatedSprite, Rectangle, TextureSource, Assets } from 'pixi.js'

import { useI18n } from 'vue-i18n'
import { speak } from '@/utils/backend'
import { fitsSheetContract, SHEET_COLS, SHEET_FRAME_H, SHEET_FRAME_W, SHEET_MIN_ROWS } from '@/utils/petSheet'
import { useReadAloud } from '@/composables/useReadAloud'

const { t } = useI18n()
const router = useRouter()
const { readAloud } = useReadAloud()
const appWindow = getCurrentWindow()

// ---- 状态 ----
const bubbleText = ref('')

const hello_list = [t('home.petGreeting'), t('home.petGreetingWelcome'), t('home.petGreetingHelp'), t('home.petGreetingChat')]
const greeting = hello_list[Math.floor(Math.random() * hello_list.length)]

// ---- 桌宠模式 ----\r
type PetMode = 'work' | 'relax'
const petMode = ref<PetMode>((localStorage.getItem('petMode') as PetMode) || 'relax')

function togglePetMode() {
  // 第三按钮已改为手账;工作/休闲模式保留在 localStorage,不再提供切换入口。
}

async function snapToBottomRight() {
  try {
    if (!(window as any).__TAURI_INTERNALS__) return
    const { PhysicalPosition, getCurrentWindow } = await import('@tauri-apps/api/window')
    const win = getCurrentWindow()

    try {
      const { availableMonitors } = await import('@tauri-apps/api/window')
      const monitors = await availableMonitors()
      if (monitors.length > 0) {
        const primary = monitors[0]
        const factor = primary.scaleFactor || 1
        const screenW = primary.size.width / factor
        const screenH = primary.size.height / factor
        const winSize = await win.outerSize()
        const w = winSize.width / factor
        const h = winSize.height / factor
        const px = Math.round(Math.max(0, screenW - w - 16) * factor)
        const py = Math.round(Math.max(0, screenH - h - 48) * factor)
        await win.setPosition(new PhysicalPosition(px, py))
        return
      }
    } catch { /* fallthrough */ }

    const screenW = window.screen.availWidth
    const screenH = window.screen.availHeight
    const { width: w, height: h } = (await win.outerSize()) || { width: 250, height: 240 }
    const scale = await win.scaleFactor().catch(() => 1)
    const px = Math.round((screenW - w / scale - 20) * scale)
    const py = Math.round((screenH - h / scale - 20) * scale)
    await win.setPosition(new PhysicalPosition(px, py))
  } catch { /* silent */ }
}

// ---- PixiJS ----
const canvasRef = ref<HTMLCanvasElement>()
const FRAME_W = 192
const FRAME_H = 208
// Pixi 默认 ticker 是 60Hz;动画速度应以 ticker 频率为基准,否则会出现动作忽快忽慢。
const TICKER_FPS = 60
// 按动作分级控制速度,避免统一降速后单帧停留太久。
const STATE_FPS = {
  // idle 是持续循环的 6 帧动作;6 FPS 会让每一帧停留过久,看起来像卡顿。
  // 提高到 10 FPS 后仍保留像素动画的节奏,但帧间过渡更连贯。
  idle: 5.5,
  waving: 6,
  jumping: 6.5,
  failed: 4.5,
  waiting: 5.5,
  review: 4.5,
  running: 8,
  runningRight: 8,
  runningLeft: 8,
} as const

// 一次性动作播完后留一点"落地/回神"的时间,避免立刻硬切到 idle。
const ACTION_SETTLE_MS: Partial<Record<PetState, number>> = {
  waving: 220,
  jumping: 320,
  failed: 520,
  review: 700,
}
// 思考先停一下再开始,让"收到任务 → 回神 → 思考"更自然。
const ACTION_START_DELAY_MS: Partial<Record<PetState, number>> = {
  review: 480,
}

// 标准 Petdex 8x9 spritesheet 行定义
const ROWS = {
  idle:         { row: 0, frames: 6 },
  runningRight: { row: 1, frames: 8 },
  runningLeft:  { row: 2, frames: 8 },
  waving:       { row: 3, frames: 4 },
  jumping:      { row: 4, frames: 5 },
  failed:       { row: 5, frames: 7 },
  waiting:      { row: 6, frames: 6 }, // 被抱起时循环(备用)
  running:      { row: 7, frames: 6 },
  review:       { row: 8, frames: 6 },
} as const

type PetState = keyof typeof ROWS
const LOOP_STATES: ReadonlySet<PetState> = new Set(['idle', 'waiting', 'running', 'runningRight', 'runningLeft'])

function isLoopState(state: PetState) {
  return LOOP_STATES.has(state) || (state === 'review' && agentThinking)
}

// 个别动作的原图帧并非严格按时间顺序排列,允许在不修改素材的情况下重排/重复帧。
// failed:站立 → 蹲下 → 跪地 → 趴倒,最后重复趴倒作为落地停留。
const FRAME_SEQUENCES: Partial<Record<PetState, readonly number[]>> = {
  failed: [0, 1, 3, 5, 6, 6, 6],
}

function animationSpeedFor(state: PetState) {
  return STATE_FPS[state] / TICKER_FPS
}


let app: Application | null = null
let sprite: AnimatedSprite | null = null
let baseSource: TextureSource | null = null
let currentState: PetState = 'idle'
let randomTimer: ReturnType<typeof setTimeout> | null = null
let actionStartTimer: ReturnType<typeof setTimeout> | null = null
let actionSettleTimer: ReturnType<typeof setTimeout> | null = null
let actionToken = 0
let lastRandomAction: PetState | '' = ''
// Agent 正在处理请求时,review 必须循环播放,直到收到完成/错误/中止状态。
let agentThinking = false

/**
 * Agent 侧触发的循环动作(running / waiting 等)必须有上限。
 * 这类动作语义上是「拖拽奔跑 / 被抱起」的常驻循环,本应由本地 dragSession 驱动;
 * 一旦被远程事件打开又无人收尾,就会永远循环,把 thinking / idle 等状态机动作挤掉。
 */
const REMOTE_LOOP_MAX_MS = 3000
let remoteLoopTimer: ReturnType<typeof setTimeout> | null = null

function clearRemoteLoopTimer() {
  if (remoteLoopTimer != null) {
    clearTimeout(remoteLoopTimer)
    remoteLoopTimer = null
  }
}

/**
 * 拖拽奔跑(Windows / Tauri 要点):
 * 1. startDragging() 的 Promise 会立刻 resolve,不能当"拖拽结束"
 * 2. 进入原生拖拽后 webview 常立刻收到 pointerup,也不能靠它结束
 * 3. 正确做法:真正发生窗口位移才进入 running;位移停顿一段时间再回 idle
 */
let dragSession = false
let dragMoved = false
let suppressNextClick = false
let lastDragX: number | null = null
let lastDragY: number | null = null
let dragDir: 'left' | 'right' | null = null
let dragScaleFactor = 1
let lastJumpTime = 0
let unlistenMoved: (() => void) | null = null
let dragWatchTimer: ReturnType<typeof setInterval> | null = null
let lastMoveAt = 0
let sessionStartAt = 0

const DRAG_DIR_THRESHOLD = 3 // 逻辑像素:超过才算"在拖"
const DRAG_STOP_MS = 120 // 停顿 → 先停奔跑动画(会话保持,便于继续拖再跑)
const DRAG_STALE_MS = 1800 // 很久无位移 → 兜底结束会话(Windows 常丢真实 pointerup)
const CLICK_IDLE_MS = 400 // 按下后几乎没动 → 当点击,结束会话
const EARLY_POINTER_UP_MS = 300 // startDragging 后这段内的 pointerup 一律忽略

function clearDragWatch() {
  if (dragWatchTimer != null) {
    clearInterval(dragWatchTimer)
    dragWatchTimer = null
  }
}

function detachPointerEndListeners() {
  window.removeEventListener('pointerup', onGlobalPointerEnd, true)
  window.removeEventListener('mouseup', onGlobalPointerEnd, true)
  window.removeEventListener('pointercancel', onGlobalPointerEnd, true)
  window.removeEventListener('blur', onGlobalPointerEnd, true)
}

function attachPointerEndListeners() {
  detachPointerEndListeners()
  // capture:尽量在被吞掉前收到松手;真实松手用于立刻停跑
  window.addEventListener('pointerup', onGlobalPointerEnd, true)
  window.addEventListener('mouseup', onGlobalPointerEnd, true)
  window.addEventListener('pointercancel', onGlobalPointerEnd, true)
  window.addEventListener('blur', onGlobalPointerEnd, true)
}

function isRunningState(state: PetState = currentState) {
  return state === 'runningRight' || state === 'runningLeft' || state === 'running'
}

function endDragSession(opts: { backToIdle: boolean; swallowClick: boolean }) {
  if (!dragSession && !dragWatchTimer) return
  dragSession = false
  clearDragWatch()
  detachPointerEndListeners()
  lastDragX = null
  lastDragY = null
  dragDir = null
  if (opts.swallowClick || dragMoved) suppressNextClick = true
  const wasRunning = isRunningState()
  dragMoved = false
  // onMoved 监听保持常驻,不在每次会话结束时拆掉
  if (opts.backToIdle && wasRunning) playState('idle', false)
}

function onGlobalPointerEnd() {
  if (!dragSession) return
  // Windows:startDragging 后立刻 pointerup,绝不能结束会话(否则轮询/位移检测全废)
  const sinceStart = performance.now() - sessionStartAt
  if (sinceStart < EARLY_POINTER_UP_MS) return
  // 已真正拖动过:松手 → idle;纯点击:交给 click / 超时
  if (!dragMoved) return
  endDragSession({ backToIdle: true, swallowClick: true })
}

function onDragPosition(xLogical: number, yLogical?: number) {
  if (!dragSession) return
  const x = Math.round(xLogical)

  if (lastDragX == null) {
    lastDragX = x
    lastDragY = yLogical != null ? Math.round(yLogical) : null
    return
  }

  const dx = x - lastDragX
  const adx = Math.abs(dx)
  let ady = 0
  if (yLogical != null) {
    const y = Math.round(yLogical)
    ady = Math.abs(y - (lastDragY ?? y))
    lastDragY = y
  }

  // 小抖动:吸收进基准,避免假位移
  if (adx < DRAG_DIR_THRESHOLD && ady < DRAG_DIR_THRESHOLD) {
    if (adx > 0) lastDragX = x
    return
  }

  lastDragX = x
  lastMoveAt = performance.now()
  dragMoved = true
  suppressNextClick = true

  // 垂直位移为主 → 跳跃(间隔 350ms, 且跳跃动画未播完时不再重触)
  if (ady >= adx && ady >= DRAG_DIR_THRESHOLD) {
    const now = performance.now()
    if (currentState !== 'jumping' && now - lastJumpTime >= 350) {
      lastJumpTime = now
      playState('jumping', true)
    }
    return
  }

  // 水平位移为主 → 奔跑
  if (adx >= DRAG_DIR_THRESHOLD) {
    const nextDir: 'left' | 'right' = dx > 0 ? 'right' : 'left'
    if (nextDir !== dragDir || !isRunningState()) {
      dragDir = nextDir
      playState(nextDir === 'right' ? 'runningRight' : 'runningLeft', false)
    }
  }
}

function startDragWatch() {
  clearDragWatch()
  lastMoveAt = performance.now()
  let polling = false

  // 50ms 轮询 outerPosition:onMoved 在部分 Windows 场景会漏事件
  dragWatchTimer = setInterval(() => {
    if (!dragSession) {
      clearDragWatch()
      return
    }
    if (polling) {
      checkDragIdle()
      return
    }
    polling = true
    void (async () => {
      try {
        const pos = await appWindow.outerPosition()
        if (dragSession) onDragPosition(pos.x / dragScaleFactor, pos.y / dragScaleFactor)
      } catch {
        // ignore
      } finally {
        polling = false
        if (dragSession) checkDragIdle()
      }
    })()
  }, 50)
}

function checkDragIdle() {
  if (!dragSession) return
  const idleFor = performance.now() - lastMoveAt
  if (dragMoved) {
    // 只停动画,不结束会话:按住鼠标停一下再拖,应能继续跑
    if (idleFor >= DRAG_STOP_MS && isRunningState()) {
      playState('idle', false)
      dragDir = null
    }
    // 兜底:很久无位移且收不到 pointerup 时结束
    if (idleFor >= DRAG_STALE_MS) {
      endDragSession({ backToIdle: true, swallowClick: true })
    }
  } else if (idleFor >= CLICK_IDLE_MS) {
    // 按下后几乎没移动:结束会话,保留 click
    endDragSession({ backToIdle: false, swallowClick: false })
  }
}

async function ensureDragMovedListener() {
  if (unlistenMoved) return
  try {
    unlistenMoved = await appWindow.onMoved(({ payload }) => {
      if (!dragSession) return
      // 拖动期间不要每个窗口位移事件都异步查询 scaleFactor;复用会话开始时
      // 缓存的比例,避免事件堆积导致方向判断和动画切换一卡一卡。
      onDragPosition(payload.x / dragScaleFactor)
    })
  } catch (e) {
    console.warn('onMoved listen failed:', e)
  }
}

async function onCanvasMousedown(e: MouseEvent) {
  // 工作模式下禁止拖动
  if (petMode.value === 'work') return
  if (e.button !== 0) return

  // 新会话:不立刻播奔跑,等窗口真的位移
  endDragSession({ backToIdle: false, swallowClick: false })
  dragSession = true
  dragMoved = false
  suppressNextClick = false
  dragDir = null
  lastDragX = null
  lastDragY = null
  sessionStartAt = performance.now()
  lastMoveAt = sessionStartAt

  dragScaleFactor = await appWindow.scaleFactor().catch(() => window.devicePixelRatio || 1)
  await ensureDragMovedListener()
  attachPointerEndListeners()
  startDragWatch()

  try {
    // 不要 await 当结束信号:Windows 上几乎立刻 resolve
    void appWindow.startDragging()
  } catch (err) {
    console.warn('startDragging failed:', err)
    endDragSession({ backToIdle: true, swallowClick: false })
  }
}




/** 像素风皮肤放大时必须 nearest 采样,否则会被插值糊掉;平滑矢量皮肤保持 linear */
function applyPetScaleMode(style?: string | null) {
  if (!baseSource) return
  try {
    baseSource.scaleMode = style === 'pixel' ? 'nearest' : 'linear'
  } catch (e) {
    console.warn('[pet] set scaleMode failed:', e)
  }
}

/**
 * 从 localStorage 推断某个 spritesheet 的画风:
 * 先查 customPets 里记住的皮肤(切换时写入),再查最近一次 petSwitchSignal。
 * 查不到 = 老数据 → 按平滑矢量处理。
 */
function currentPetStyle(preview: string): string | null {
  try {
    const saved = JSON.parse(localStorage.getItem('customPets') || '[]')
    const hit = Array.isArray(saved) ? saved.find((p: any) => p?.preview === preview) : null
    if (hit?.style) return hit.style
    const signal = JSON.parse(localStorage.getItem('petSwitchSignal') || 'null')
    if (signal?.spritesheetPath === preview && signal.style) return signal.style
  } catch { /* ignore */ }
  return null
}

function getFrames(
  source: TextureSource,
  row: number,
  frameCount: number,
  frameIndices?: readonly number[],
) {
  return Array.from({ length: frameCount }, (_, i) =>
    new Texture({
      source: source as TextureSource,
      frame: new Rectangle(
        (frameIndices?.[i] ?? i) * FRAME_W,
        row * FRAME_H,
        FRAME_W,
        FRAME_H,
      ),
    })
  )
}

function playStateNow(state: PetState, returnToIdle: boolean, token: number) {
  if (!sprite || !baseSource) return
  // 同一循环动作不要重开,否则拖拽中反复 set textures 会看起来只闪一帧
  if (state === currentState && isLoopState(state) && sprite.playing) {
    return
  }
  currentState = state
  const def = ROWS[state]
  sprite.textures = getFrames(
    baseSource as TextureSource,
    def.row,
    def.frames,
    FRAME_SEQUENCES[state],
  )
  sprite.animationSpeed = animationSpeedFor(state)
  sprite.loop = isLoopState(state)
  // 清掉上一个一次性动作的回调,避免旧动作完成时抢先把新动作切回 idle。
  sprite.onComplete = undefined
  // 更换 textures 后显式从第 0 帧开始播放。仅设置 textures 不保证 Pixi
  // 在所有版本/场景下仍会继续推进帧,尤其是上一个动作刚刚结束时。
  sprite.gotoAndPlay(0)

  if (returnToIdle && !sprite.loop) {
    const playing = state
    sprite.onComplete = () => {
      // 仅当仍是本次动作时回 idle,并留出一个短暂的自然停顿。
      if (currentState !== playing || token !== actionToken) return
      const settleMs = ACTION_SETTLE_MS[playing] ?? 0
      actionSettleTimer = setTimeout(() => {
        actionSettleTimer = null
        if (currentState === playing && token === actionToken) playState('idle', false)
      }, settleMs)
    }
  }
}

function playState(state: PetState, returnToIdle = true) {
  if (!sprite || !baseSource) return
  const token = ++actionToken
  // 任何新的状态切换都作废上一个远程循环动作的到期回调,避免它稍后抢状态。
  clearRemoteLoopTimer()
  if (actionStartTimer) {
    clearTimeout(actionStartTimer)
    actionStartTimer = null
  }
  if (actionSettleTimer) {
    clearTimeout(actionSettleTimer)
    actionSettleTimer = null
  }

  const delay = ACTION_START_DELAY_MS[state] ?? 0
  if (delay > 0 && state !== currentState) {
    // 思考前保持 idle,但不重置 idle 的当前帧,避免突然闪回第一帧。
    if (!isLoopState(currentState)) {
      currentState = 'idle'
      const idleDef = ROWS.idle
      sprite.textures = getFrames(baseSource as TextureSource, idleDef.row, idleDef.frames)
      sprite.animationSpeed = animationSpeedFor('idle')
      sprite.loop = true
      sprite.play()
    }
    actionStartTimer = setTimeout(() => {
      actionStartTimer = null
      if (token === actionToken) playStateNow(state, returnToIdle, token)
    }, delay)
    return
  }
  playStateNow(state, returnToIdle, token)
}

function pickRandomAction(actions: readonly PetState[], exclude?: string): PetState {
  const candidates = exclude ? actions.filter((a) => a !== exclude) : [...actions]
  if (candidates.length === 0) return actions[0]
  return candidates[Math.floor(Math.random() * candidates.length)]
}

function scheduleRandom(delayMs?: number) {
  randomTimer = setTimeout(() => {
    // 工作模式:不做随机动作,只保持 idle
    if (petMode.value !== 'relax') {
      scheduleRandom()
      return
    }
    if (currentState === 'idle' && !dragSession) {
      // 所有非循环动作池,充分展现活力
      const pool = ['waving', 'jumping', 'failed', 'review'] as const
      const act = pickRandomAction(pool, lastRandomAction)
      lastRandomAction = act
      playState(act)

      // 15% 概率在动作完毕后追加第二个动作(连招:更生动)
      if (Math.random() < 0.15) {
        const originalAct = act
        const secondPool = pool.filter(a => a !== originalAct)
        const secondAct = secondPool[Math.floor(Math.random() * secondPool.length)]
        // 在第一个动作播完后,短暂延迟再播第二个
        const frameCount = ROWS[act].frames
        const playTime = (frameCount / STATE_FPS[act]) * 1000
        setTimeout(() => {
          if (currentState === 'idle' && !dragSession) {
            lastRandomAction = secondAct
            playState(secondAct)
          }
        }, playTime + (ACTION_SETTLE_MS[act] ?? 0) + (ACTION_START_DELAY_MS[secondAct] ?? 0) + 120)
      }
    }
    // 随机间隔 3~9 秒,比之前更紧凑
    scheduleRandom()
  }, delayMs ?? (3000 + Math.random() * 6000))
}

function handlePetClick() {
  // 拖拽结束后紧随的 click 不触发,避免拖完立刻 jump
  if (suppressNextClick || dragMoved) {
    suppressNextClick = false
    return
  }
  // 若仍在会话但未真正拖动:当作点击
  if (dragSession && !dragMoved) {
    endDragSession({ backToIdle: false, swallowClick: false })
  }
  // 工作模式下只播气泡+waving,不做激进交互
  if (petMode.value === 'work') {
    playState('waving')
    showBubble(t('home.workingDnd'), 2500)
    return
  }
  // 点击时所有动作都可触发,包括 review(思考)
  const clickPool = ['waving', 'jumping', 'failed', 'review'] as const
  playState(clickPool[Math.floor(Math.random() * clickPool.length)])
  showBubble(greeting)
}

function onPetMouseEnter() {
  if (petMode.value === 'work') return
  if (currentState === 'idle' && !dragSession) {
    playState('waving')
  }
}

function showBubble(text: string, duration = 3000) {
  if (!text) return
  bubbleText.value = text
  if (bubbleClearTimer) clearTimeout(bubbleClearTimer)
  bubbleClearTimer = setTimeout(() => {
    bubbleText.value = ''
    bubbleClearTimer = null
  }, duration)
}

// ---- 后端桌宠事件(emit_pet_action → /pet/events SSE)----
const BACKEND_URL = 'http://127.0.0.1:8000'
const ACTION_ALIASES: Record<string, PetState> = {
  happy: 'jumping',
  celebrate: 'jumping',
  jump: 'jumping',
  wave: 'waving',
  thinking: 'review',
  sad: 'failed',
  error: 'failed',
  scheduled_job: 'jumping',  // 定时任务触发 → 开心跳一下
}

let petEventAbort: AbortController | null = null
let petEventReconnectTimer: ReturnType<typeof setTimeout> | null = null
let bubbleClearTimer: ReturnType<typeof setTimeout> | null = null
let lastRemoteActionId = ''

function resolvePetState(action: string | undefined | null): PetState | null {
  if (!action) return null
  const raw = String(action).trim()
  if (!raw) return null
  if (raw in ROWS) return raw as PetState
  const key = raw.replace(/[-_]/g, '').toLowerCase()
  const mapped = ACTION_ALIASES[key] || ACTION_ALIASES[raw]
  if (mapped) return mapped
  // runningRight / runningLeft 大小写容错
  if (key === 'runningright') return 'runningRight'
  if (key === 'runningleft') return 'runningLeft'
  if (key === 'running') return 'running'
  return null
}

function applyRemotePetAction(payload: {
  id?: string
  action?: string
  bubble?: string
  loop?: boolean
  source?: string
}) {
  // 定时任务通知:开关打开时才朗读其摘要(bubble)
  if ((payload.source === 'schedule' || payload.action === 'scheduled_job') && payload.bubble && readAloud.value) {
    speak(payload.bubble)
  }
  // 工作模式下忽略远程动作(仅接收 bubble 消息)
  if (petMode.value === 'work') {
    if (payload.bubble) showBubble(payload.bubble, 3200)
    return
  }
  if (payload.id && payload.id === lastRemoteActionId) return
  if (payload.id) lastRemoteActionId = payload.id

  // 拖爪奔跑优先,避免远程 idle 打断
  if (dragSession && dragMoved) return

  const state = resolvePetState(payload.action)
  if (!state) {
    // 未知 action 但有气泡时仍展示,避免定时任务等自定义事件消息丢失
    if (payload.bubble) showBubble(payload.bubble, 3200)
    else console.warn('[pet] unknown action:', payload.action)
    return
  }
  // 远程循环动作(waiting / running 系)要限时收尾:放完就回 idle,
  // 思考中则回到 review,保证状态机最终有主;一次性的表情动作播完自然回 idle。
  // idle 本身就是休息态,不加限时。
  const returnToIdle = !isLoopState(state)
  playState(state, returnToIdle)
  if (isLoopState(state) && state !== 'idle') {
    remoteLoopTimer = setTimeout(() => {
      remoteLoopTimer = null
      if (currentState !== state) return
      playState(agentThinking ? 'review' : 'idle', false)
    }, REMOTE_LOOP_MAX_MS)
  }
  if (payload.bubble) showBubble(payload.bubble, 3200)
}

type AgentStatus = 'thinking' | 'complete' | 'error' | 'idle'

function applyAgentStatus(payload: { status?: AgentStatus; bubble?: string }) {
  const status = payload.status
  if (!status) return

  if (status === 'thinking') {
    agentThinking = true
    // false:不要在 review 播完后回 idle,由后续状态事件结束本次循环。
    playState('review', false)
    if (payload.bubble) showBubble(payload.bubble, 2200)
    return
  }

  agentThinking = false
  if (status === 'complete') {
    playState('jumping', true)
    showBubble(payload.bubble || t('chat.complete'), 2600)
  } else if (status === 'error') {
    playState('failed', true)
    showBubble(payload.bubble || t('chat.errorOccurred'), 2800)
  } else {
    playState('idle', false)
    if (payload.bubble) showBubble(payload.bubble, 2200)
  }
}

let unlistenAgentStatus: UnlistenFn | null = null

function parseSseChunk(buffer: string): { events: Array<{ event: string; data: string }>; rest: string } {
  const events: Array<{ event: string; data: string }> = []
  const parts = buffer.split('\n\n')
  const rest = parts.pop() ?? ''
  for (const block of parts) {
    if (!block.trim()) continue
    let event = 'message'
    const dataLines: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      // 忽略 id: / :comment
    }
    if (dataLines.length) events.push({ event, data: dataLines.join('\n') })
  }
  return { events, rest }
}

async function connectPetEvents() {
  // 已有连接则先断
  stopPetEvents()
  petEventAbort = new AbortController()
  const signal = petEventAbort.signal

  const run = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/pet/events?replay=0`, {
        method: 'GET',
        headers: { Accept: 'text/event-stream' },
        signal,
      })
      if (!res.ok || !res.body) {
        throw new Error(`pet events HTTP ${res.status}`)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const { events, rest } = parseSseChunk(buf)
        buf = rest
        for (const ev of events) {
          let payload: any = null
          try {
            payload = JSON.parse(ev.data)
          } catch {
            continue
          }
          const type = payload?.type || ev.event
          if (type === 'pet_action') {
            applyRemotePetAction(payload)
          }
          // pet_hello / pet_heartbeat 忽略
        }
      }
      // 正常结束也重连
      if (!signal.aborted) schedulePetReconnect()
    } catch (e: any) {
      if (signal.aborted) return
      console.warn('[pet] events disconnected, retry...', e?.message || e)
      schedulePetReconnect()
    }
  }
  void run()
}

function schedulePetReconnect() {
  if (petEventReconnectTimer) clearTimeout(petEventReconnectTimer)
  petEventReconnectTimer = setTimeout(() => {
    petEventReconnectTimer = null
    void connectPetEvents()
  }, 2000)
}

function stopPetEvents() {
  if (petEventAbort) {
    petEventAbort.abort()
    petEventAbort = null
  }
  if (petEventReconnectTimer) {
    clearTimeout(petEventReconnectTimer)
    petEventReconnectTimer = null
  }
}

async function hangAround()
{

}


async function revealWindow(win: WebviewWindow): Promise<boolean> {
  try {
    // 强制还原(不依赖 isMinimized 查询结果,避免权限/状态误判)
    try { await win.unminimize() } catch (e) {
      console.warn('unminimize failed:', e)
    }
    try { await win.show() } catch (e) {
      console.warn('show failed:', e)
    }
    try { await win.setFocus() } catch (e) {
      console.warn('setFocus failed:', e)
    }
    // 任务栏闪烁提示(即使前台抢焦点被系统拦截也能看见)
    try {
      const { UserAttentionType } = await import('@tauri-apps/api/window')
      await win.requestUserAttention(UserAttentionType.Informational)
    } catch {}
    return true
  } catch (e) {
    console.warn('revealWindow failed, will recreate:', e)
    return false
  }
}

async function openOrCreateWindow(
  label: string,
  options: {
    url: string
    title: string
    width: number
    height: number
  },
) {
  try {
    const existing = await WebviewWindow.getByLabel(label)
    if (existing) {
      const ok = await revealWindow(existing)
      if (ok) return
      // 旧窗口已失效,尝试关闭后重建
      try { await existing.close() } catch {}
    }
    new WebviewWindow(label, {
      url: options.url,
      title: options.title,
      width: options.width,
      height: options.height,
      resizable: true,
      decorations: false,
      transparent: true,
      center: true,
    })
  } catch (e) {
    console.error(`Error opening window '${label}':`, e)
    // 最后兜底:直接新建
    try {
      new WebviewWindow(label, {
        url: options.url,
        title: options.title,
        width: options.width,
        height: options.height,
        resizable: true,
        decorations: false,
        transparent: true,
        center: true,
      })
    } catch (e2) {
      console.error(`Failed to create window '${label}':`, e2)
    }
  }
}

async function openChatWindow() {
  await openOrCreateWindow('chat', {
    url: '/chat_window',
    title: t('home.windowChat'),
    width: 900,
    height: 700,
  })
}

async function openSkinWindow() {
  await openOrCreateWindow('skin', {
    url: '/skin',
    title: t('home.windowSkin'),
    width: 400,
    height: 500,
  })
}

async function openSettingWindow() {
  await openOrCreateWindow('setting', {
    url: '/setting',
    title: t('home.windowSetting'),
    width: 600,
    height: 650,
  })
}

async function openJournalWindow() {
  await openOrCreateWindow('journal', {
    url: '/journal',
    title: t('home.windowJournal'),
    width: 420,
    height: 620,
  })
}

// ---- 全屏弹幕窗口(透明 + 鼠标点击穿透) ----
// 在最大的显示器上铺满,alwaysOnTop + skipTaskbar + focusable=false,
// 创建后再 setIgnoreCursorEvents(true),点击直接穿透到桌面/其他窗口。
async function ensureDanmakuWindow() {
  try {
    // 先检查后端配置:弹幕总开关关闭则不创建
    try {
      const res = await fetch('http://127.0.0.1:8000/danmaku/config')
      if (res.ok) {
        const data = await res.json()
        if (data.config?.enabled === false) return
      }
    } catch { /* 后端不可达时按开启处理 */ }
    const existing = await WebviewWindow.getByLabel('danmaku')
    if (existing) {
      return
    }
    const { availableMonitors } = await import('@tauri-apps/api/window')
    let mw = 0
    let mh = 0
    let mx = 0
    let my = 0
    try {
      const monitors = await availableMonitors()
      if (monitors.length) {
        // 选面积最大的显示器,物理像素 / scaleFactor 换成逻辑像素
        for (const m of monitors) {
          const w = m.size.width / (m.scaleFactor || 1)
          const h = m.size.height / (m.scaleFactor || 1)
          if (w * h > mw * mh) {
            mw = w
            mh = h
            mx = m.position.x / (m.scaleFactor || 1)
            my = m.position.y / (m.scaleFactor || 1)
          }
        }
      }
    } catch { /* fallthrough */ }
    if (!mw || !mh) {
      mw = window.screen.width
      mh = window.screen.height
    }
    const win = new WebviewWindow('danmaku', {
      url: '/danmaku',
      title: 'Danmaku',
      x: mx,
      y: my,
      width: mw,
      height: mh,
      transparent: true,
      decorations: false,
      alwaysOnTop: true,
      skipTaskbar: true,
      focusable: false,
      resizable: false,
      shadow: false,
    })
    // 创建后双保险:穿透 + 不可聚焦
    try {
      await win.setIgnoreCursorEvents(true)
      await win.setFocusable(false)
    } catch (e) {
      console.warn('[danmaku] setIgnoreCursorEvents failed:', e)
    }
  } catch (e) {
    console.warn('[danmaku] window create failed:', e)
  }
}

/** 根据配置关闭弹幕窗(仅总开关) */
async function closeDanmakuWindow() {
  try {
    const win = await WebviewWindow.getByLabel('danmaku')
    if (win) await win.close()
  } catch (e) {
    console.warn('[danmaku] window close failed:', e)
  }
}

let unlistenDanmakuCfg: UnlistenFn | null = null

// ---- 皮肤切换 ----
let unlistenPetSwitched: UnlistenFn | null = null
let onPetStorage: ((e: StorageEvent) => void) | null = null
let lastPetSwitchKey = ''

async function loadPetTexture(spritesheetPath: string) {
  if (!app || !sprite) return

  // 规范化路径(Assets.load 需要 / 开头或完整 URL)
  let path = spritesheetPath || ''
  if (path && !path.startsWith('http') && !path.startsWith('/')) {
    path = '/' + path
  }
  // 加 cache-bust,避免同路径换图后 Pixi 命中旧缓存
  const cacheBust = path.includes('?') ? `&_t=${Date.now()}` : `?_t=${Date.now()}`
  const loadPath = `${path}${cacheBust}`

  // 卸载旧纹理(失败忽略)
  try {
    if (baseSource) {
      // 尝试按当前 path 卸载;失败也不阻塞新加载
      await Assets.unload(path).catch(() => undefined)
    }
  } catch { /* ignore */ }

  // 加载新纹理
  const texture = await Assets.load<Texture>(loadPath)
  baseSource = texture.source as TextureSource
  applyPetScaleMode(currentPetStyle(path))

  // 重建 sprite textures 并回到 idle
  sprite.textures = getFrames(baseSource as TextureSource, ROWS.idle.row, ROWS.idle.frames)
  sprite.animationSpeed = animationSpeedFor('idle')
  sprite.loop = true
  sprite.gotoAndPlay(0)
  currentState = 'idle'
}

async function onPetSwitched(payload: {
  petId: string
  petFolder: string
  spritesheetPath: string
  displayName: string
  style?: 'pixel' | 'smooth'
}) {
  const key = `${payload.petId}|${payload.spritesheetPath}`
  // 去重:emit + emitTo + storage 可能连发
  if (key && key === lastPetSwitchKey) {
    // 允许短时间后再次切换同一皮肤(用户手动再点)
  }
  lastPetSwitchKey = key
  console.log('[pet] pet-switched received:', payload)
  try {
    await loadPetTexture(payload.spritesheetPath)
    applyPetScaleMode(payload.style)
    if (payload.petId) {
      try { localStorage.setItem('currentPetId', payload.petId) } catch { /* ignore */ }
    }
    showBubble(t('home.skinSwitched', { name: payload.displayName || payload.petId }), 2000)
  } catch (e: any) {
    console.error('[pet] failed to switch pet texture:', e)
    // 切换失败时回退到内置 frieren，避免桌宠卡住
    if (payload.spritesheetPath !== '/codex_pet/frieren/spritesheet.webp') {
      try {
        await loadPetTexture('/codex_pet/frieren/spritesheet.webp')
        try { localStorage.setItem('currentPetId', 'frieren') } catch { /* ignore */ }
      } catch { /* 彻底失败只能提示 */ }
    }
    showBubble(t('home.skinSwitchFailed'), 2500)
  }
}


// ---- 生命周期 ----
onMounted(async () => {
  if (!canvasRef.value) return
  app = new Application()
  await app.init({
    canvas: canvasRef.value,
    width: FRAME_W,
    height: FRAME_H * 1.1,
    backgroundAlpha: 0,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  })

  // 读取上次保存的皮肤，默认 frieren
  let spritesheetPath = '/codex_pet/frieren/spritesheet.webp'
  try {
    const savedPetId = localStorage.getItem('currentPetId')
    // 旧版默认内置 '02'/'01' 现已废弃，回退到 frieren
    if (savedPetId && savedPetId !== '02' && savedPetId !== '01') {
      const savedPetsStr = localStorage.getItem('customPets')
      if (savedPetsStr) {
        const savedPets = JSON.parse(savedPetsStr)
        const found = savedPets.find((p: any) => p.id === savedPetId)
        if (found && found.preview) {
          // 旧目录分家前路径 /pet/xxx → /codex_pet/xxx(customPets 存的都是导入的 codex 桌宠)
          spritesheetPath = found.preview.startsWith('/pet/')
            ? found.preview.replace(/^\/pet\//, '/codex_pet/')
            : found.preview
        }
      }
    }
  } catch { /* fallback to default */ }

  let texture: Texture
  try {
    texture = await Assets.load<Texture>(spritesheetPath)
    // 尺寸不符同样会「加载成功」,但切出来是错位马赛克 —— 当作失败回退,不把坏皮肤播出去
    if (!fitsSheetContract(texture.width, texture.height)) {
      throw new Error(
        `尺寸 ${texture.width}x${texture.height} 不符切片契约 ` +
          `${SHEET_FRAME_W * SHEET_COLS}x${SHEET_FRAME_H * SHEET_MIN_ROWS}`,
      )
    }
  } catch (e) {
    // 加载失败（旧导入皮肤损坏/格式不支持/尺寸不符），回退到内置 frieren
    console.warn(`[pet] 加载 ${spritesheetPath} 失败，回退到 frieren`, e)
    spritesheetPath = '/codex_pet/frieren/spritesheet.webp'
    try { localStorage.setItem('currentPetId', 'frieren') } catch { /* ignore */ }
    texture = await Assets.load<Texture>(spritesheetPath)
  }
  baseSource = texture.source as TextureSource
  applyPetScaleMode(currentPetStyle(spritesheetPath))
  const frames = getFrames(baseSource as TextureSource, ROWS.idle.row, ROWS.idle.frames)
  sprite = new AnimatedSprite(frames)
  sprite.animationSpeed = animationSpeedFor('idle')
  sprite.scale.set(1)
  sprite.loop = true
  sprite.play()

  app.stage.addChild(sprite)
  scheduleRandom()
  // 订阅后端 emit_pet_action → SSE,驱动远程动作
  void connectPetEvents()
  // 全屏弹幕窗口(透明 + 鼠标穿透),静默创建
  void ensureDanmakuWindow()

  // 监听弹幕开关变化:总开关关闭时关窗,开启时建窗
  try {
    unlistenDanmakuCfg = await listen<{ config?: { enabled?: boolean } }>(
      'danmaku-config-changed',
      (event) => {
        const enabled = event.payload?.config?.enabled
        if (enabled === false) {
          void closeDanmakuWindow()
        } else if (enabled === true) {
          void ensureDanmakuWindow()
        }
      },
    )
  } catch (e) {
    console.warn('[danmaku] config listen failed:', e)
  }

  // 聊天窗口通过 Tauri event 广播 Agent 生命周期,避免 thinking 动作只播放一遍。
  try {
    unlistenAgentStatus = await listen<{ status?: AgentStatus; bubble?: string }>(
      'agent-status',
      (event) => applyAgentStatus(event.payload),
    )
  } catch (e) {
    console.warn('[pet] failed to listen agent-status:', e)
  }

  // 订阅皮肤切换事件(Tauri 跨窗口)
  try {
    const { listen } = await import('@tauri-apps/api/event')
    unlistenPetSwitched = await listen<{
      petId: string
      petFolder: string
      spritesheetPath: string
      displayName: string
      style?: 'pixel' | 'smooth'
    }>('pet-switched', (event) => {
      void onPetSwitched(event.payload)
    })
  } catch (e) {
    console.warn('[pet] failed to listen pet-switched event:', e)
  }

  // 兜底:同源多 webview 的 localStorage 信号(skin 窗写入 petSwitchSignal)
  onPetStorage = (e: StorageEvent) => {
    if (e.key !== 'petSwitchSignal' || !e.newValue) return
    try {
      const payload = JSON.parse(e.newValue)
      if (payload?.spritesheetPath) {
        void onPetSwitched({
          petId: payload.petId || '',
          petFolder: payload.petFolder || '',
          spritesheetPath: payload.spritesheetPath,
          displayName: payload.displayName || payload.petId || '',
          style: payload.style,
        })
      }
    } catch (err) {
      console.warn('[pet] invalid petSwitchSignal:', err)
    }
  }
  window.addEventListener('storage', onPetStorage)
})

onUnmounted(() => {
  if (randomTimer) clearTimeout(randomTimer)
  stopPetEvents()
  if (bubbleClearTimer) {
    clearTimeout(bubbleClearTimer)
    bubbleClearTimer = null
  }
  endDragSession({ backToIdle: false, swallowClick: false })
  if (unlistenMoved) {
    unlistenMoved()
    unlistenMoved = null
  }
  if (unlistenPetSwitched) {
    unlistenPetSwitched()
    unlistenPetSwitched = null
  }
  if (unlistenDanmakuCfg) {
    unlistenDanmakuCfg()
    unlistenDanmakuCfg = null
  }
  if (unlistenAgentStatus) {
    unlistenAgentStatus()
    unlistenAgentStatus = null
  }
  if (onPetStorage) {
    window.removeEventListener('storage', onPetStorage)
    onPetStorage = null
  }
  app?.destroy(false)
})



</script>

<style scoped>
.pet-container {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.pet-root {
  width: 100vw;
  height: 100vh;
  background: transparent;
  position: relative;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.pet-canvas {
  image-rendering: pixelated;
  cursor: pointer;
  position: relative;
  z-index: 1;
}

/* 气泡 */
.speech-bubble {
  position: absolute;
  bottom: calc(FRAME_H * 1.2px + 16px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg-elevated);
  color: var(--text-primary);
  font-size: 13px;
  padding: 8px 14px;
  border-radius: var(--radius-lg, 12px);
  max-width: 240px;
  z-index: 10;
  border: 1px solid var(--accent-border);
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.18));
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: calc();
  overflow: hidden;
  line-height: 1.45;
}
.speech-bubble::after {
  content: '';
  position: absolute;
  bottom: -6px;
  left: 50%;
  transform: translateX(-50%);
  width: 10px;
  height: 6px;
  background: var(--bg-elevated);
  clip-path: polygon(0 0, 100% 0, 50% 100%);
}

/* 右侧按钮列 */
.btn-col {
  display: flex;
  flex-direction: column;
  gap: 8px;
  position: relative;
  z-index: 10;
}

.icon-btn {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: var(--activity-bar-bg);
  color: var(--accent-300, #F7A85B);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--duration-fast, 120ms) var(--ease-standard, ease);
  pointer-events: auto;
  position: relative;
  z-index: 10;
}
.icon-btn:hover {
  background: var(--bg-elevated);
  color: var(--accent-500, #EF6B6E);
  border-color: var(--accent-border);
}
.icon-btn.danger:hover {
  background: rgba(211, 85, 90, 0.15);
  color: var(--error, #D3555A);
  border-color: rgba(211, 85, 90, 0.4);
}

/* 模式按钮 - 统一风格,颜色继承 icon-btn 默认 accent 色 */
.mode-btn {
  transition: all var(--duration-fast, 120ms) var(--ease-standard, ease);
}
.mode-btn:hover {
  background: var(--bg-elevated);
}

/* 气泡过渡动画 */
.bubble-enter-active, .bubble-leave-active { transition: all 0.25s ease; }
.bubble-enter-from, .bubble-leave-to { opacity: 0; transform: translateX(-50%) translateY(6px); }
</style>
