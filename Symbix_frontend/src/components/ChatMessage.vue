<template>
  <div class="message-row" :class="msg.role">
    <!-- Assistant Avatar -->
    <div v-if="msg.role === 'assistant'" class="avatar avatar-bot">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
        <line x1="9" y1="9" x2="9.01" y2="9"/>
        <line x1="15" y1="9" x2="15.01" y2="9"/>
      </svg>
    </div>

    <div class="message-content" :class="msg.role">
      <!-- 编辑模式 (仅 user) -->
      <template v-if="isEditing">
        <div class="edit-area">
          <n-input
            ref="editInputRef"
            v-model:value="editText"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 5 }"
            @keydown="handleKeydown"
            class="edit-input"
          />
          <div class="edit-actions">
            <n-button size="tiny" type="primary" @click="submitEdit" :disabled="!editText.trim()">
              <template #icon>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13"/>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
              </template>
              保存并发送
            </n-button>
            <n-button size="tiny" text @click="cancelEdit" class="cancel-btn">取消</n-button>
          </div>
        </div>
      </template>
      <template v-else>
        <div class="message-bubble" :class="msg.role">
          <!-- 渲染消息内容：支持简单 Markdown -->
          <div class="msg-text" v-html="renderedContent"></div>
        </div>
      </template>

      <!-- 操作按钮 (仅 assistant: 复制) -->
      <div v-if="msg.role === 'assistant' && !isEditing" class="msg-actions">
        <n-button text size="tiny" @click="copyContent" class="action-btn" title="复制">
          <template #icon>
            <svg v-if="!copied" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </template>
        </n-button>
      </div>

      <!-- 操作按钮 (仅 user: 编辑) -->
      <div v-if="msg.role === 'user' && !isEditing" class="msg-actions user-actions">
        <n-button text size="tiny" @click="startEdit" class="action-btn" title="编辑">
          <template #icon>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
          </template>
        </n-button>
      </div>
    </div>

    <!-- User Avatar -->
    <div v-if="msg.role === 'user'" class="avatar avatar-user">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
        <circle cx="12" cy="7" r="4"/>
      </svg>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'

const props = defineProps<{
  msg: { role: 'user' | 'assistant'; content: string }
}>()

const emit = defineEmits<{
  edit: [newText: string]
}>()

const copied = ref(false)
const isEditing = ref(false)
const editText = ref('')
const editInputRef = ref<any>(null)

function copyContent() {
  navigator.clipboard.writeText(props.msg.content)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

function startEdit() {
  if (props.msg.role !== 'user') return
  editText.value = props.msg.content
  isEditing.value = true
  nextTick(() => {
    editInputRef.value?.focus()
  })
}

function cancelEdit() {
  isEditing.value = false
  editText.value = ''
}

function submitEdit() {
  const trimmed = editText.value.trim()
  if (!trimmed) return
  emit('edit', trimmed)
  isEditing.value = false
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submitEdit()
  } else if (e.key === 'Escape') {
    e.preventDefault()
    cancelEdit()
  }
}

// Simple markdown-like rendering
const renderedContent = computed(() => {
  let text = props.msg.content
  // Escape HTML
  text = text
    .replace(/&/g, '&')
    .replace(/</g, '<')
    .replace(/>/g, '>')

  // Inline code: `code`
  text = text.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')

  // Bold: **text**
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

  // Italic: *text*
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>')

  // Code blocks: ```code```
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre class="code-block"><code>$2</code></pre>')

  // Line breaks
  text = text.replace(/\n/g, '<br>')

  return text
})
</script>

<style scoped>
.message-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  margin: 8px 0;
  animation: msgIn 0.25s ease;
}
@keyframes msgIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.message-row.user {
  justify-content: flex-end;
}

.message-content {
  display: flex;
  flex-direction: column;
}
.message-content.assistant {
  align-items: flex-start;
}
.message-content.user {
  align-items: flex-end;
}

/* ---- Avatar ---- */
.avatar {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-bottom: 2px;
}
.avatar-bot {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(167, 139, 250, 0.1));
  color: #818cf8;
}
.avatar-user {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(79, 70, 229, 0.15));
  color: #c7d2fe;
}

/* ---- Bubble ---- */
.message-bubble {
  max-width: min(72%, 760px);
  padding: 12px 18px;
  border-radius: 18px;
  color: #e5e7eb;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.65;
  font-size: 14px;
  position: relative;
}
.message-bubble.user {
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  border-bottom-right-radius: 6px;
  box-shadow: 0 2px 12px rgba(99, 102, 241, 0.2);
}
.message-bubble.assistant {
  background: rgba(38, 40, 50, 0.7);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.04);
  border-bottom-left-radius: 6px;
}

/* ---- Message Text ---- */
.msg-text {
  white-space: pre-wrap;
}

/* ---- Inline Code ---- */
.msg-text :deep(.inline-code) {
  background: rgba(99, 102, 241, 0.15);
  color: #c7d2fe;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

/* ---- Code Block ---- */
.msg-text :deep(.code-block) {
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  padding: 14px 16px;
  margin: 8px 0;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.55;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}
.msg-text :deep(.code-block code) {
  color: #c7d2fe;
}

/* ---- Actions ---- */
.msg-actions {
  display: flex;
  gap: 4px;
  margin-top: 4px;
  margin-left: 2px;
  opacity: 0;
  transition: opacity 0.2s ease;
}
.message-row:hover .msg-actions {
  opacity: 1;
}
.action-btn {
  color: #6b6b80 !important;
  padding: 3px 6px !important;
  border-radius: 6px !important;
}
.action-btn:hover {
  color: #a0a0b8 !important;
  background: rgba(255, 255, 255, 0.04) !important;
}

/* ---- User Actions (right-aligned) ---- */
.user-actions {
  margin-left: auto;
  margin-right: 2px;
}

/* ---- Edit Area ---- */
.edit-area {
  max-width: min(72%, 760px);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.edit-input {
  background: rgba(30, 30, 40, 0.9);
  border: 1px solid rgba(99, 102, 241, 0.4);
  border-radius: 14px;
  padding: 4px;
}
.edit-input :deep(.n-input__textarea-el) {
  color: #e4e4e7 !important;
  padding: 10px 14px !important;
  font-size: 14px;
  line-height: 1.55;
  caret-color: #6366f1;
}
.edit-input :deep(.n-input__border),
.edit-input :deep(.n-input__state-border) {
  border-color: rgba(99, 102, 241, 0.3) !important;
}
.edit-input :deep(.n-input__placeholder) {
  color: #55556b !important;
}
.edit-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
}
.cancel-btn {
  color: #6b6b80 !important;
  font-size: 12px !important;
}
.cancel-btn:hover {
  color: #a0a0b8 !important;
}

/* ---- Scrollbar for code blocks ---- */
.msg-text :deep(.code-block::-webkit-scrollbar) {
  height: 4px;
}
.msg-text :deep(.code-block::-webkit-scrollbar-thumb) {
  background: rgba(255, 255, 255, 0.08);
  border-radius: 2px;
}
</style>
