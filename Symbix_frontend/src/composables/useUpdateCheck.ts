import { ref, readonly } from 'vue'
import { getVersion } from '@tauri-apps/api/app'
import { openUpdateWindow } from '@/composables/useUpdateWindow'

declare const __APP_VERSION__: string

const REPO = 'yoruniubi/Symbix'
const RELEASES_API = `https://api.github.com/repos/${REPO}/releases?per_page=10`
/** 下载页固定指向 latest，避免写死某个 tag */
const DOWNLOAD_PAGE = `https://github.com/${REPO}/releases/latest`
/** 只接受 vX.Y.Z 形式，assets-v1 这类资源 tag 会被忽略 */
const SEMVER_TAG = /^v(\d+)\.(\d+)\.(\d+)$/

const LS_AUTO_CHECK = 'symbix_update_auto_check'
const LS_DISMISSED = 'symbix_update_dismissed'
const LS_LAST_CHECK = 'symbix_update_last_check'
/** 上次发现的更新缓存:重启后设置页仍能直接「查看更新内容」，不用重新检查 */
const LS_LAST_INFO = 'symbix_update_last_info'
const DAY_MS = 24 * 60 * 60 * 1000

export interface UpdateInfo {
  version: string
  /** Release 正文(markdown)，即"更新了哪些内容" */
  body: string
  url: string
  publishedAt: string
}

const currentVersion = ref('')
const latest = ref<UpdateInfo | null>(null)
const checking = ref(false)
/** 至少成功检查过一次(用于区分「还没查」和「查了没新版」) */
const checked = ref(false)
const error = ref('')
const autoCheck = ref(true)
/** 同一窗口内只做一次启动检查(聊天窗与设置窗各自独立，互不影响) */
let startupStarted = false

function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {}
}

function parseVersion(text: string): [number, number, number] | null {
  const m = SEMVER_TAG.exec(text.trim())
  if (!m) return null
  return [Number(m[1]), Number(m[2]), Number(m[3])]
}

/** a > b 返回正数，相等返回 0 */
function compareVersion(a: [number, number, number], b: [number, number, number]): number {
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) return a[i] - b[i]
  }
  return 0
}

/** 当前应用版本：Tauri 环境用原生版本号，浏览器调试回退到构建时注入的版本 */
async function resolveCurrentVersion(): Promise<string> {
  try {
    return await getVersion()
  } catch {
    return typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : '0.0.0'
  }
}

export function useUpdateCheck() {
  /** 读取当前版本(幂等，重复调用只查一次) */
  async function initCurrentVersion(): Promise<string> {
    if (!currentVersion.value) {
      currentVersion.value = await resolveCurrentVersion()
      // 已经升到该版本了(或更高)，缓存里的「新版本」就是过期信息，丢掉
      const cachedParsed = latest.value ? parseVersion(latest.value.version) : null
      const curParsed = parseVersion(`v${currentVersion.value}`)
      if (cachedParsed && curParsed && compareVersion(cachedParsed, curParsed) <= 0) {
        latest.value = null
      }
    }
    return currentVersion.value
  }

  /**
   * 检查更新。
   *
   * @param manual 手动点击「检查更新」= true：忽略 24h 节流与"已忽略该版本"记录，结果直接弹窗
   * @returns 'update' 有新版 / 'latest' 已是最新 / 'throttled' 节流跳过 / 'error' 失败
   */
  async function checkForUpdate(options: { manual?: boolean } = {}): Promise<'update' | 'latest' | 'throttled' | 'error'> {
    const manual = !!options.manual
    if (checking.value) return 'throttled'
    if (!manual) {
      const last = Number(safeGet(LS_LAST_CHECK) || 0)
      if (Date.now() - last < DAY_MS) return 'throttled'
    }

    checking.value = true
    error.value = ''
    try {
      const current = await initCurrentVersion()
      const res = await fetch(RELEASES_API, {
        headers: { Accept: 'application/vnd.github+json' },
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const releases: any[] = await res.json()

      // 取版本号最高的正式发布(忽略 draft / prerelease / 非 semver tag)
      let best: { info: UpdateInfo; parsed: [number, number, number] } | null = null
      for (const rel of releases) {
        if (rel.draft || rel.prerelease) continue
        const parsed = parseVersion(rel.tag_name || '')
        if (!parsed) continue
        if (!best || compareVersion(parsed, best.parsed) > 0) {
          best = {
            parsed,
            info: {
              version: rel.tag_name,
              body: rel.body || '',
              url: rel.html_url || DOWNLOAD_PAGE,
              publishedAt: rel.published_at || '',
            },
          }
        }
      }
      safeSet(LS_LAST_CHECK, String(Date.now()))
      checked.value = true
      if (!best) {
        latest.value = null
        return 'latest'
      }

      const currentParsed = parseVersion(`v${current}`)
      const isNewer = currentParsed ? compareVersion(best.parsed, currentParsed) > 0 : best.info.version !== current
      if (!isNewer) {
        latest.value = null
        return 'latest'
      }

      latest.value = best.info
      try {
        safeSet(LS_LAST_INFO, JSON.stringify(best.info))
      } catch {}
      // 手动检查总是弹；自动检查只在这个版本还没被忽略过时弹
      if (manual || safeGet(LS_DISMISSED) !== best.info.version) {
        void openUpdateWindow()
      }
      return 'update'
    } catch (e: any) {
      error.value = e?.message || String(e)
      return 'error'
    } finally {
      checking.value = false
    }
  }

  /** 自动检查开关(默认开)：影响启动时的静默检查，不影响手动按钮 */
  function setAutoCheck(enabled: boolean) {
    autoCheck.value = enabled
    safeSet(LS_AUTO_CHECK, enabled ? 'on' : 'off')
  }

  /** 启动时读一次开关与上次发现的更新(供设置页直接「查看更新内容」) */
  function loadAutoCheck() {
    autoCheck.value = safeGet(LS_AUTO_CHECK) !== 'off'
    const cached = safeGet(LS_LAST_INFO)
    if (!cached) return
    try {
      const info = JSON.parse(cached) as UpdateInfo
      if (info?.version) latest.value = info
    } catch {}
  }

  /** 本次忽略该版本(下次自动检查不再提醒，手动检查照常弹) */
  function dismiss() {
    if (latest.value) safeSet(LS_DISMISSED, latest.value.version)
  }

  /**
   * 窗口开启时的启动检查（在聊天窗里调，同一个 webview 内只跑一次）。
   * 先看本地缓存的版本信息（重启后不必再联网），再按 24h 节流静默查一次。
   * 发现新版本时开一个独立的更新窗口，不往桌宠/聊天窗里塞弹窗。
   */
  async function startupCheck() {
    if (startupStarted) return
    startupStarted = true
    loadAutoCheck()
    await initCurrentVersion()
    if (!autoCheck.value) return
    // 缓存的版本仍未安装且未被忽略 → 直接开窗，不用等网络
    if (latest.value && safeGet(LS_DISMISSED) !== latest.value.version) {
      void openUpdateWindow()
    }
    setTimeout(() => {
      void checkForUpdate()
    }, 2000)
  }

  return {
    currentVersion: readonly(currentVersion),
    latest: readonly(latest),
    checking: readonly(checking),
    checked: readonly(checked),
    error: readonly(error),
    autoCheck: readonly(autoCheck),
    downloadPage: DOWNLOAD_PAGE,
    initCurrentVersion,
    checkForUpdate,
    setAutoCheck,
    loadAutoCheck,
    startupCheck,
    dismiss,
  }
}
