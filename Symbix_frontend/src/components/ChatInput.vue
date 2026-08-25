<template>
  <div class="input-container" @paste="handlePaste">
    <!-- 附件预览区 -->
    <div v-if="attachments.length > 0" class="attachment-preview">
      <div v-for="(file, idx) in attachments" :key="idx" class="file-chip" :class="{ 'is-image': !!file.previewSrc }">
        <!-- 图片附件:显示缩略图预览 -->
        <img v-if="file.previewSrc" :src="file.previewSrc" class="file-chip-thumb" alt="" />
        <!-- 非图片附件:文件图标 -->
        <n-icon v-else size="16" class="file-chip-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
          </svg>
        </n-icon>
        <span class="file-chip-name">{{ file.name }}<span v-if="file.status==='uploading'" class="file-chip-status">{{ t('chatInput.fileUploading') }}</span><span v-else-if="file.status==='error'" class="file-chip-status err">{{ t('chatInput.fileFailed') }}</span></span>
        <n-button text size="tiny" @click="removeAttachment(idx)" class="file-chip-remove">
          <n-icon size="14"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg></n-icon>
        </n-button>
      </div>
    </div>

    <!-- 主输入区 -->
    <div class="input-row">

      <!-- 文本输入 -->
      <n-input
        ref="inputRef"
        v-model:value="inputValue"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 5 }"
        :placeholder="t('chatInput.placeholder')"
        @keydown="handleInputKeydown"
        :disabled="loading"
        class="chat-input"
      />

      <!-- 停止按钮 (loading 时显示) -->
      <n-button
        v-if="loading"
        circle
        @click="emit('stop')"
        class="stop-btn"
        :title="t('chatInput.stopGenerate')"
      >
        <template #icon>
          <n-icon size="16">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2"/>
            </svg>
          </n-icon>
        </template>
      </n-button>
      <!-- 发送按钮 -->
      <n-button
        v-else
        type="primary"
        circle
        @click="handleSend"
        :disabled="!canSend"
        class="send-btn"
        :class="{ 'has-content': canSend }"
      >
        <template #icon>
          <n-icon size="18">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </n-icon>
        </template>
      </n-button>
    </div>

    <!-- 底部工具栏 -->
    <div class="input-footer">
      <!-- 上传文件按钮 -->
      <n-upload
        :custom-request="handleFileUpload"
        :show-file-list="false"
        multiple
        accept="*"
        style="width: auto; flex-shrink: 0;"
      >
        <n-button text class="tool-btn" :title="t('chatInput.uploadFile')">
          <n-icon size="20">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
          </n-icon>
        </n-button>
      </n-upload>
      <!-- 语音输入按钮 -->
      <n-button text class="tool-btn voice-btn" :class="{ recording: isRecording }" @click="toggleVoice" :title="t('chatInput.voiceInput')">
        <n-icon size="20">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
            <line x1="12" y1="19" x2="12" y2="23"/>
            <line x1="8" y1="23" x2="16" y2="23"/>
          </svg>
        </n-icon>
        <span v-if="isRecording" class="recording-dot"></span>
      </n-button>
      <n-popover v-model:show="showModelPopover" trigger="click" placement="top-start" :show-arrow="false" :content-style="{ padding: 0 }" content-class="model-popover-content">
        <template #trigger>
          <n-button text size="tiny" class="footer-btn">
            <n-icon size="14" style="margin-right:3px;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/></svg>
            </n-icon>
            {{ t('chatInput.selectModel') }}: {{ currentModelLabel }}
          </n-button>
        </template>
        <div class="model-list-scroll">
          <div
            v-for="opt in modelOptions"
            :key="opt.value"
            class="model-item"
            :class="{ active: opt.value === currentModel }"
            @click="handleModelSelect(opt.value)"
          >
            <span class="model-item-label">{{ opt.label }}</span>
            <svg v-if="opt.value === currentModel" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
        </div>
      </n-popover>
      <span class="footer-hint" v-if="!loading">{{ t('chatInput.enterToSend') }}</span>
      <span class="footer-hint recording-hint" v-else-if="isRecording">{{ t('chatInput.listening') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { NIcon, useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'

export interface AttachmentItem {
  name: string
  path?: string
  mime?: string
  size?: number
  kind?: string
  preview?: string
  /** 本地即时缩略图预览(dataURL / blobURL),粘贴或选择图片立即展示 */
  previewSrc?: string
  status?: 'uploading' | 'ok' | 'error'
  error?: string
  file?: File
}


const props = defineProps<{
  loading: boolean
  modelOptions: { label: string; value: string }[]
  currentModel: string
  /** 当前会话 id，用于上传目录隔离；未创建会话时用 pending 占位 */
  sessionId?: string | null
}>()

const emit = defineEmits<{
  send: [text: string, files: AttachmentItem[]]
  'update:model': [model: string]
  stop: []
}>()

const messageUi = useMessage()
const inputValue = ref('')
const inputRef = ref<any>(null)
const attachments = ref<AttachmentItem[]>([])
const isRecording = ref(false)
const showModelPopover = ref(false)
let recordTimer: any = null

const { t } = useI18n()

const BACKEND_URL = 'http://127.0.0.1:8000'

/** 图片扩展名集合 */
const IMAGE_EXTS = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']

/** 缓存模型视觉能力查询结果，避免重复请求 */
let _visionCache: { model: string; vision: boolean } | null = null

/** 查询当前模型是否支持视觉（带缓存） */
async function checkModelVision(): Promise<boolean> {
  const model = props.currentModel
  if (!model) return false
  if (_visionCache && _visionCache.model === model) return _visionCache.vision
  try {
    // 调用实时探测接口（后端发起最小请求测试）
    const res = await fetch(`${BACKEND_URL}/model/probe-vision?model=${encodeURIComponent(model)}`)
    if (!res.ok) return false
    const data = await res.json()
    const vision = !!data.vision
    _visionCache = { model, vision }
    return vision
  } catch {
    return false
  }
}

/** 模型切换时清除缓存（外部可调用） */
function invalidateVisionCache() {
  _visionCache = null
}

// 监听模型变化时清除缓存
watch(() => props.currentModel, () => {
  _visionCache = null
})

/** 判断文件是否为图片 */
function isImageFile(name: string, mime?: string): boolean {
  if (mime && mime.startsWith('image/')) return true
  const ext = name.slice(name.lastIndexOf('.')).toLowerCase()
  return IMAGE_EXTS.includes(ext)
}

const canSend = computed(() => {
  const textOk = !!inputValue.value.trim()
  const readyFiles = attachments.value.filter(a => a.status === 'ok' || (!a.status && a.path))
  const busy = attachments.value.some(a => a.status === 'uploading')
  return !busy && (textOk || readyFiles.length > 0)
})

/** 生成图片本地即时预览(dataURL),供附件区缩略图显示 */
function makeImagePreview(raw: File): string | undefined {
  if (!isImageFile(raw.name, raw.type)) return undefined
  try {
    return URL.createObjectURL(raw)
  } catch {
    return undefined
  }
}

const currentModelLabel = computed(() => {
  const opt = props.modelOptions.find(o => o.value === props.currentModel)
  return opt?.label || props.currentModel || t('chatInput.selectModel')
})

function handleSend() {
  const text = inputValue.value.trim()
  if (!canSend.value || props.loading) return
  const files = attachments.value.filter(a => a.status === 'ok' || (!!a.path && a.status !== 'error'))
  attachments.value.forEach(revokePreview)
  attachments.value = []
  emit('send', text || '', files)
  inputValue.value = ''
}

/** 释放 blob URL,避免内存泄漏 */
function revokePreview(a: AttachmentItem) {
  if (a.previewSrc && a.previewSrc.startsWith('blob:')) {
    try { URL.revokeObjectURL(a.previewSrc) } catch { /* ignore */ }
  }
}

async function handleFileUpload({ file, onFinish, onError }: any) {
  const raw: File | undefined = file?.file
  if (!raw) {
    onFinish?.()
    return
  }
  await uploadFile(raw)
  onFinish?.()
}

/**
 * 上传单个文件到后端并加入附件列表(status: uploading -> ok/error)
 * 同时生成图片即时缩略图预览。粘贴图片与选择上传共用此逻辑。
 */
async function uploadFile(raw: File) {
  const item: AttachmentItem = {
    name: raw.name,
    size: raw.size,
    mime: raw.type,
    status: 'uploading',
    file: raw,
    previewSrc: makeImagePreview(raw),
  }
  // 立即生成本地预览(在 upload 完成前就能看到缩略图)
  attachments.value.push(item)
  const idx = attachments.value.length - 1
  try {
    const form = new FormData()
    form.append('files', raw, raw.name)
    // 优先用父组件传入的会话 id;新对话尚未建 session 时用 pending 目录
    form.append('session_id', props.sessionId || 'pending')
    const res = await fetch(`${BACKEND_URL}/upload`, {

      method: 'POST',
      body: form,
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    const meta = (data.uploaded && data.uploaded[0]) || {}
    if (meta.status === 'ok') {
      attachments.value[idx] = {
        ...attachments.value[idx],
        path: meta.path,
        name: meta.filename || raw.name,
        mime: meta.mime || raw.type,
        size: meta.size ?? raw.size,
        kind: meta.kind,
        preview: meta.preview,
        status: 'ok',
        file: undefined,
      }
      // 如果是图片,检查当前模型是否支持视觉
      if (isImageFile(raw.name, raw.type)) {
        const vision = await checkModelVision()
        if (!vision) {
          messageUi.warning(t('chatInput.imageNoVision', { model: props.currentModel }))
        }
      }
    } else {
      attachments.value[idx] = {
        ...attachments.value[idx],
        status: 'error',
        error: meta.message || '上传失败',
      }
      messageUi.error(t('chatInput.uploadFailed', { name: raw.name }))
    }
  } catch (e: any) {
    attachments.value[idx] = {
      ...attachments.value[idx],
      status: 'error',
      error: e?.message || String(e),
    }
    messageUi.error(t('chatInput.uploadFailed', { name: raw.name }))
  }
}

/** 处理 Ctrl+V 粘贴:提取剪贴板中的图片文件(截图/复制的图)并走上传预览流程 */
async function handlePaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items || []
  if (items.length === 0) return
  const imageFiles: File[] = []
  for (let i = 0; i < items.length; i++) {
    const it = items[i]
    if (it.kind === 'file' && it.type && it.type.startsWith('image/')) {
      const f = it.getAsFile()
      if (f) imageFiles.push(f)
    }
  }
  if (imageFiles.length === 0) return
  // 阻止浏览器将图片二进制数据粘贴为文本
  e.preventDefault()
  // 剪贴板粘贴的图片可能无文件名,补充一个可读名字
  const named = imageFiles.map((f, i) => {
    if (f.name) return f
    const ext = (f.type.split('/')[1] || 'png').replace('jpeg', 'jpg')
    return new File([f], `pasted-image-${Date.now()}-${i + 1}.${ext}`, { type: f.type })
  })
  for (const f of named) await uploadFile(f)
}

function removeAttachment(idx: number) {
  revokePreview(attachments.value[idx])
  attachments.value.splice(idx, 1)
}

function toggleVoice() {
  if (isRecording.value) {
    stopVoice()
  } else {
    startVoice()
  }
}

function startVoice() {
  isRecording.value = true
  // Simulated voice recording - real impl would use Web Speech API
  recordTimer = setTimeout(() => {
    stopVoice()
  }, 5000)
}

function stopVoice() {
  isRecording.value = false
  if (recordTimer) clearTimeout(recordTimer)
}

function handleModelSelect(modelValue: string) {
  emit('update:model', modelValue)
  showModelPopover.value = false
}

function handleInputKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

// 组件卸载时释放所有 blob URL
onBeforeUnmount(() => {
  attachments.value.forEach(revokePreview)
})
</script>

<style scoped>
.input-container {
  flex: 0 0 auto;
  flex-shrink: 0;
  width: 100%;
  box-sizing: border-box;
  background: var(--bg-elevated);
  backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg, 12px);
  padding: 8px 12px 6px;
  margin-bottom: env(safe-area-inset-bottom, 0px);
  transition: border-color var(--duration-base, 180ms) var(--ease-standard, ease),
              box-shadow var(--duration-base, 180ms) var(--ease-standard, ease);
}

.input-container:focus-within {
  border-color: var(--accent-border);
  box-shadow: 0 0 0 2px rgba(239, 107, 110, 0.12);
}


/* 附件预览 */
.attachment-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 4px 8px;
}
.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--accent-soft);
  border: 1px solid var(--accent-border);
  border-radius: var(--radius-sm, 6px);
  padding: 4px 6px 4px 10px;
  font-size: 12px;
  color: var(--text-primary);
}
.file-chip.is-image {
  padding: 4px;
}
/* 图片附件缩略图预览 */
.file-chip-thumb {
  width: 36px;
  height: 36px;
  object-fit: cover;
  border-radius: var(--radius-sm, 4px);
  flex-shrink: 0;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  cursor: pointer;
  transition: transform var(--duration-fast, 120ms) var(--ease-standard, ease);
}
.file-chip-thumb:hover {
  transform: scale(1.06);
}
.file-chip-icon {
  color: var(--accent-500, #EF6B6E);
  flex-shrink: 0;
}
.file-chip-status { margin-left: 4px; font-size: 10px; color: var(--accent-300, #F7A85B); }
.file-chip-status.err { color: var(--error, #D3555A); }

.file-chip-name {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-chip-remove {
  color: #94a3b8 !important;
  padding: 2px !important;
}
.file-chip-remove:hover {
  color: #f87171 !important;
}

/* 主输入行 */
.input-row {
  display: flex;
  align-items: flex-end;
  gap: 6px;
}
.tool-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50% !important;
  color: var(--text-secondary);
  flex-shrink: 0;
  transition: all var(--duration-base, 180ms) var(--ease-standard, ease);
}
.tool-btn:hover {
  color: var(--accent-500, #EF6B6E) !important;
  background: var(--accent-soft) !important;
}
.tool-btn:active {
  transform: scale(0.92);
}
.voice-btn.recording {
  color: var(--error, #D3555A) !important;
  background: rgba(211, 85, 90, 0.15) !important;
  animation: pulse-rec 1.5s ease-in-out infinite;
}
.recording-dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--error, #D3555A);
  box-shadow: 0 0 6px var(--error, #D3555A);
}
@keyframes pulse-rec {
  0%, 100% { box-shadow: 0 0 0 0 rgba(211, 85, 90, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(211, 85, 90, 0); }
}


/* 文本输入 */
.chat-input {
  flex: 1;
  overflow: hidden;
}
.chat-input :deep(.n-input-wrapper) {
  padding: 0 !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
.chat-input :deep(.n-input__textarea-el) {
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  padding: 8px 4px 6px 4px;
  caret-color: var(--accent-500, #EF6B6E);
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.55;
}
.chat-input :deep(.n-input__textarea-el:focus) {
  background: transparent !important;
}
.chat-input :deep(.n-input__textarea-el:-webkit-autofill),
.chat-input :deep(.n-input__textarea-el:-webkit-autofill:hover),
.chat-input :deep(.n-input__textarea-el:-webkit-autofill:focus) {
  -webkit-box-shadow: 0 0 0 1000px var(--bg-elevated) inset !important;
  -webkit-text-fill-color: var(--text-primary) !important;
  transition: background-color 5000s ease-in-out 0s;
}
.chat-input :deep(.n-input__placeholder) {
  padding: 8px 4px 6px 4px !important;
  line-height: 1.55;
  color: var(--text-muted);
}

.chat-input :deep(.n-input__border),
.chat-input :deep(.n-input__state-border) {
  display: none !important;
}
.chat-input :deep(.n-input) {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
.chat-input :deep(.n-input)::before {
  display: none !important;
}
.chat-input :deep(.n-input__textarea-mirror) {
  background: transparent !important;
  border: none !important;
}

/* 发送按钮 */
.send-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  opacity: 0.5;
  transition: all 0.25s ease;
}
.send-btn :deep(.n-button__border),
.send-btn :deep(.n-button__state-border) {
  border: none !important;
}
.send-btn :deep(.n-button__content) {
  background: var(--bg-surface) !important;
  border-radius: 50%;
}
.send-btn.has-content {
  opacity: 1;
}
.send-btn.has-content :deep(.n-button__content) {
  background: var(--accent-500, #EF6B6E) !important;
}
.send-btn.has-content:not(:disabled):hover {
  transform: scale(1.08);
  box-shadow: var(--shadow-glow, 0 0 24px rgba(242, 101, 122, 0.25));
}
.send-btn.has-content:not(:disabled):hover :deep(.n-button__content) {
  background: var(--accent-600, #E2515F) !important;
}

.send-btn:disabled {
  opacity: 0.35;
}

/* 停止按钮 */
.stop-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  transition: all 0.25s ease;
}
.stop-btn :deep(.n-button__border),
.stop-btn :deep(.n-button__state-border) {
  border: none !important;
}
.stop-btn :deep(.n-button__content) {
  background: rgba(211, 85, 90, 0.15);
  border-radius: 50%;
  color: var(--error, #D3555A);
}
.stop-btn:hover {
  transform: scale(1.08);
  box-shadow: 0 4px 14px rgba(211, 85, 90, 0.3);
}
.stop-btn:hover :deep(.n-button__content) {
  background: rgba(211, 85, 90, 0.25);
}

/* 底部栏 */
.input-footer {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 4px;
  padding: 2px 6px 2px;
  border-top: 1px solid var(--border);
  margin-top: 2px;
}
.footer-btn {
  font-size: 11px;
  color: var(--text-muted) !important;
  padding: 2px 8px !important;
  border-radius: var(--radius-sm, 6px) !important;
  transition: all var(--duration-base, 180ms) var(--ease-standard, ease);
}
.footer-btn:hover {
  color: var(--accent-500, #EF6B6E) !important;
  background: var(--accent-soft) !important;
}
.footer-hint {
  font-size: 10px;
  color: var(--text-muted);
  margin-left: auto;
}
.recording-hint {
  color: var(--error, #D3555A);
  animation: blink-text 1s ease-in-out infinite;
}

@keyframes blink-text {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
:deep(.n-upload) {
  width: auto !important;
  flex-shrink: 0;
}
:deep(.n-upload-trigger) {
  width: auto !important;
}
</style>

<style>
/* 模型选择弹出框 - 渲染到 body，需要全局样式 */
/*  */
.model-list-scroll {
  max-height: 240px;
  overflow-y: auto;
  padding: 4px;
}
.model-list-scroll::-webkit-scrollbar {
  width: 4px;
}
.model-list-scroll::-webkit-scrollbar-track {
  background: transparent;
}
.model-list-scroll::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}
.model-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border-radius: var(--radius-md, 8px);
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
  transition: all var(--duration-fast, 120ms) var(--ease-standard, ease);
  white-space: nowrap;
}
.model-item:hover {
  background: var(--accent-soft);
  color: var(--text-primary);
}
.model-item.active {
  color: var(--accent-500, #EF6B6E);
  background: var(--accent-soft);
}

.model-item-label {
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
