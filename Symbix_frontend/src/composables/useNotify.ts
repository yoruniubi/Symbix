import { ref, readonly } from 'vue'
import {
  isPermissionGranted,
  requestPermission,
  sendNotification,
} from '@tauri-apps/plugin-notification'

export type NotifySoundId = 'chime' | 'ding' | 'soft' | 'pop' | 'none'

export interface NotifySettings {
  /** 任务完成后是否提醒 */
  enabled: boolean
  /** 是否播放音效 */
  soundEnabled: boolean
  /** 音效预设 */
  soundId: NotifySoundId
  /** 音量 0–1 */
  volume: number
  /** 是否尝试系统桌面通知 */
  desktopNotify: boolean
}

const STORAGE_KEY = 'symbix_notify_settings'

const defaultSettings: NotifySettings = {
  enabled: true,
  soundEnabled: true,
  soundId: 'chime',
  volume: 0.55,
  desktopNotify: true,
}

const settings = ref<NotifySettings>({ ...defaultSettings })
let audioCtx: AudioContext | null = null

function loadNotifySettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      settings.value = { ...defaultSettings, ...parsed }
      // clamp
      settings.value.volume = Math.min(1, Math.max(0, Number(settings.value.volume) || 0.55))
    }
  } catch {
    settings.value = { ...defaultSettings }
  }
}

function saveNotifySettings(partial: Partial<NotifySettings>) {
  settings.value = { ...settings.value, ...partial }
  settings.value.volume = Math.min(1, Math.max(0, Number(settings.value.volume) || 0))
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

/** 播放单音（正弦衰减） */
function playTone(
  ctx: AudioContext,
  freq: number,
  start: number,
  duration: number,
  volume: number,
  type: OscillatorType = 'sine',
) {
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(freq, start)
  gain.gain.setValueAtTime(0.0001, start)
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, volume), start + 0.02)
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration)
  osc.connect(gain)
  gain.connect(ctx.destination)
  osc.start(start)
  osc.stop(start + duration + 0.02)
}

/**
 * 用 Web Audio 合成几种轻量完成音效，无需外置音频文件。
 */
export function playNotifySound(soundId?: NotifySoundId, volume?: number) {
  const id = soundId ?? settings.value.soundId
  if (id === 'none') return

  const vol = Math.min(1, Math.max(0, volume ?? settings.value.volume))
  if (vol <= 0) return

  const ctx = getCtx()
  if (!ctx) return

  const t0 = ctx.currentTime

  switch (id) {
    case 'chime':
      // 上行三和弦琶音
      playTone(ctx, 523.25, t0, 0.35, vol * 0.55) // C5
      playTone(ctx, 659.25, t0 + 0.09, 0.35, vol * 0.5) // E5
      playTone(ctx, 783.99, t0 + 0.18, 0.55, vol * 0.45) // G5
      break
    case 'ding':
      // 清脆叮
      playTone(ctx, 880, t0, 0.45, vol * 0.5)
      playTone(ctx, 1318.5, t0 + 0.04, 0.3, vol * 0.28)
      break
    case 'soft':
      // 柔和双音
      playTone(ctx, 392, t0, 0.55, vol * 0.4, 'triangle')
      playTone(ctx, 493.88, t0 + 0.12, 0.5, vol * 0.35, 'triangle')
      break
    case 'pop':
      // 短促提示
      playTone(ctx, 640, t0, 0.12, vol * 0.55, 'square')
      playTone(ctx, 960, t0 + 0.08, 0.16, vol * 0.35, 'square')
      break
    default:
      playTone(ctx, 660, t0, 0.3, vol * 0.45)
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

/**
 * 任务完成提醒：音效 + 可选桌面通知。
 * silent=true 时仅用于设置页试听（不弹桌面通知）。
 */
export async function notifyTaskComplete(options?: {
  title?: string
  body?: string
  /** 仅试听音效 */
  preview?: boolean
}) {
  // 确保已加载本地配置
  if (!localStorage.getItem(STORAGE_KEY) && settings.value === defaultSettings) {
    loadNotifySettings()
  }

  const cfg = settings.value
  if (!options?.preview && !cfg.enabled) return

  if (cfg.soundEnabled || options?.preview) {
    playNotifySound(cfg.soundId, cfg.volume)
  }

  if (options?.preview) return

  if (cfg.desktopNotify && typeof document !== 'undefined') {
    const title = options?.title || 'Symbix'
    const body = options?.body || '任务已完成'

    // 仅在页面不可见时弹系统通知，避免打扰
    if (document.hidden || !document.hasFocus()) {
      // Tauri 环境：使用原生通知插件
      if (typeof window !== 'undefined' && (window as any).__TAURI__) {
        try {
          let granted = await isPermissionGranted()
          if (!granted) {
            const permission = await requestPermission()
            granted = permission === 'granted'
          }
          if (granted) {
            sendNotification({ title, body })
          }
        } catch {
          // 回退到 Web Notification
          await fallbackWebNotify(title, body)
        }
      } else {
        // 浏览器环境：使用 Web Notification
        await fallbackWebNotify(title, body)
      }
    }
  }
}

async function fallbackWebNotify(title: string, body: string) {
  const ok = await ensureDesktopPermission()
  if (ok) {
    try {
      new Notification(title, { body, silent: true })
    } catch {
      /* ignore */
    }
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
    defaultSettings,
  }
}
