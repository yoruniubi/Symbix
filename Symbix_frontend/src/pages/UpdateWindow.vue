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
        <span class="badge">{{ t('update.badge') }}</span>
      </div>

      <div class="notes-box">
        <div v-if="checking" class="empty">{{ t('update.checking') }}</div>
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

      <div class="footer">
        <span class="hint">{{ t('update.hint') }}</span>
        <n-space align="center">
          <n-button @click="handleLater">{{ t('update.later') }}</n-button>
          <n-button type="primary" @click="handleDownload">{{ t('update.download') }}</n-button>
        </n-space>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { openUrl } from '@tauri-apps/plugin-opener'
import MarkdownRender from 'markstream-vue'
import TitleBar from '@/components/TitleBar.vue'
import { useUpdateCheck } from '@/composables/useUpdateCheck'

/**
 * 「有新版本」独立窗口。
 *
 * 数据来自 useUpdateCheck：同源 localStorage 里缓存了上次发现的版本，
 * 所以窗口能直接渲染更新内容；缓存没有(比如手动打开)才去联网拉一次。
 */

const { t, locale } = useI18n()
const appWindow = getCurrentWindow()
const { currentVersion, latest, checking, error, loadAutoCheck, initCurrentVersion, checkForUpdate, dismiss } =
  useUpdateCheck()

const publishedText = computed(() => {
  const raw = latest.value?.publishedAt
  if (!raw) return ''
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(locale.value === 'en' ? 'en-US' : 'zh-CN')
})

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

async function handleDownload() {
  const url = latest.value?.url
  if (url) {
    try {
      await openUrl(url)
    } catch {
      window.open(url, '_blank')
    }
  }
  await handleLater()
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
