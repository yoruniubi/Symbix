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
        <!-- Reasoning (思维过程) -->
        <div v-if="msg.reasoning" class="reasoning-block">
          <div class="reasoning-header" @click="toggleReasoning">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
            </svg>
            <span>思维过程</span>
            <svg class="reasoning-arrow" :class="{ expanded: showReasoning }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
          </div>
          <div v-show="showReasoning" class="reasoning-text">{{ msg.reasoning }}</div>
        </div>

        <!-- Steps / 工具卡片 -->
        <div v-if="msg.steps && msg.steps.length" class="steps-block">
          <div v-for="(step, i) in msg.steps" :key="i" class="step-card" :class="step.status">
            <div class="step-header" @click="toggleStep(Number(i))">
              <span class="step-icon">
                <svg v-if="step.status === 'done'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                <svg v-else-if="step.status === 'running' || step.status === 'pending'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                <svg v-else-if="step.status === 'awaiting_approval'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
                <svg v-else-if="step.status === 'rejected'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
              </span>
              <span class="step-name">{{ formatToolName(step.name) }}</span>
              <span class="step-badge" :class="step.status">{{ statusLabel(step.status) }}</span>
              <svg class="step-expand-arrow" :class="{ expanded: expandedSteps[Number(i)] }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </div>
            <div v-show="expandedSteps[Number(i)]" class="step-details">
              <div v-if="step.arguments" class="step-detail-row">
                <div class="detail-label">参数</div>
                <pre class="detail-pre">{{ formatJson(step.arguments) }}</pre>
              </div>
              <div v-if="step.result" class="step-detail-row">
                <div class="detail-label">结果</div>
                <pre class="detail-pre">{{ truncateResult(step.result) }}</pre>
              </div>
            </div>
          </div>
        </div>

        <!-- 审批按钮 -->
        <div v-if="msg.approval_id" class="approval-block">
          <div class="approval-hint">⚠️ Agent 想执行工具，需要你的审批</div>
          <div class="approval-actions">
            <n-button size="small" type="primary" @click="emit('approve', true)">同意执行</n-button>
            <n-button size="small" tertiary @click="emit('approve', false)">拒绝</n-button>
          </div>
        </div>

        <div v-if="msg.content" class="message-bubble" :class="msg.role">
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
  msg: any
}>()

const emit = defineEmits<{
  edit: [newText: string]
  approve: [approved: boolean]
}>()

const copied = ref(false)
const isEditing = ref(false)
const editText = ref('')
const editInputRef = ref<any>(null)
const showReasoning = ref(false)
const expandedSteps = ref<Record<number, boolean>>({})

function toggleReasoning() {
  showReasoning.value = !showReasoning.value
}

function toggleStep(i: number) {
  expandedSteps.value[i] = !expandedSteps.value[i]
}

function formatToolName(name: string): string {
  if (!name) return '工具调用'
  // 去掉 snake_case → 可读中文映射
  const map: Record<string, string> = {
    'create_file': '📄 创建文件',
    'read_file': '📖 读取文件',
    'write_file': '✏️ 写入文件',
    'delete_file': '🗑️ 删除文件',
    'list_files': '📂 列出目录',
    'execute_command': '⚡ 执行命令',
    'search_files': '🔍 搜索文件',
    'read_multiple_files': '📚 批量读取',
    'java_class_scanner': '☕ 扫描 Java 类',
    'file_structure_scanner': '🏗️ 扫描文件结构',
    'batch_code_modifier': '🔧 批量修改代码',
    'code_quality_scanner': '✅ 代码质量扫描',
  }
  if (map[name]) return map[name]
  // 通用格式化
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    'done': '✓ 完成',
    'pending': '⏳ 执行中',
    'running': '⏳ 执行中',
    'awaiting_approval': '⚠️ 待审批',
    'rejected': '✗ 已拒绝',
    'skipped': '⊘ 已跳过',
  }
  return map[status] || status
}

function formatJson(raw: string): string {
  try {
    const obj = JSON.parse(raw)
    return JSON.stringify(obj, null, 2)
  } catch {
    return raw
  }
}

function truncateResult(raw: string): string {
  if (!raw) return '(空)'
  if (raw.length > 800) return raw.slice(0, 800) + '\n\n... (结果已截断，共 ' + raw.length + ' 字符)'
  return raw
}

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
  font-size: 13px;
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

/* ---- Reasoning Block ---- */
.reasoning-block {
  max-width: min(72%, 760px);
  margin-bottom: 8px;
}

.reasoning-header {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #818cf8;
  font-size: 12px;
  padding: 4px 0;
  user-select: none;
  opacity: 0.8;
  transition: opacity 0.2s;
}

.reasoning-header:hover {
  opacity: 1;
}

.reasoning-header .reasoning-arrow {
  transition: transform 0.2s ease;
}

.reasoning-header .reasoning-arrow.expanded {
  transform: rotate(180deg);
}

.reasoning-text {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
  font-size: 12px;
  color: #8b8ba0;
  padding: 8px 12px;
  margin-top: 4px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  border-left: 2px solid rgba(99, 102, 241, 0.3);
}

/* ---- Steps Block ---- */
.steps-block {
  max-width: min(72%, 760px);
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.step-card {
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(20, 22, 30, 0.7);
  backdrop-filter: blur(6px);
  overflow: hidden;
  transition: border-color 0.2s ease;
}
.step-card.done {
  border-color: rgba(34, 197, 94, 0.25);
  background: rgba(34, 197, 94, 0.05);
}
.step-card.pending, .step-card.running {
  border-color: rgba(99, 102, 241, 0.3);
  background: rgba(99, 102, 241, 0.06);
}
.step-card.awaiting_approval {
  border-color: rgba(234, 179, 8, 0.3);
  background: rgba(234, 179, 8, 0.06);
  animation: pulse-approval 2s infinite;
}
.step-card.rejected {
  border-color: rgba(239, 68, 68, 0.25);
  background: rgba(239, 68, 68, 0.05);
}
@keyframes pulse-approval {
  0%, 100% { border-color: rgba(234, 179, 8, 0.3); }
  50% { border-color: rgba(234, 179, 8, 0.6); }
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}
.step-header:hover {
  background: rgba(255, 255, 255, 0.03);
}

.step-icon {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  width: 20px;
  height: 20px;
}
.step-card.done .step-icon { color: #22c55e; }
.step-card.pending .step-icon, .step-card.running .step-icon { color: #818cf8; }
.step-card.awaiting_approval .step-icon { color: #facc15; }
.step-card.rejected .step-icon { color: #ef4444; }

.spin {
  animation: spin 1.2s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

.step-name {
  font-size: 13px;
  font-weight: 500;
  color: #d0d0da;
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.step-badge {
  font-size: 11px;
  padding: 0 6px;
  border-radius: 10px;
  line-height: 20px;
  flex-shrink: 0;
  color: #8b8ba0;
  background: rgba(255, 255, 255, 0.06);
}
.step-badge.done { color: #22c55e; background: rgba(34, 197, 94, 0.1); }
.step-badge.pending, .step-badge.running { color: #818cf8; background: rgba(99, 102, 241, 0.12); }
.step-badge.awaiting_approval { color: #facc15; background: rgba(234, 179, 8, 0.1); }
.step-badge.rejected { color: #ef4444; background: rgba(239, 68, 68, 0.1); }

.step-expand-arrow {
  color: #6b6b80;
  flex-shrink: 0;
  transition: transform 0.2s ease;
}
.step-expand-arrow.expanded {
  transform: rotate(180deg);
}

.step-details {
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  padding: 10px 12px;
}

.step-detail-row {
  margin-bottom: 8px;
}
.step-detail-row:last-child {
  margin-bottom: 0;
}

.detail-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #6b6b80;
  margin-bottom: 4px;
}

.detail-pre {
  margin: 0;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 11px;
  line-height: 1.5;
  color: #b0b0c0;
  white-space: pre-wrap;
  word-break: break-all;
  overflow-x: auto;
  max-height: 240px;
  overflow-y: auto;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 6px;
  padding: 8px 10px;
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
