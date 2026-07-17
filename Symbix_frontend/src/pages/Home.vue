<template>
  <div class="pet-root">
    <div class="pet-container">
      <canvas
        ref="canvasRef"
        class="pet-canvas"
        @click="handlePetClick"
        @mousedown="onCanvasMousedown"
      />
      <div class="btn-col">
        <n-tooltip placement="right" trigger="hover">
            <template #trigger>
              <button class="icon-btn" @click="openChatWindow" aria-label="对话">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
              </button>
            </template>
            对话
          </n-tooltip>

        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <button class="icon-btn" @click="openSkinWindow" aria-label="换肤">
              <svg width="18" height="18" viewBox="0 0 1024 1024" fill="currentColor">
                <path d="M752.8 143.2c3.2 0 6.3 1.3 8.5 3.5L955.6 341c5.5 5.5 5.5 14.3 0 19.8L864 452.5l-96-96V895H448v1H256V357.5l-96 96-91.6-91.6c-5.5-5.5-5.5-14.3 0-19.8L263 147.5c2.3-2.3 5.3-3.5 8.5-3.5H351c33.4 26.9 92.6 64 164.6 64 72.1 0 131.4-37.2 164.8-64.2l72.3-0.6h0.1z m0-64h-0.6l-83.8 0.7c-7.6 0.1-15 2.8-20.7 7.8-19.6 17-71.3 56.3-132.1 56.3-60.6 0-112.3-39.1-132-56.2-5.8-5.1-13.3-7.8-21-7.8h-91c-20.2 0-39.5 8-53.7 22.3L23.1 296.8c-30.5 30.5-30.5 79.8 0 110.3L128 512c8.8 8.8 20.4 13.3 32 13.3s23.2-4.4 32-13.3v416c0 17.7 14.3 32 32 32h288v-1h288c17.7 0 32-14.3 32-32V511c8.8 8.8 20.4 13.3 32 13.3s23.2-4.4 32-13.3l104.8-104.8c30.5-30.5 30.5-79.8 0-110.3L806.5 101.5c-14.2-14.2-33.6-22.3-53.7-22.3z"/>
              </svg>
            </button>
          </template>
          换肤
        </n-tooltip>

        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <button class="icon-btn" @click="openSettingWindow" aria-label="设置">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
            </button>
          </template>
          设置
        </n-tooltip>

        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <button class="icon-btn danger" @click="appWindow.hide()" aria-label="隐藏">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </button>
          </template>
          隐藏
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
import { Application, Texture, AnimatedSprite, Rectangle, TextureSource, Assets } from 'pixi.js'

const router = useRouter()
const appWindow = getCurrentWindow()

// ---- 状态 ----
const bubbleText = ref('')

const hello_list = ['今天想做些什么？', '欢迎回来！', '需要帮忙吗？', '有什么想聊的？']
const greeting = hello_list[Math.floor(Math.random() * hello_list.length)]

// ---- PixiJS ----
const canvasRef = ref<HTMLCanvasElement>()
const FRAME_W = 192
const FRAME_H = 208
const FPS = 8
const ROWS = {
  idle:     { row: 0, frames: 6 },
  waving:   { row: 3, frames: 4 },
  jumping:  { row: 4, frames: 5 },
  failed:   { row: 5, frames: 8 },
}

let app: Application | null = null
let sprite: AnimatedSprite | null = null
let baseSource: TextureSource | null = null
let currentState = 'idle'
let randomTimer: ReturnType<typeof setTimeout> | null = null

function onCanvasMousedown(e: MouseEvent) {
  if (e.button !== 0) return
  appWindow.startDragging()
}

function getFrames(source: TextureSource, row: number, frameCount: number) {
  return Array.from({ length: frameCount }, (_, i) =>
    new Texture({
      source: source as TextureSource,
      frame: new Rectangle(i * FRAME_W, row * FRAME_H, FRAME_W, FRAME_H),
    })
  )
}

function playState(state: keyof typeof ROWS, returnToIdle = true) {
  if (!sprite || !baseSource) return
  currentState = state
  const def = ROWS[state]
  sprite.textures = getFrames(baseSource as TextureSource, def.row, def.frames)
  sprite.loop = state === 'idle'
  sprite.gotoAndPlay(0)
  if (returnToIdle && !sprite.loop) {
    sprite.onComplete = () => playState('idle', false)
  } else {
    sprite.onComplete = undefined
  }
}

function scheduleRandom() {
  randomTimer = setTimeout(() => {
    if (currentState === 'idle') {
      const actions = ['waving', 'jumping'] as const
      playState(actions[Math.floor(Math.random() * actions.length)])
    }
    scheduleRandom()
  }, 5000 + Math.random() * 10000)
}

function handlePetClick() {
  playState('jumping')
  showBubble(greeting)
}

function showBubble(text: string, duration = 3000) {
  bubbleText.value = text
  setTimeout(() => { bubbleText.value = '' }, duration)
}

// ---- 打开窗口 ----
/**
 * 显示已有窗口；若窗口已最小化/隐藏则还原并聚焦。
 * 失败（例如窗口已销毁但仍有 label 缓存）则返回 false，调用方重建。
 *
 * Windows 上最小化后仅 setFocus 不够，必须 unminimize + show。
 * 状态查询 API 若因权限失败，仍强制执行恢复动作。
 */
async function revealWindow(win: WebviewWindow): Promise<boolean> {
  try {
    // 强制还原（不依赖 isMinimized 查询结果，避免权限/状态误判）
    try { await win.unminimize() } catch (e) {
      console.warn('unminimize failed:', e)
    }
    try { await win.show() } catch (e) {
      console.warn('show failed:', e)
    }
    try { await win.setFocus() } catch (e) {
      console.warn('setFocus failed:', e)
    }
    // 任务栏闪烁提示（即使前台抢焦点被系统拦截也能看见）
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
      // 旧窗口已失效，尝试关闭后重建
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
    })
  } catch (e) {
    console.error(`Error opening window '${label}':`, e)
    // 最后兜底：直接新建
    try {
      new WebviewWindow(label, {
        url: options.url,
        title: options.title,
        width: options.width,
        height: options.height,
        resizable: true,
        decorations: false,
        transparent: true,
      })
    } catch (e2) {
      console.error(`Failed to create window '${label}':`, e2)
    }
  }
}

async function openChatWindow() {
  await openOrCreateWindow('chat', {
    url: '/chat_window',
    title: 'Symbix - 对话',
    width: 900,
    height: 700,
  })
}

async function openSkinWindow() {
  await openOrCreateWindow('skin', {
    url: '/skin',
    title: 'Symbix - 换肤',
    width: 400,
    height: 500,
  })
}

async function openSettingWindow() {
  await openOrCreateWindow('setting', {
    url: '/setting',
    title: 'Symbix - 设置',
    width: 600,
    height: 650,
  })
}

// ---- 生命周期 ----
onMounted(async () => {
  if (!canvasRef.value) return
  app = new Application()
  await app.init({
    canvas: canvasRef.value,
    width: FRAME_W ,
    height: FRAME_H *1.1,
    backgroundAlpha: 0,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  })
  const texture = await Assets.load<Texture>('/pet/02/spritesheet.webp')
  baseSource = texture.source as TextureSource
  const frames = getFrames(baseSource as TextureSource, ROWS.idle.row, ROWS.idle.frames)
  sprite = new AnimatedSprite(frames)
  sprite.animationSpeed = FPS / 60
  sprite.scale.set(1)
  sprite.loop = true
  sprite.play()
  app.stage.addChild(sprite)
  scheduleRandom()
})

onUnmounted(() => {
  if (randomTimer) clearTimeout(randomTimer)
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
  white-space: nowrap;
  max-width: 240px;
  white-space: normal;
  z-index: 10;
  border: 1px solid var(--accent-border);
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.18));
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
  color: var(--text-secondary);
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
  color: var(--text-primary);
  border-color: var(--accent-border);
}
.icon-btn.danger:hover {
  background: rgba(211, 85, 90, 0.15);
  color: var(--error, #D3555A);
  border-color: rgba(211, 85, 90, 0.4);
}

/* 气泡过渡动画 */
.bubble-enter-active, .bubble-leave-active { transition: all 0.25s ease; }
.bubble-enter-from, .bubble-leave-to { opacity: 0; transform: translateX(-50%) translateY(6px); }
</style>