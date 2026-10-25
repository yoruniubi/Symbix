/**
 * 陪伴功能设置(弹幕)。
 * 配置持久化在后端 danmaku_config.json(与 voice/mcp 等独立配置文件同模式),
 * 前端只负责读写 API,并用 Tauri 事件通知 Home 窗口同步弹幕窗。
 */
import { ref, readonly } from 'vue'

export interface CompanionSettings {
  /** 弹幕总开关 */
  enabled: boolean
  /** 空闲漫游弹幕 */
  idle_enabled: boolean
  /** 时段问候弹幕 */
  greeting_enabled: boolean
  /** 空闲弹幕最小间隔(秒) */
  idle_interval_s: number
}

const BACKEND_URL = 'http://127.0.0.1:8000'

/** 带超时的 fetch:避免请求挂起导致 companionLoading 永远 true(富按钮全禁用) */
async function fetchWithTimeout(url: string, init: RequestInit = {}, ms = 5000): Promise<Response> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), ms)
  try {
    return await fetch(url, { ...init, signal: ctrl.signal })
  } finally {
    clearTimeout(timer)
  }
}

const defaultSettings: CompanionSettings = {
  enabled: true,
  idle_enabled: true,
  greeting_enabled: true,
  idle_interval_s: 600,
}

const settings = ref<CompanionSettings>({ ...defaultSettings })

async function loadCompanionSettings() {
  try {
    const res = await fetchWithTimeout(`${BACKEND_URL}/danmaku/config`)
    if (res.ok) {
      const data = await res.json()
      settings.value = { ...defaultSettings, ...(data.config || {}) }
    }
  } catch {
    // 后端不可达时保持默认
  }
}

async function saveCompanionSettings(partial: Partial<CompanionSettings>) {
  const next = { ...settings.value, ...partial }
  settings.value = next
  try {
    await fetchWithTimeout(`${BACKEND_URL}/danmaku/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(partial),
    })
  } catch {
    // 忽略网络错误
  }
  // 通知 Home 窗口:弹幕开关变化 → 启停全屏弹幕窗
  try {
    const { emit } = await import('@tauri-apps/api/event')
    await emit('danmaku-config-changed', { config: next })
  } catch {
    // 非 Tauri 环境忽略
  }
}

async function resetCompanionSettings() {
  settings.value = { ...defaultSettings }
  try {
    await fetchWithTimeout(`${BACKEND_URL}/danmaku/config/reset`, { method: 'POST' })
  } catch {
    // 忽略网络错误
  }
}

/** 触发一条测试弹幕(设置页「测试一下」用,后端会无视总开关直接推一条) */
async function testDanmaku(): Promise<boolean> {
  try {
    const res = await fetchWithTimeout(`${BACKEND_URL}/danmaku/test`, { method: 'POST' })
    return res.ok
  } catch {
    return false
  }
}

/** 触发一条测试主动搭话(可点击气泡;无视频控,两种形态随机) */
async function testProactive(): Promise<boolean> {
  try {
    const res = await fetchWithTimeout(`${BACKEND_URL}/companion/proactive/test`, { method: 'POST' })
    return res.ok
  } catch {
    return false
  }
}

export function useCompanion() {
  return {
    companionSettings: readonly(settings),
    loadCompanionSettings,
    saveCompanionSettings,
    resetCompanionSettings,
    testDanmaku,
    testProactive,
    defaultSettings,
  }
}