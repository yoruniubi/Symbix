<template>
  <!-- 本轮产物:Agent 每写/下载一个文件就多一张卡,免得用户照着路径去翻 -->
  <div v-if="artifacts.length" class="artifact-bar">
    <div class="artifact-head">
      <span class="artifact-title">{{ t('artifact.title') }}</span>
      <span class="artifact-count">{{ artifacts.length }}</span>
    </div>

    <div
      v-for="(a, i) in artifacts"
      :key="a.path"
      class="artifact-item"
      :class="{ expanded: previewIndex === i }"
    >
      <div class="artifact-row">
        <svg class="artifact-icon" :class="`kind-${a.kind}`" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path v-for="(d, di) in iconPaths(a.kind)" :key="di" :d="d" />
        </svg>

        <div class="artifact-meta">
          <div class="artifact-name" :title="a.path">{{ a.name }}</div>
          <div class="artifact-sub">
            <span class="artifact-op" :class="a.op">{{ opLabel(a.op) }}</span>
            <span class="artifact-dir" :title="a.path">{{ a.dir }}</span>
          </div>
        </div>

        <div class="artifact-actions">
          <button
            v-if="canPreviewArtifact(a)"
            class="artifact-btn"
            @click="togglePreview(a, i)"
          >{{ previewIndex === i ? t('artifact.collapse') : t('artifact.preview') }}</button>
          <!-- 「打开」按钮已移除:交给系统打开需要按文件类型挑程序(浏览器/编辑器/
               Office/看图器),这条路不可靠。改为「预览」内联看内容 + 「定位」在资源
               管理器里高亮,用户自己选程序。 -->
          <button class="artifact-btn" @click="revealArtifact(a)">{{ t('artifact.reveal') }}</button>
        </div>
      </div>

      <!-- 内联预览:图片走 /files/raw 字节流,文本/代码走 /files/read -->
      <div v-if="previewIndex === i" class="artifact-preview">
        <div v-if="previewLoading" class="artifact-preview-hint">{{ t('artifact.loading') }}</div>
        <img v-else-if="previewUrl" class="artifact-preview-img" :src="previewUrl" :alt="a.name" />
        <pre v-else-if="previewText" class="artifact-preview-text">{{ previewText }}</pre>
        <div v-else class="artifact-preview-hint">{{ t('artifact.previewEmpty') }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { BACKEND_URL } from '@/utils/backend'
import {
  canPreviewArtifact,
  collectMessageArtifacts,
  type ArtifactKind,
  type ArtifactOp,
  type MessageArtifact,
} from '@/utils/msgArtifacts'

const props = defineProps<{
  /** 该条消息的 steps,内部自行挑出产物 */
  steps?: unknown
}>()

const { t } = useI18n()
const messageUi = useMessage()

const artifacts = computed<MessageArtifact[]>(() => collectMessageArtifacts(props.steps))

/** 展开预览的下标;-1 表示全收起(一次只展开一个,避免长会话里堆一屏图) */
const previewIndex = ref(-1)
const previewUrl = ref('')
const previewText = ref('')
const previewLoading = ref(false)

/** 预览请求令牌:快速来回点时不把旧结果盖到新卡片上 */
let previewToken = 0

function isTauriApp(): boolean {
  return typeof window !== 'undefined' && !!(window as any).__TAURI_INTERNALS__
}

/** 预览文本截断长度:够看开头判断内容,又不至于把长日志塞满页面 */
const PREVIEW_TEXT_LIMIT = 4000

function releasePreview() {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
  previewText.value = ''
}

onUnmounted(releasePreview)

// 消息重算(流式刷新)导致产物列表变了就收起预览,避免下标错位指到别的文件
watch(
  () => artifacts.value.length,
  () => {
    previewIndex.value = -1
    releasePreview()
  },
)

/** 文件已经不在了(404):这是历史卡片过期,不是「预览功能坏了」,文案要分开说 */
class ArtifactGoneError extends Error {}

async function togglePreview(a: MessageArtifact, index: number) {
  if (previewIndex.value === index) {
    previewIndex.value = -1
    releasePreview()
    return
  }
  previewIndex.value = index
  releasePreview()
  previewLoading.value = true
  const token = ++previewToken
  try {
    if (a.kind === 'image') {
      const res = await fetch(`${BACKEND_URL}/api/files/raw?path=${encodeURIComponent(a.path)}`)
      if (res.status === 404) throw new ArtifactGoneError()
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      if (token !== previewToken) return
      previewUrl.value = URL.createObjectURL(blob)
    } else {
      const res = await fetch(`${BACKEND_URL}/api/files/read?path=${encodeURIComponent(a.path)}`)
      if (res.status === 404) throw new ArtifactGoneError()
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (token !== previewToken) return
      const content = String(data?.content ?? '')
      previewText.value = content.length > PREVIEW_TEXT_LIMIT
        ? `${content.slice(0, PREVIEW_TEXT_LIMIT)}\n\n${t('artifact.truncated')}`
        : content
    }
  } catch (e) {
    if (token !== previewToken) return
    if (e instanceof ArtifactGoneError) messageUi.warning(t('artifact.previewGone'))
    else messageUi.error(t('artifact.previewFailed', { err: String(e) }))
  } finally {
    if (token === previewToken) previewLoading.value = false
  }
}

async function copyPath(path: string) {
  try {
    await navigator.clipboard.writeText(path)
    messageUi.info(t('artifact.copied'))
  } catch {
    messageUi.warning(path)
  }
}

async function revealArtifact(a: MessageArtifact) {
  if (!isTauriApp()) return copyPath(a.path)
  try {
    const { revealItemInDir } = await import('@tauri-apps/plugin-opener')
    await revealItemInDir(a.path)
  } catch (e) {
    messageUi.error(t('artifact.revealFailed', { err: String(e) }))
  }
}

const OP_LABEL_KEY: Record<ArtifactOp, string> = {
  create: 'artifact.opCreate',
  edit: 'artifact.opEdit',
  download: 'artifact.opDownload',
  image: 'artifact.opImage',
}

function opLabel(op: ArtifactOp): string {
  return t(OP_LABEL_KEY[op] || 'artifact.opCreate')
}

/** 按类型给图标路径(统一 24x24 线框,和聊天页其它图标一个风格) */
const ICON_PATHS: Record<ArtifactKind, string[]> = {
  image: [
    'M21 19V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2z',
    'M3 16l5-5 4 4 3-3 6 6',
    'M9 9.5a1.2 1.2 0 1 1-2.4 0 1.2 1.2 0 0 1 2.4 0z',
  ],
  doc: ['M14 3v5h5', 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z', 'M8 13h8', 'M8 17h5'],
  sheet: ['M14 3v5h5', 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z', 'M8 12h8v6H8z', 'M8 15h8'],
  slide: ['M14 3v5h5', 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z', 'M9 17l3-4 2.5 2.5L17 12'],
  pdf: ['M14 3v5h5', 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z', 'M9 13h1.5a1.5 1.5 0 0 1 0 3H9v3'],
  text: ['M14 3v5h5', 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z', 'M8 12h8', 'M8 16h8'],
  code: ['M14 3v5h5', 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z', 'M10 12l-2 2 2 2', 'M14 12l2 2-2 2'],
  archive: ['M21 8v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8', 'M2 8h20v3H2z', 'M10 15h4'],
  other: ['M14 3v5h5', 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z'],
}

function iconPaths(kind: ArtifactKind): string[] {
  return ICON_PATHS[kind] || ICON_PATHS.other
}
</script>

<style scoped>
.artifact-bar {
  max-width: min(72%, 760px);
  margin-bottom: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md, 8px);
  background: var(--bg-elevated);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.artifact-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 2px 4px;
}

.artifact-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.artifact-count {
  font-size: 11px;
  padding: 0 5px;
  border-radius: 8px;
  background: var(--accent-soft);
  color: var(--accent-500, #EF6B6E);
}

.artifact-item {
  border-radius: var(--radius-sm, 6px);
  overflow: hidden;
}

.artifact-item.expanded {
  background: var(--bg-app);
}

.artifact-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px;
  border-radius: var(--radius-sm, 6px);
}

.artifact-row:hover {
  background: var(--bg-app);
}

.artifact-icon {
  flex-shrink: 0;
  color: var(--text-secondary);
}

.artifact-icon.kind-image {
  color: #4CAF7D;
}

.artifact-icon.kind-pdf {
  color: #E05B5B;
}

.artifact-icon.kind-sheet {
  color: #3E9A6B;
}

.artifact-icon.kind-doc {
  color: #4A82D8;
}

.artifact-icon.kind-slide {
  color: #D88A3A;
}

.artifact-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.artifact-name {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.artifact-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.artifact-op {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--accent-500, #EF6B6E);
}

.artifact-op.edit {
  color: #D88A3A;
}

.artifact-op.download,
.artifact-op.image {
  color: #4CAF7D;
}

.artifact-dir {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.artifact-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}

.artifact-btn {
  font-size: 11px;
  padding: 2px 7px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 6px);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.artifact-btn:hover {
  color: var(--accent-500, #EF6B6E);
  border-color: var(--accent-500, #EF6B6E);
}

.artifact-preview {
  padding: 6px 8px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.artifact-preview-img {
  max-width: 100%;
  max-height: 320px;
  object-fit: contain;
  align-self: flex-start;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--border);
  background: #fff;
}

.artifact-preview-text {
  margin: 0;
  max-height: 300px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.5;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.artifact-preview-hint {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
