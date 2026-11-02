<template>
  <div class="update-window">
    <TitleBar />

    <div class="update-content">
      <div class="header">
        <div class="head-left">
          <h1 class="title">{{ t('update.title', { version: latest?.version || '' }) }}</h1>
          <p class="subtitle">
            {{ t('update.fromTo', { current: currentVersion || '—', next: latest?.version || '—' }) }}
            <span v-if="publishedText" class="date">· {{ publishedText }}</span>
          </p>
        </div>
        <span class="badge">{{ phaseLabel }}</span>
      </div>

      <div class="notes-box">
        <div v-if="checking && !latest" class="empty">{{ t('update.checking') }}</div>
        <MarkdownRender
          v-else-if="latest?.body"
          class="notes"
          mode="chat"
          :content="latest.body"
          :final="true"
          :max-live-nodes="0"
        />
        <div v-else-if="error" class="empty">{{ t('update.failed', { msg: error }) }}</div>
        <div v-else class="empty">{{ t('update.emptyNotes') }}</div>
      </div>

      <!-- 进度条只在真正开始下载之后出现, idle 时不占地方 -->
      <div v-if="showProgress" class="progress-box">
        <n-progress
          type="line"
          :percentage="percent"
          :height="6"
          :border-radius="3"
          :show-indicator="false"
          :status="phase === 'failed' ? 'error' : phase === 'done' ? 'success' : 'default'"
        />
        <div class="progress-line">
          <span class="progress-text">{{ progressText }}</span>
          <span v-if="sizeText" class="progress-size">{{ sizeText }}</span>
        </div>
      </div>

      <div class="footer">
        <span class="hint">{{ footHint }}</span>
        <n-space align="center">
          <n-button :disabled="busy" @click="handleLater">{{ laterLabel }}</n-button>
          <n-button v-if="phase === 'done'" type="primary" @click="handleRestart">
            {{ t('update.restart') }}
          </n-button>
          <n-button v-else-if="phase === 'failed'" type="primary" @click="handleDownloadPage">
            {{ t('update.openPage') }}
          </n-button>
          <n-button v-else type="primary" :loading="busy" @click="handleUpdate">
            {{ phase === 'idle' ? t('update.download') : t('update.retrying') }}
          </n-button>
        </n-space>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { invoke } from '@tauri-apps/api/core'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { openUrl } from '@tauri-apps/plugin-opener'
import { check } from '@tauri-apps/plugin-updater'
import { relaunch } from '@tauri-apps/plugin-process'
import MarkdownRender from 'markstream-vue'
import TitleBar from '@/components/TitleBar.vue'
import { useUpdateCheck } from '@/composables/useUpdateCheck'

/**
 * 「有新版本」独立窗口 + 应用内更新进度。
 *
 * 数据分两条腿:
 * - 版本信息(有没有新版 / 更新内容)来自 useUpdateCheck(GitHub Releases API),
 *   这样 Linux deb、浏览器调试这类「装不了」的场景也能正常展示更新说明。
 * - 真正的下载与安装交给 tauri-plugin-updater:它按平台拉 latest.json 里对应的
 *   安装包、边下边验签、下完静默拉起安装器(Windows 走 NSIS passive 模式)。
 *   插件不可用(dev / 浏览器 / Linux deb)时自动退回「打开下载页」。
 *
 * 窗口随时可关:下载跑在 Rust 侧,关窗只是丢掉进度显示,不影响安装。
 */

type Phase = 'idle' | 'checking' | 'downloading' | 'installing' | 'done' | 'failed'

const { t, locale } = useI18n()
const appWindow = getCurrentWindow()
const { currentVersion, latest, checking, error, downloadPage, loadAutoCheck, initCurrentVersion, checkForUpdate, dismiss } =
  useUpdateCheck()

const phase = ref<Phase>('idle')
const totalBytes = ref(0)
const receivedBytes = ref(0)
const failReason = ref('')

/** 下载中 / 安装中时禁止关掉后再点按钮,避免并发两次下载 */
const busy = computed(() => phase.value === 'checking' || phase.value === 'downloading')
const showProgress = computed(() => phase.value === 'downloading' || phase.value === 'installing' || phase.value === 'done' || phase.value === 'failed')
const percent = computed(() => {
  if (phase.value === 'done') return 100
  if (!totalBytes.value) return 0
  return Math.min(100, Math.round((receivedBytes.value / totalBytes.value) * 100))
})

const phaseLabel = computed(() => {
  switch (phase.value) {
    case 'downloading':
      return t('update.badgeDownloading')
    case 'installing':
      return t('update.badgeInstalling')
    case 'done':
      return t('update.badgeDone')
    case 'failed':
      return t('update.badgeFailed')
    default:
      return t('update.badge')
  }
})

const laterLabel = computed(() => (phase.value === 'done' ? t('update.laterRestart') : t('update.later')))

const footHint = computed(() => {
  if (phase.value === 'done') return t('update.hintDone')
  if (phase.value === 'failed') return t('update.hintFailed', { msg: failReason.value })
  if (phase.value === 'downloading' || phase.value === 'installing') return t('update.hintBackground')
  return t('update.hint')
})

const progressText = computed(() => {
  switch (phase.value) {
    case 'downloading':
      return t('update.downloading')
    case 'installing':
      return t('update.installing')
    case 'done':
      return t('update.installed')
    case 'failed':
      return t('update.installFailed')
    default:
      return ''
  }
})

const sizeText = computed(() => {
  if (!totalBytes.value) return ''
  return `${formatBytes(receivedBytes.value)} / ${formatBytes(totalBytes.value)}`
})

const publishedText = computed(() => {
  const raw = latest.value?.publishedAt
  if (!raw) return ''
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(locale.value === 'en' ? 'en-US' : 'zh-CN')
})

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

onMounted(async () => {
  loadAutoCheck()
  await initCurrentVersion()
  // 没有缓存内容时补一次请求(手动打开的窗口)
  if (!latest.value) await checkForUpdate({ manual: true })
})

/** 稍后：记住该版本，自动检查不再提醒(设置页手动检查仍会再开这个窗口) */
async function handleLater() {
  dismiss()
  try {
    await appWindow.close()
  } catch {}
}

/** 退回老路子:浏览器打开发布页，用户自己下安装包 */
async function handleDownloadPage() {
  const url = latest.value?.url || downloadPage
  try {
    await openUrl(url)
  } catch {
    window.open(url, '_blank')
  }
  await handleLater()
}

async function handleUpdate() {
  failReason.value = ''
  receivedBytes.value = 0
  totalBytes.value = 0
  phase.value = 'checking'
  try {
    const update = await check()
    // 插件说没有新版(latest.json 未跟上/手动打开的窗口):直接给下载页
    if (!update) {
      phase.value = 'idle'
      await handleDownloadPage()
      return
    }
    phase.value = 'downloading'
    // 下载与安装拆成两步:中间要把后端收掉,否则 Windows 上安装器改不动被占用的 exe
    await update.download((event) => {
      switch (event.event) {
        case 'Started':
          totalBytes.value = event.data.contentLength ?? 0
          break
        case 'Progress':
          receivedBytes.value += event.data.chunkLength
          break
        case 'Finished':
          receivedBytes.value = totalBytes.value || receivedBytes.value
          break
      }
    })

    phase.value = 'installing'
    try {
      await invoke('stop_backend_for_update')
    } catch {
      // 浏览器调试或老版本壳没有这个命令,不影响后面安装
    }
    await update.install()
    // Windows 上走到这一步前进程已被安装器接管并退出,所以这里主要是 macOS
    phase.value = 'done'
  } catch (e: any) {
    phase.value = 'failed'
    failReason.value = e?.message || String(e)
  }
}

async function handleRestart() {
  try {
    await relaunch()
  } catch {
    try {
      await appWindow.close()
    } catch {}
  }
}
</script>

<style scoped>
.update-window {
  width: 100vw;
  height: 100vh;
  background: var(--bg-app);
  color: var(--text-primary);
  padding-top: 32px;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  overflow: hidden;
}

.update-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 18px 14px;
  box-sizing: border-box;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
}

.subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.date {
  margin-left: 2px;
}

.badge {
  flex: none;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--accent-soft);
  color: var(--text-primary);
}

.notes-box {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 14px;
  border-radius: 10px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
}

.notes {
  font-size: 13px;
  line-height: 1.75;
  color: var(--text-primary);
}

.empty {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 10px 0;
}

.progress-box {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.progress-text {
  font-size: 12px;
  color: var(--text-secondary);
}

.progress-size {
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.hint {
  font-size: 11px;
  color: var(--text-secondary);
}
</style>
