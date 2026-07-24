import { ref, readonly } from 'vue'
import {
  isPermissionGranted,
  requestPermission,
  sendNotification,
} from '@tauri-apps/plugin-notification'

/**
 * 情绪陪伴向 · 柔和完成音效预设
 * random：每次从柔和池中随机挑一种（避免连续重复）
 */
export type NotifySoundId =
  | 'random'
  | 'breeze'   // 轻风 · 慢琶音
  | 'dew'      // 晨露 · 透明双音
  | 'lullaby'  // 摇篮 · 慢三音
  | 'petal'    // 花瓣 · 极轻泛音
  | 'warmth'   // 暖意 · 低沉三角波
  | 'ripple'   // 涟漪 · 轻微上扬
  | 'mist'     // 薄雾 · 下行柔雾
  | 'ember'    // 余烬 · 低暖双音
  | 'cloud'    // 云朵 · 漂浮叠音
  | 'hush'     // 轻语 · 极弱低语
  | 'dawn'     // 破晓 · 缓缓升起
  | 'silk'     // 丝绸 · 顺滑滑音感
  | 'moon'     // 月色 · 静谧和声
  | 'rain'     // 细雨 · 轻点双滴
  | 'none'
  | 'chime'
  | 'ding'
  | 'soft'
  | 'pop'

export interface NotifySettings {
  /** 任务完成后是否提醒 */
  enabled: boolean
  /** 是否播放音效 */
  soundEnabled: boolean
  /** 音效预设 */
  soundId: NotifySoundId
  /** 音量 0–1（默认偏低，陪伴感） */
  volume: number
  /** 是否发送系统桌面通知 */
  desktopNotify: boolean
  /**
   * 仅在窗口不在前台时弹系统通知。
   * false = 完成时始终弹（便于调试 / 更明显）
   */
  onlyWhenBackground: boolean
}

const STORAGE_KEY = 'symbix_notify_settings'

/** 柔和随机池（不含 none / random / 旧硬音） */
const SOFT_POOL: NotifySoundId[] = [
  'breeze',
  'dew',
  'lullaby',
  'petal',
  'warmth',
  'ripple',
  'mist',
  'ember',
  'cloud',
  'hush',
  'dawn',
  'silk',
  'moon',
  'rain',
]

/** 陪伴向默认文案池（系统通知 body 为空时随机） */
const COMPANION_BODIES = [
  '我在这里，任务已经完成啦～',
  '好啦，这一段已经帮你做好了。',
  '完成了，慢慢看就好。',
  '搞定了，有需要再叫我。',
  '这件事已经收尾了，我陪着你。',
  '处理好了，休息一下也可以。',
]

const defaultSettings: NotifySettings = {
  enabled: true,
  soundEnabled: true,
  soundId: 'random',
  volume: 0.38,
  desktopNotify: true,
  onlyWhenBackground: false,
}

const settings = ref<NotifySettings>({ ...defaultSettings })
let audioCtx: AudioContext | null = null
let lastRandomId: NotifySoundId | null = null

function loadNotifySettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      settings.value = { ...defaultSettings, ...parsed }
      settings.value.volume = Math.min(
        1,
        Math.max(0, Number(settings.value.volume) || 0.38),
      )
      if (typeof settings.value.onlyWhenBackground !== 'boolean') {
        settings.value.onlyWhenBackground = false
      }
      // 旧默认音量偏高时略压一点（仅当接近旧默认 0.55）
      if (settings.value.volume > 0.52 && settings.value.volume <= 0.56) {
        settings.value.volume = 0.38
      }
    }
  } catch {
    settings.value = { ...defaultSettings }
  }
}

function saveNotifySettings(partial: Partial<NotifySettings>) {
  settings.value = { ...settings.value, ...partial }
  settings.value.volume = Math.min(
    1,
    Math.max(0, Number(settings.value.volume) || 0),
  )
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings.value))
}

function resetNotifySettings() {
  settings.value = { ...defaultSettings }
  localStorage.removeItem(STORAGE_KEY)
}

function getCtx(): AudioContext | null {
  try {
    const AC = window.AudioContext || (window as any).webkitAudioContext
    if (!AC) return null
    if (!audioCtx) audioCtx = new AC()
    if (audioCtx.state === 'suspended') {
      void audioCtx.resume()
    }
    return audioCtx
  } catch {
    return null
  }
}

interface SoftToneOpts {
  type?: OscillatorType
  detune?: number
  /** 低通截止，越低越柔和（默认 2800） */
  filterFreq?: number
  /** 额外整体衰减系数 */
  soft?: number
}

/**
 * 柔和单音：慢起慢落 + 低通滤波，避免刺耳。
 * 面向情绪陪伴场景，宁可听不清也不要尖锐。
 */
function playSoftTone(
  ctx: AudioContext,
  freq: number,
  start: number,
  duration: number,
  volume: number,
  opts: SoftToneOpts = {},
) {
  const {
    type = 'sine',
    detune = 0,
    filterFreq = 2800,
    soft = 1,
  } = opts

  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  const filter = ctx.createBiquadFilter()

  osc.type = type
  osc.frequency.setValueAtTime(freq, start)
  if (detune) osc.detune.setValueAtTime(detune, start)

  filter.type = 'lowpass'
  filter.frequency.setValueAtTime(filterFreq, start)
  filter.Q.setValueAtTime(0.5, start)

  // 更长 attack / release，陪伴感
  const peak = Math.max(0.0001, volume * soft)
  const attack = Math.min(0.12, duration * 0.32)
  const release = Math.max(0.18, duration * 0.6)
  const end = start + duration + release * 0.2

  gain.gain.setValueAtTime(0.0001, start)
  gain.gain.exponentialRampToValueAtTime(peak, start + attack)
  gain.gain.exponentialRampToValueAtTime(0.0001, end)

  osc.connect(filter)
  filter.connect(gain)
  gain.connect(ctx.destination)
  osc.start(start)
  osc.stop(end + 0.08)
}

function pickRandomSoft(): NotifySoundId {
  let pool = SOFT_POOL
  if (lastRandomId && SOFT_POOL.length > 1) {
    pool = SOFT_POOL.filter((id) => id !== lastRandomId)
  }
  const id = pool[Math.floor(Math.random() * pool.length)]
  lastRandomId = id
  return id
}

function resolveSoundId(soundId?: NotifySoundId): NotifySoundId {
  const id = soundId ?? settings.value.soundId
  if (id === 'random') return pickRandomSoft()
  // 旧硬音映射到柔和等价
  if (id === 'chime') return 'breeze'
  if (id === 'ding') return 'dew'
  if (id === 'soft') return 'warmth'
  if (id === 'pop') return 'petal'
  return id
}

/**
 * 用 Web Audio 合成情绪陪伴向柔和完成音。
 * 无需外置音频文件。
 */
export function playNotifySound(soundId?: NotifySoundId, volume?: number) {
  const resolved = resolveSoundId(soundId)
  if (resolved === 'none') return

  const vol = Math.min(1, Math.max(0, volume ?? settings.value.volume))
  if (vol <= 0) return

  const ctx = getCtx()
  if (!ctx) return

  const t0 = ctx.currentTime
  // 整体再压峰值，陪伴感优先
  const v = vol * 0.48

  switch (resolved) {
    case 'breeze':
      // 轻风：C5 → E5 → G5 慢琶音
      playSoftTone(ctx, 523.25, t0, 0.6, v * 0.4, { filterFreq: 2600 })
      playSoftTone(ctx, 659.25, t0 + 0.16, 0.65, v * 0.34, { filterFreq: 2600 })
      playSoftTone(ctx, 783.99, t0 + 0.32, 0.9, v * 0.28, { filterFreq: 2400 })
      break
    case 'dew':
      // 晨露：A5 + 轻微泛音
      playSoftTone(ctx, 880, t0, 0.55, v * 0.34, { filterFreq: 3200 })
      playSoftTone(ctx, 1320, t0 + 0.08, 0.45, v * 0.14, { filterFreq: 3000 })
      break
    case 'lullaby':
      // 摇篮：G4 → B4 → D5，triangle 更暖
      playSoftTone(ctx, 392.0, t0, 0.75, v * 0.36, {
        type: 'triangle',
        filterFreq: 1800,
      })
      playSoftTone(ctx, 493.88, t0 + 0.24, 0.8, v * 0.3, {
        type: 'triangle',
        filterFreq: 1800,
      })
      playSoftTone(ctx, 587.33, t0 + 0.48, 1.0, v * 0.26, {
        type: 'triangle',
        filterFreq: 1600,
      })
      break
    case 'petal':
      // 花瓣：极轻双音 + detune
      playSoftTone(ctx, 698.46, t0, 0.7, v * 0.28, { filterFreq: 2400 })
      playSoftTone(ctx, 880.0, t0 + 0.12, 0.75, v * 0.18, {
        detune: 5,
        filterFreq: 2400,
      })
      break
    case 'warmth':
      // 暖意：低八度三角波
      playSoftTone(ctx, 261.63, t0, 0.95, v * 0.38, {
        type: 'triangle',
        filterFreq: 1400,
      })
      playSoftTone(ctx, 329.63, t0 + 0.2, 0.9, v * 0.26, {
        type: 'triangle',
        filterFreq: 1400,
      })
      break
    case 'ripple':
      // 涟漪：轻微上扬三音
      playSoftTone(ctx, 659.25, t0, 0.48, v * 0.3, { filterFreq: 2600 })
      playSoftTone(ctx, 739.99, t0 + 0.14, 0.52, v * 0.26, { filterFreq: 2600 })
      playSoftTone(ctx, 830.61, t0 + 0.3, 0.7, v * 0.2, { filterFreq: 2400 })
      break
    case 'mist':
      // 薄雾：下行柔雾 E5 → C5 → A4
      playSoftTone(ctx, 659.25, t0, 0.7, v * 0.28, { filterFreq: 2000 })
      playSoftTone(ctx, 523.25, t0 + 0.18, 0.8, v * 0.24, { filterFreq: 1800 })
      playSoftTone(ctx, 440.0, t0 + 0.38, 1.0, v * 0.2, {
        type: 'triangle',
        filterFreq: 1500,
      })
      break
    case 'ember':
      // 余烬：低暖双音
      playSoftTone(ctx, 196.0, t0, 1.1, v * 0.36, {
        type: 'triangle',
        filterFreq: 1000,
      })
      playSoftTone(ctx, 246.94, t0 + 0.22, 1.0, v * 0.24, {
        type: 'triangle',
        filterFreq: 1100,
      })
      break
    case 'cloud':
      // 云朵：漂浮叠音（轻微失谐）
      playSoftTone(ctx, 523.25, t0, 0.9, v * 0.26, { filterFreq: 2200 })
      playSoftTone(ctx, 659.25, t0 + 0.05, 0.95, v * 0.2, {
        detune: -4,
        filterFreq: 2200,
      })
      playSoftTone(ctx, 783.99, t0 + 0.28, 1.05, v * 0.16, {
        detune: 3,
        filterFreq: 2000,
      })
      break
    case 'hush':
      // 轻语：极弱低语，几乎像呼吸
      playSoftTone(ctx, 293.66, t0, 0.85, v * 0.22, {
        type: 'triangle',
        filterFreq: 900,
        soft: 0.85,
      })
      playSoftTone(ctx, 349.23, t0 + 0.28, 0.95, v * 0.16, {
        type: 'triangle',
        filterFreq: 900,
        soft: 0.85,
      })
      break
    case 'dawn':
      // 破晓：缓缓升起
      playSoftTone(ctx, 349.23, t0, 0.65, v * 0.26, { filterFreq: 2000 })
      playSoftTone(ctx, 440.0, t0 + 0.2, 0.7, v * 0.28, { filterFreq: 2200 })
      playSoftTone(ctx, 523.25, t0 + 0.42, 0.85, v * 0.3, { filterFreq: 2400 })
      playSoftTone(ctx, 659.25, t0 + 0.62, 1.0, v * 0.22, { filterFreq: 2400 })
      break
    case 'silk':
      // 丝绸：顺滑滑音感（两级靠近）
      playSoftTone(ctx, 587.33, t0, 0.75, v * 0.28, {
        detune: -3,
        filterFreq: 2300,
      })
      playSoftTone(ctx, 698.46, t0 + 0.15, 0.85, v * 0.24, {
        detune: 2,
        filterFreq: 2300,
      })
      playSoftTone(ctx, 783.99, t0 + 0.34, 0.95, v * 0.18, { filterFreq: 2100 })
      break
    case 'moon':
      // 月色：静谧五度
      playSoftTone(ctx, 261.63, t0, 1.15, v * 0.3, {
        type: 'triangle',
        filterFreq: 1200,
      })
      playSoftTone(ctx, 392.0, t0 + 0.08, 1.2, v * 0.22, {
        type: 'triangle',
        filterFreq: 1300,
        detune: 2,
      })
      break
    case 'rain':
      // 细雨：轻点双滴
      playSoftTone(ctx, 987.77, t0, 0.35, v * 0.22, { filterFreq: 3400 })
      playSoftTone(ctx, 1174.66, t0 + 0.14, 0.32, v * 0.16, { filterFreq: 3200 })
      playSoftTone(ctx, 880.0, t0 + 0.36, 0.4, v * 0.14, { filterFreq: 2800 })
      break
    default:
      playSoftTone(ctx, 523.25, t0, 0.55, v * 0.3, { filterFreq: 2200 })
  }
}

async function ensureDesktopPermission(): Promise<boolean> {
  if (typeof Notification === 'undefined') return false
  if (Notification.permission === 'granted') return true
  if (Notification.permission === 'denied') return false
  try {
    const result = await Notification.requestPermission()
    return result === 'granted'
  } catch {
    return false
  }
}

function isWindowInBackground(): boolean {
  if (typeof document === 'undefined') return true
  return document.hidden || !document.hasFocus()
}

function pickCompanionBody(fallback?: string): string {
  if (fallback && fallback.trim()) return fallback
  return COMPANION_BODIES[Math.floor(Math.random() * COMPANION_BODIES.length)]
}

/**
 * 发送系统通知：优先 Tauri 原生插件，失败再回退 Web Notification。
 * silent=true，避免系统默认提示音盖过我们的柔和音效。
 */
async function sendDesktopNotification(title: string, body: string) {
  // 1) Tauri 原生
  try {
    let granted = await isPermissionGranted()
    if (!granted) {
      const permission = await requestPermission()
      granted = permission === 'granted'
    }
    if (granted) {
      sendNotification({
        title,
        body,
        // 关闭系统自带提示音，由 Web Audio 柔和音接管
        silent: true,
      } as any)
      return true
    }
  } catch {
    // 非 Tauri 环境或插件未就绪
  }

  // 2) Web Notification 回退
  return fallbackWebNotify(title, body)
}

async function fallbackWebNotify(title: string, body: string): Promise<boolean> {
  const ok = await ensureDesktopPermission()
  if (!ok) return false
  try {
    new Notification(title, { body, silent: true })
    return true
  } catch {
    return false
  }
}

/**
 * 主动请求系统通知权限（设置页「测试通知」/ 保存时调用）。
 */
export async function requestDesktopNotifyPermission(): Promise<
  'granted' | 'denied' | 'default' | 'unavailable'
> {
  try {
    let granted = await isPermissionGranted()
    if (granted) return 'granted'
    const permission = await requestPermission()
    return permission === 'granted'
      ? 'granted'
      : permission === 'denied'
        ? 'denied'
        : 'default'
  } catch {
    // 回退 Web
    if (typeof Notification === 'undefined') return 'unavailable'
    if (Notification.permission === 'granted') return 'granted'
    if (Notification.permission === 'denied') return 'denied'
    try {
      const r = await Notification.requestPermission()
      return r
    } catch {
      return 'unavailable'
    }
  }
}

/**
 * 任务完成提醒：柔和音效 + 系统桌面通知。
 * preview=true 时仅试听音效。
 */
export async function notifyTaskComplete(options?: {
  title?: string
  body?: string
  /** 仅试听音效 */
  preview?: boolean
  /** 强制弹系统通知（忽略 onlyWhenBackground） */
  forceDesktop?: boolean
}) {
  loadNotifySettings()

  const cfg = settings.value
  if (!options?.preview && !cfg.enabled) return

  if (cfg.soundEnabled || options?.preview) {
    playNotifySound(cfg.soundId, cfg.volume)
  }

  if (options?.preview) return

  if (!cfg.desktopNotify) return

  const title = options?.title || 'Symbix'
  const body = pickCompanionBody(options?.body)

  const shouldNotify =
    options?.forceDesktop ||
    !cfg.onlyWhenBackground ||
    isWindowInBackground()

  if (shouldNotify) {
    await sendDesktopNotification(title, body)
  }
}

// 启动时加载一次
loadNotifySettings()

export function useNotify() {
  return {
    notifySettings: readonly(settings),
    loadNotifySettings,
    saveNotifySettings,
    resetNotifySettings,
    playNotifySound,
    notifyTaskComplete,
    requestDesktopNotifyPermission,
    defaultSettings,
    SOFT_POOL,
  }
}
