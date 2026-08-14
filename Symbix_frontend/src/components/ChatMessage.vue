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
              {{ t('chat.saveAndSend') }}
            </n-button>
            <n-button size="tiny" text @click="cancelEdit" class="cancel-btn">{{ t('chat.cancel') }}</n-button>
          </div>
        </div>
      </template>
      <template v-else>
        <!-- Reasoning (思维过程) — 仅非空内容时展示 -->
        <div v-if="hasReasoning" class="reasoning-block">
          <div class="reasoning-header" @click="toggleReasoning">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
            </svg>
            <span>{{ t('chat.thinkingProcess') }}</span>
            <svg class="reasoning-arrow" :class="{ expanded: showReasoning }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
          </div>
          <div v-show="showReasoning" class="reasoning-text">{{ String(msg.reasoning).trim() }}</div>
        </div>

        <!-- Steps / 工具卡片 — 过滤无效空 step -->
        <div v-if="visibleSteps.length" class="steps-block">
          <div v-for="(step, i) in visibleSteps" :key="step.id || i" class="step-card" :class="step.status">

            <div class="step-header" @click="toggleStep(Number(i))">
              <span class="step-icon">
                <svg v-if="step.status === 'done'" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                <svg v-else-if="step.status === 'running' || step.status === 'pending'" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                <svg v-else-if="step.status === 'awaiting_approval'" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
                <svg v-else-if="step.status === 'rejected'" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
              </span>
              <span class="step-name">{{ formatToolName(step.name) }}</span>
              <span class="step-badge" :class="step.status">{{ statusLabel(step.status) }}</span>
              <svg class="step-expand-arrow" :class="{ expanded: expandedSteps[Number(i)] }" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </div>
            <div v-show="expandedSteps[Number(i)]" class="step-details">
              <div v-if="step.arguments" class="step-detail-row">
                <div class="detail-label">{{ t('chat.param') }}</div>
                <pre class="detail-pre">{{ formatJson(step.arguments) }}</pre>
              </div>
              <div v-if="step.result" class="step-detail-row">
                <div class="detail-label">{{ t('chat.result') }}</div>
                <pre class="detail-pre">{{ truncateResult(step.result) }}</pre>
              </div>
            </div>
          </div>
        </div>

        <!-- 审批按钮 -->
        <div v-if="msg.approval_id" class="approval-block">
          <div class="approval-hint">{{ t('chat.awaitingApproval') }}</div>
          
          <!-- 风险等级显示 -->
          <div v-if="msg.risk_level" class="risk-info">
            <span class="risk-badge" :class="'risk-' + msg.risk_level">
              {{ t('chat.riskLevel' + msg.risk_level.charAt(0).toUpperCase() + msg.risk_level.slice(1)) }}
            </span>
            <span v-if="msg.risk_reason" class="risk-reason">
              {{ t('chat.riskReason') }}: {{ msg.risk_reason }}
            </span>
          </div>
          
          <div class="approval-actions">
            <n-button size="small" type="primary" :loading="msg.approval_pending === true" :disabled="msg.approval_pending === true" @click="emit('approve', true)">{{ t('chat.approve') }}</n-button>
            <n-button size="small" tertiary :disabled="msg.approval_pending === true" @click="emit('approve', false)">{{ t('chat.reject') }}</n-button>
          </div>
        </div>

        <!-- 生成中状态提示 -->
        <div v-if="msg.generating" class="generating-block">
          <svg class="generating-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
          <span class="generating-text">{{ t('chat.generating') }}</span>
        </div>

        <div v-if="hasContent" class="message-bubble" :class="msg.role" ref="bubbleRef">
          <!-- assistant：流式 Markdown；user：纯文本 -->
          <MarkdownRender
            v-if="msg.role === 'assistant'"
            class="msg-markdown"
            mode="chat"
            :content="markdownContent"
            :final="isFinal"
            :max-live-nodes="0"
            :batch-rendering="true"
            :render-batch-size="16"
            :render-batch-delay="8"
            :typewriter="true"
            :fade="false"
            :is-dark="isDark"
          />
          <div v-else class="msg-text">{{ plainContent }}</div>
        </div>


      </template>

      <!-- 操作按钮 (仅 assistant: 复制 & 重试) -->
      <div v-if="msg.role === 'assistant' && !isEditing" class="msg-actions">
        <n-button text size="tiny" @click="copyContent" class="action-btn" :title="t('chat.copy')">
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
        <n-button text size="tiny" @click="retry" class="action-btn" :title="t('chat.retry')">
          <template #icon>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="23 4 23 10 17 10"/>
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
          </template>
        </n-button>
      </div>

      <!-- 操作按钮 (仅 user: 编辑) -->
      <div v-if="msg.role === 'user' && !isEditing" class="msg-actions user-actions">
        <n-button text size="tiny" @click="startEdit" class="action-btn" :title="t('chat.edit')">
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
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import MarkdownRender from 'markstream-vue'
import { useTheme } from '@/composables/useTheme'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  msg: any
  /** 流式是否结束；历史消息默认 true */
  final?: boolean
}>()

const { isDark } = useTheme()

const emit = defineEmits<{
  edit: [newText: string]
  approve: [approved: boolean]
  retry: []
}>()

const copied = ref(false)
const isEditing = ref(false)
const editText = ref('')
const editInputRef = ref<any>(null)
const showReasoning = ref(false)
const expandedSteps = ref<Record<number, boolean>>({})
const bubbleRef = ref<HTMLElement | null>(null)

const { t } = useI18n()

/** 为 Markdown 渲染后的代码块注入"复制"按钮 */
function injectCopyButtons() {
  if (!bubbleRef.value) return
  // 仅处理尚未注入的 pre（用 dataset 属性标记）
  const pres = bubbleRef.value.querySelectorAll('pre:not([data-copy-injected])')
  pres.forEach(el => {
    const pre = el as HTMLElement
    pre.setAttribute('data-copy-injected', '')
    // 给 pre 设置相对定位，作为按钮的定位锚点
    if (!pre.style.position || pre.style.position === 'static') {
      pre.style.position = 'relative'
    }

    const btn = document.createElement('button')
    btn.className = 'code-copy-btn'
    btn.setAttribute('data-copy-state', 'idle')
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
    btn.title = t('chat.copyCode')
    btn.addEventListener('click', async (e) => {
      e.stopPropagation()
      const code = pre.querySelector('code')?.textContent || pre.textContent || ''
      try {
        await navigator.clipboard.writeText(code)
      } catch {
        // fallback
        const ta = document.createElement('textarea')
        ta.value = code
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        document.body.appendChild(ta)
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
      }
      btn.setAttribute('data-copy-state', 'done')
      btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
      setTimeout(() => {
        btn.setAttribute('data-copy-state', 'idle')
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
      }, 2000)
    })
    pre.appendChild(btn)
  })
}

function toggleReasoning() {
  showReasoning.value = !showReasoning.value
}

function toggleStep(i: number) {
  expandedSteps.value[i] = !expandedSteps.value[i]
}

function formatToolName(name: string): string {
  if (!name) return t('chat.toolCall')
  // 去掉 snake_case → 可读中文映射
  const map: Record<string, string> = {
    'create_file': t('chat.toolCreateFile'),
    'read_file': t('chat.toolReadFile'),
    'write_file': t('chat.toolWriteFile'),
    'delete_file': t('chat.toolDeleteFile'),
    'list_files': t('chat.toolListFiles'),
    'execute_command': t('chat.toolExecuteCommand'),
    'search_files': t('chat.toolSearchFiles'),
    'read_multiple_files': t('chat.toolReadMultipleFiles'),
    'java_class_scanner': t('chat.toolJavaClassScanner'),
    'file_structure_scanner': t('chat.toolFileStructureScanner'),
    'batch_code_modifier': t('chat.toolBatchCodeModifier'),
    'code_quality_scanner': t('chat.toolCodeQualityScanner'),
  }
  if (map[name]) return map[name]
  // 通用格式化
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    'done': t('chat.statusDone'),
    'pending': t('chat.statusPending'),
    'running': t('chat.statusRunning'),
    'awaiting_approval': t('chat.statusAwaitingApproval'),
    'rejected': t('chat.statusRejected'),
    'skipped': t('chat.statusSkipped'),
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
  if (!raw) return t('chat.emptyResult')
  if (raw.length > 800) return raw.slice(0, 800) + '\n\n... ' + t('chat.resultTruncated', { count: raw.length })
  return raw
}

function retry() {
  emit('retry')
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

/** 非空白 reasoning 才展示，避免上方空白条 */
const hasReasoning = computed(() => {
  const r = props.msg?.reasoning
  return typeof r === 'string' ? r.trim().length > 0 : !!r
})

/** 过滤掉无 name 的空 step（流式过程中可能短暂出现） */
const visibleSteps = computed(() => {
  const steps = props.msg?.steps
  if (!Array.isArray(steps) || steps.length === 0) return []
  return steps.filter((s: any) => {
    if (!s) return false
    const name = (s.name || '').trim()
    return !!(name || s.arguments || s.result || s.status === 'awaiting_approval')
  })
})

const hasContent = computed(() => {
  const c = props.msg?.content
  return typeof c === 'string' ? c.trim().length > 0 : !!c
})

/** 流结束标记：显式传入优先；历史消息默认已完成 */
const isFinal = computed(() => {
  if (typeof props.final === 'boolean') return props.final
  // 消息自身可带 streaming 标记
  if (props.msg?.streaming === true) return false
  return true
})

const markdownContent = computed(() => {
  const text = String(props.msg?.content ?? '')
  return text.replace(/^\s*\n+/, '').replace(/\n+\s*$/, '')
})

const plainContent = computed(() => String(props.msg?.content ?? ''))

/** Markdown 内容变化后，延迟注入代码块复制按钮 */
watch(markdownContent, () => {
  nextTick(() => {
    // markstream-vue 的 batch 渲染有延迟，多等一帧确保 DOM 就绪
    setTimeout(() => injectCopyButtons(), 50)
  })
})

onMounted(() => {
  nextTick(() => {
    setTimeout(() => injectCopyButtons(), 50)
  })
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
  background: var(--accent-soft);
  color: var(--accent-500, #EF6B6E);
}
.avatar-user {
  background: rgba(247, 168, 91, 0.15);
  color: var(--accent-300, #F7A85B);
}

/* ---- Bubble ---- */
.message-bubble {
  max-width: min(72%, 760px);
  padding: 12px 18px;
  border-radius: var(--radius-md, 8px);
  color: var(--text-primary);
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.65;
  font-size: 14px;
  position: relative;
}
.message-bubble.user {
  background: var(--accent-500, #EF6B6E);
  color: #FFFFFF;
  border-bottom-right-radius: 4px;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.12));
}
.message-bubble.assistant {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}


/* ---- Message Text (user plain) ---- */
.msg-text {
  white-space: pre-wrap;
  word-break: break-word;
}

/* ---- Markdown (assistant via markstream-vue) ---- */
.msg-markdown {
  width: 100%;
  min-width: 0;
  color: inherit;
  font-size: 14px;
  line-height: 1.65;
  word-break: break-word;
  overflow-wrap: anywhere;
}
.msg-markdown :deep(.markstream-vue) {
  color: inherit;
}
.msg-markdown :deep(p) {
  margin: 0.4em 0;
}
.msg-markdown :deep(p:first-child) {
  margin-top: 0;
}
.msg-markdown :deep(p:last-child) {
  margin-bottom: 0;
}
.msg-markdown :deep(h1),
.msg-markdown :deep(h2),
.msg-markdown :deep(h3),
.msg-markdown :deep(h4) {
  margin: 0.75em 0 0.4em;
  line-height: 1.35;
  font-weight: 600;
  color: var(--text-primary);
}
.msg-markdown :deep(h1) { font-size: 1.25em; }
.msg-markdown :deep(h2) { font-size: 1.15em; }
.msg-markdown :deep(h3) { font-size: 1.05em; }
.msg-markdown :deep(ul),
.msg-markdown :deep(ol) {
  margin: 0.4em 0;
  padding-left: 1.35em;
}
.msg-markdown :deep(li) {
  margin: 0.15em 0;
}
.msg-markdown :deep(blockquote) {
  margin: 0.5em 0;
  padding: 0.35em 0.85em;
  border-left: 3px solid var(--accent-border);
  color: var(--text-secondary);
  background: var(--bg-app);
  border-radius: 0 var(--radius-sm, 6px) var(--radius-sm, 6px) 0;
}
.msg-markdown :deep(a) {
  color: var(--accent-500, #EF6B6E);
  text-decoration: none;
}
.msg-markdown :deep(a:hover) {
  text-decoration: underline;
}
.msg-markdown :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: 0.8em 0;
}
.msg-markdown :deep(code) {
  background: var(--accent-soft);
  color: var(--accent-300, #F7A85B);
  padding: 1px 5px;
  border-radius: var(--radius-sm, 6px);
  font-size: 0.9em;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}
.msg-markdown :deep(pre) {
  background: var(--bg-app);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 6px);
  padding: 12px 14px;
  margin: 8px 0;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.55;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}
.msg-markdown :deep(pre code) {
  background: transparent;
  color: var(--text-primary);
  padding: 0;
  border-radius: 0;
  font-size: inherit;
}
.msg-markdown :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.6em 0;
  font-size: 13px;
}
.msg-markdown :deep(th),
.msg-markdown :deep(td) {
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
}
.msg-markdown :deep(th) {
  background: var(--surface-hover);
  font-weight: 600;
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
  color: var(--text-muted) !important;
  padding: 3px 6px !important;
  border-radius: var(--radius-sm, 6px) !important;
}
.action-btn:hover {
  color: var(--text-secondary) !important;
  background: var(--surface-hover) !important;
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
  background: var(--bg-elevated);
  border: 1px solid var(--accent-border);
  border-radius: var(--radius-md, 8px);
  padding: 4px;
}
.edit-input :deep(.n-input__textarea-el) {
  color: var(--text-primary) !important;
  padding: 10px 14px !important;
  font-size: 14px;
  line-height: 1.55;
  caret-color: var(--accent-500, #EF6B6E);
}
.edit-input :deep(.n-input__border),
.edit-input :deep(.n-input__state-border) {
  border-color: var(--accent-border) !important;
}
.edit-input :deep(.n-input__placeholder) {
  color: var(--text-muted) !important;
}

.edit-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
}
.cancel-btn {
  color: var(--text-muted) !important;
  font-size: 12px !important;
}
.cancel-btn:hover {
  color: var(--text-secondary) !important;
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
  color: var(--accent-500, #EF6B6E);
  font-size: 12px;
  padding: 4px 0;
  user-select: none;
  opacity: 0.85;
  transition: opacity var(--duration-fast, 120ms);
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
  color: var(--text-secondary);
  padding: 8px 12px;
  margin-top: 4px;
  background: var(--bg-app);
  border-radius: var(--radius-sm, 6px);
  border-left: 2px solid var(--accent-border);
}

/* ---- Steps Block — Codex 风格紧凑单行 ---- */
.steps-block {
  max-width: min(72%, 760px);
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-family: var(--font-mono, 'JetBrains Mono', 'Consolas', monospace);
}

.step-card {
  border: 0;
  border-radius: 4px;
  background: transparent;
  overflow: hidden;
  transition: background 0.12s ease;
}
.step-card:hover {
  background: rgba(255, 255, 255, 0.03);
}
.step-card.done {
  background: transparent;
}
.step-card.pending, .step-card.running {
  background: transparent;
}
.step-card.awaiting_approval {
  background: rgba(216, 155, 60, 0.06);
}
.step-card.rejected {
  background: rgba(211, 85, 90, 0.05);
}
@keyframes pulse-approval {
  0%, 100% { background: rgba(216, 155, 60, 0.05); }
  50% { background: rgba(216, 155, 60, 0.12); }
}


.step-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  cursor: pointer;
  user-select: none;
  transition: background 0.12s;
  border-radius: 4px;
}
.step-header:hover {
  background: rgba(255, 255, 255, 0.04);
}

.step-icon {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  width: 14px;
  height: 14px;
}
.step-card.done .step-icon { color: var(--success, #4E9A6E); }
.step-card.pending .step-icon, .step-card.running .step-icon { color: var(--accent-500, #EF6B6E); }
.step-card.awaiting_approval .step-icon { color: var(--warning, #D89B3C); }
.step-card.rejected .step-icon { color: var(--error, #D3555A); }

.spin {
  animation: spin 1.2s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

.step-name {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-secondary);
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.step-card.done .step-name { color: var(--text-muted); }
.step-card.running .step-name, .step-card.pending .step-name { color: var(--text-primary); }

.step-badge {
  font-size: 10px;
  padding: 0;
  border-radius: 0;
  line-height: 16px;
  flex-shrink: 0;
  color: var(--text-muted);
  background: transparent;
}
.step-badge.done { color: var(--success, #4E9A6E); background: transparent; }
.step-badge.pending, .step-badge.running { color: var(--accent-500, #EF6B6E); background: transparent; }
.step-badge.awaiting_approval { color: var(--warning, #D89B3C); background: transparent; }
.step-badge.rejected { color: var(--error, #D3555A); background: transparent; }

.step-expand-arrow {
  color: var(--text-muted);
  opacity: 0.4;
  flex-shrink: 0;
  transition: transform var(--duration-base, 180ms) ease, opacity 0.12s;
}
.step-card:hover .step-expand-arrow {
  opacity: 0.8;
}
.step-expand-arrow.expanded {
  transform: rotate(180deg);
}

.step-details {
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  padding: 6px 8px 8px 28px;
  margin-top: 2px;
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
  color: var(--text-muted);
  margin-bottom: 4px;
}
.detail-pre {
  margin: 0;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  overflow-x: auto;
  max-height: 240px;
  overflow-y: auto;
  background: var(--bg-app);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 6px);
  padding: 8px 10px;
}

/* ---- Approval Block ---- */
.approval-block {
  max-width: min(72%, 760px);
  margin-bottom: 8px;
  padding: 12px 14px;
  border-radius: var(--radius-md, 8px);
  border: 1px solid rgba(216, 155, 60, 0.4);
  background: rgba(216, 155, 60, 0.08);
}

/* ---- Generating Block ---- */
.generating-block {
  max-width: min(72%, 760px);
  margin-bottom: 8px;
  padding: 10px 14px;
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--accent-border);
  background: var(--accent-soft);
  display: flex;
  align-items: center;
  gap: 8px;
}

.generating-icon {
  color: var(--accent-500, #EF6B6E);
  flex-shrink: 0;
  animation: spin 1.2s linear infinite;
}

.generating-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.approval-hint {
  font-size: 13px;
  color: var(--warning, #D89B3C);
  margin-bottom: 10px;
  line-height: 1.4;
}

.risk-info {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.risk-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.2;
}

.risk-badge.risk-safe {
  background: rgba(110, 231, 183, 0.15);
  color: #6EE7B7;
  border: 1px solid rgba(110, 231, 183, 0.3);
}

.risk-badge.risk-medium {
  background: rgba(251, 191, 36, 0.15);
  color: #FBBF24;
  border: 1px solid rgba(251, 191, 36, 0.3);
}

.risk-badge.risk-high {
  background: rgba(239, 68, 68, 0.15);
  color: #EF4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.risk-reason {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.approval-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

/* ---- Scrollbar for code blocks ---- */
.msg-markdown :deep(pre::-webkit-scrollbar) {
  height: 4px;
}
.msg-markdown :deep(pre::-webkit-scrollbar-thumb) {
  background: var(--scrollbar);
  border-radius: 2px;
}

/* ---- Code Block Copy Button (injected via JS) ---- */
/* 由于按钮通过 document.createElement 注入，需要用 :global() 作用到 */
:global(.code-copy-btn) {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: var(--radius-sm, 6px);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s ease, background 0.15s ease;
  z-index: 5;
}
:global(pre:hover .code-copy-btn),
:global(pre:focus-within .code-copy-btn) {
  opacity: 1;
}
:global(.code-copy-btn:hover) {
  background: var(--surface-hover);
  color: var(--text-primary);
}
:global(.code-copy-btn[data-copy-state="done"]) {
  color: var(--success, #4E9A6E);
  opacity: 1;
}
</style>
