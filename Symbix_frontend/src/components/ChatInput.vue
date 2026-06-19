<template>
  <div class="input-container">
    <!-- 附件预览区 -->
    <div v-if="attachments.length > 0" class="attachment-preview">
      <div v-for="(file, idx) in attachments" :key="idx" class="file-chip">
        <n-icon size="16" class="file-chip-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
          </svg>
        </n-icon>
        <span class="file-chip-name">{{ file.name }}</span>
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
        placeholder="输入消息，Enter 发送，Shift+Enter 换行..."
        @keydown.enter.exact.prevent="handleSend"
        :disabled="loading"
        class="chat-input"
      />

      <!-- 发送按钮 -->
      <n-button
        type="primary"
        circle
        @click="handleSend"
        :disabled="!canSend || loading"
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
        <n-button text class="tool-btn" title="上传文件">
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
      <n-button text class="tool-btn voice-btn" :class="{ recording: isRecording }" @click="toggleVoice" title="语音输入">
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
      <n-dropdown trigger="click" :options="modelOptions" @select="handleModelSelect">
        <n-button text size="tiny" class="footer-btn">
          <n-icon size="14" style="margin-right:3px;">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/></svg>
          </n-icon>
          {{ currentModelLabel }}
        </n-button>
      </n-dropdown>
      <span class="footer-hint" v-if="!loading">Enter 发送 · Shift+Enter 换行</span>
      <span class="footer-hint recording-hint" v-else-if="isRecording">🎤 正在聆听...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { NIcon } from 'naive-ui'

const props = defineProps<{
  loading: boolean
  modelOptions: { label: string; value: string }[]
  currentModel: string
}>()

const emit = defineEmits<{
  send: [text: string, files: File[]]
  'update:model': [model: string]
}>()

const inputValue = ref('')
const inputRef = ref<any>(null)
const attachments = ref<File[]>([])
const isRecording = ref(false)
let recordTimer: any = null

const canSend = computed(() => inputValue.value.trim() || attachments.value.length > 0)

const currentModelLabel = computed(() => {
  const opt = props.modelOptions.find(o => o.value === props.currentModel)
  return opt?.label || props.currentModel || '选择模型'
})

function handleSend() {
  const text = inputValue.value.trim()
  if (!canSend.value || props.loading) return
  const files = [...attachments.value]
  attachments.value = []
  emit('send', text || '', files)
  inputValue.value = ''
}

function handleFileUpload({ file, onFinish }: any) {
  if (file.file) {
    attachments.value.push(file.file)
  }
  onFinish()  // 加这一行
}

function removeAttachment(idx: number) {
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
}
</script>

<style scoped>
.input-container {
  flex-shrink: 0;
  background: rgba(22, 22, 28, 0.8);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 20px;
  padding: 8px 12px 4px;
  transition: border-color 0.3s ease;
}
.input-container:focus-within {
  border-color: rgba(99, 102, 241, 0.4);
  box-shadow: 0 0 20px rgba(99, 102, 241, 0.06);
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
  background: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 10px;
  padding: 4px 6px 4px 10px;
  font-size: 12px;
  color: #c7d2fe;
}
.file-chip-icon {
  color: #818cf8;
  flex-shrink: 0;
}
.file-chip-name {
  max-width: 120px;
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
  color: #85859b;
  flex-shrink: 0;
  transition: all 0.2s ease;
}
.tool-btn:hover {
  color: #c7d2fe !important;
  background: rgba(99, 102, 241, 0.1) !important;
}
.tool-btn:active {
  transform: scale(0.92);
}
.voice-btn.recording {
  color: #ef4444 !important;
  background: rgba(239, 68, 68, 0.15) !important;
  animation: pulse-rec 1.5s ease-in-out infinite;
}
.recording-dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 6px #ef4444;
}
@keyframes pulse-rec {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }
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
  caret-color: #6366f1;
  color: #e4e4e7;
  font-size: 14px;
  line-height: 1.55;
}
.chat-input :deep(.n-input__textarea-el:focus) {
  background: transparent !important;
}
.chat-input :deep(.n-input__textarea-el:-webkit-autofill),
.chat-input :deep(.n-input__textarea-el:-webkit-autofill:hover),
.chat-input :deep(.n-input__textarea-el:-webkit-autofill:focus) {
  -webkit-box-shadow: 0 0 0 1000px rgba(22, 22, 28, 0.8) inset !important;
  -webkit-text-fill-color: #e4e4e7 !important;
  transition: background-color 5000s ease-in-out 0s;
}
.chat-input :deep(.n-input__placeholder) {
  padding: 8px 4px !important;
  color: #55556b;
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
  background: #2a2a35 !important;
  transition: all 0.25s ease;
  opacity: 0.5;
}
.send-btn.has-content {
  background: linear-gradient(135deg, #6366f1, #4f46e5) !important;
  opacity: 1;
}
.send-btn.has-content:not(:disabled):hover {
  background: linear-gradient(135deg, #818cf8, #6366f1) !important;
  transform: scale(1.08);
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
}
.send-btn:disabled {
  opacity: 0.35;
}

/* 底部栏 */
.input-footer {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 4px;
  padding: 2px 6px 2px;
  border-top: 1px solid rgba(255, 255, 255, 0.03);
  margin-top: 2px;
}
.footer-btn {
  font-size: 11px;
  color: #6b6b80 !important;
  padding: 2px 8px !important;
  border-radius: 8px !important;
  transition: all 0.2s ease;
}
.footer-btn:hover {
  color: #a5b4fc !important;
  background: rgba(99, 102, 241, 0.08) !important;
}
.footer-hint {
  font-size: 10px;
  color: #4a4a5a;
  margin-left: auto;
}
.recording-hint {
  color: #ef4444;
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
.send-btn :deep(.n-button__border) {
  display: none !important;
}
.send-btn :deep(.n-button__state-border) {
  display: none !important;
}
.send-btn:focus {
  outline: none !important;
  box-shadow: none !important;
}
.chat-input :deep(.n-input__textarea-el) {
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  padding: 8px 4px 6px 4px;
  caret-color: #6366f1;
  color: #e4e4e7;
  font-size: 14px;
  line-height: 1.55;
  /* 关键：覆盖 focus 状态的背景 */
  outline: none !important;
  box-shadow: none !important;
}

.chat-input :deep(.n-input__textarea-el:focus) {
  background: transparent !important;
  outline: none !important;
  box-shadow: none !important;
}

/* 覆盖浏览器默认的 focus 高亮 */
.chat-input :deep(.n-input__textarea-el:focus-visible) {
  background: transparent !important;
  outline: none !important;
}
</style>
