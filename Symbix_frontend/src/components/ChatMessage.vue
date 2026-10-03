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
                <svg v-else-if="step.status === 'awaiting_approval'" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 3a2 2 0 0 0-2 2v3H7a2 2 0 0 0-2 2v3l-1 3h16l-1-3v-3a2 2 0 0 0-2-2h-3V5a2 2 0 0 0-2-2z"/>
                  <path d="M5 21h14"/>
                </svg>
                <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
              </span>
              <span class="step-name">
                <span v-if="toolIconSvg(step.name)" class="tool-icon" v-html="toolIconSvg(step.name)"></span>
                {{ formatToolName(step.name) }}
              </span>
              <span class="step-badge" :class="step.status">{{ statusLabel(step.status) }}</span>
              <svg class="step-expand-arrow" :class="{ expanded: expandedSteps[Number(i)] }" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </div>
            <div v-if="step.progress" class="step-progress">
              <span class="step-progress-dot"></span>{{ step.progress }}
            </div>
            <div v-show="expandedSteps[Number(i)]" class="step-details">
              <div v-if="step.arguments" class="step-detail-row">
                <div class="detail-label">{{ t('chat.param') }}</div>
                <pre class="detail-pre">{{ formatJson(step.arguments) }}</pre>
              </div>
              <div v-if="step.result" class="step-detail-row">
                <div class="detail-label">{{ t('chat.result') }}</div>
                <pre class="detail-pre">{{ formatStepResult(step) }}</pre>
              </div>
            </div>
          </div>
        </div>

        <!-- 提问卡:Agent 向用户提问,选项/输入回答后继续。kind=plan 时为待办清单确认卡 -->
        <div v-if="msg.pending_question" class="question-block" :class="{ 'plan-block': msg.pending_question.kind === 'plan' }">
          <div class="question-hint">
            {{ msg.pending_question.kind === 'plan' ? t('chat.planConfirm') : t('chat.agentQuestion') }}
          </div>
          <div class="question-text">{{ msg.pending_question.question }}</div>
          <div v-if="msg.pending_question.context" class="question-context">
            {{ msg.pending_question.context }}
          </div>
          <div v-if="msg.pending_question.suggestions && msg.pending_question.suggestions.length" class="question-suggestions">
            <n-button
              v-for="(s, si) in msg.pending_question.suggestions"
              :key="si"
              size="small"
              tertiary
              :disabled="msg.approval_pending === true"
              class="suggestion-btn"
              @click="emit('answer', s)"
            >
              {{ s }}
            </n-button>
          </div>
          <div class="question-custom">
            <n-input
              v-model:value="answerText"
              :placeholder="msg.pending_question.kind === 'plan' ? t('chat.planAnswerPlaceholder') : t('chat.answerPlaceholder')"
              size="small"
              :disabled="msg.approval_pending === true"
              @keydown.enter.prevent="submitAnswer"
            />
            <n-button
              size="small"
              type="primary"
              :loading="msg.approval_pending === true"
              :disabled="!answerText.trim()"
              @click="submitAnswer"
            >
              {{ t('chat.submitAnswer') }}
            </n-button>
            <n-button
              size="small"
              tertiary
              :disabled="msg.approval_pending === true"
              @click="emit('approve', false)"
            >
              {{ msg.pending_question.kind === 'plan' ? t('chat.planReject') : t('chat.rejectQuestion') }}
            </n-button>
          </div>
        </div>

        <!-- 审批按钮 -->
        <div v-if="msg.approval_id && !msg.pending_question" class="approval-block">
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
  answer: [answer: string]
  retry: []
}>()

const copied = ref(false)
const isEditing = ref(false)
const editText = ref('')
const editInputRef = ref<any>(null)
const showReasoning = ref(false)
const expandedSteps = ref<Record<number, boolean>>({})
const bubbleRef = ref<HTMLElement | null>(null)
const answerText = ref('')

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

/** 提交自定义回答(提问卡)。 */
function submitAnswer() {
  const a = answerText.value.trim()
  if (!a) return
  emit('answer', a)
}

function toggleStep(i: number) {
  expandedSteps.value[i] = !expandedSteps.value[i]
}

// 按工具名分发 SVG 图标（整个 svg 字符串，通过 v-html 注入 span 内）
const TOOL_ICONS: Record<string, string> = {
  // 文件类
  edit_file: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>',
  read_file: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
  list_files: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M3 12h18M3 18h18"/></svg>',
  parse_file: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="12" y2="17"/></svg>',
  create_file: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="12" x2="12" y2="18"/><line x1="9" y1="15" x2="15" y2="15"/></svg>',
  write_file: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>',
  delete_file: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>',
  // 搜索类
  search_files: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
  search_and_replace: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="10" r="6"/><line x1="20" y1="20" x2="15.5" y2="15.5"/><line x1="4" y1="4" x2="8" y2="8"/><line x1="8" y1="4" x2="4" y2="8"/></svg>',
  search_file_with_name: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><path d="M11 8v6M8 11h6"/></svg>',
  // 终端
  open_terminal: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/><rect x="2" y="3" width="20" height="18" rx="2"/></svg>',
  execute_command: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/><rect x="2" y="3" width="20" height="18" rx="2"/></svg>',
  // 桌姄
  emit_pet_action: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>',
  // 交互澄清
  ask_clarifying_question: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
  // 子 Agent 委派(A2A-lite)
  delegate_task: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>',
  // 子 Agent 编队(并行扇出)
  delegate_tasks: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
  check_agent_status: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
  play_status_animation: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3l14 9-14 9z"/></svg>',
  // 技能
  create_skill: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 16.8l-6.2 4.5 2.4-7.4L2 9.4h7.6z"/></svg>',
  // web
  fetch_webpage: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10 15 15 0 0 1 4-10z"/></svg>',
  search_online: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><path d="M11 8a8 8 0 0 1 7 8M3 11a8 8 0 0 1 8 8"/></svg>',
  // MCP 工具常用 icon
  github: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>',
  slack: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 10c-.83 0-1.5-.67-1.5-1.5v-5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5z"/><path d="M20.5 10H19V8.5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/><path d="M9.5 14c.83 0 1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5S8 21.33 8 20.5v-5c0-.83.67-1.5 1.5-1.5z"/><path d="M3.5 14H5v1.5c0 .83-.67 1.5-1.5 1.5S2 16.33 2 15.5 2.67 14 3.5 14z"/><path d="M14 14.5c0-.83.67-1.5 1.5-1.5h5c.83 0 1.5.67 1.5 1.5s-.67 1.5-1.5 1.5h-5c-.83 0-1.5-.67-1.5-1.5z"/><path d="M15.5 19H14v1.5c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5-.67-1.5-1.5-1.5z"/><path d="M10 9.5C10 8.67 9.33 8 8.5 8h-5C2.67 8 2 8.67 2 9.5S2.67 11 3.5 11h5c.83 0 1.5-.67 1.5-1.5z"/><path d="M8.5 5H10V3.5C10 2.67 9.33 2 8.5 2S7 2.67 7 3.5 7.67 5 8.5 5z"/></svg>',
  file: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
  folder: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
  search: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
  globe: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10 15 15 0 0 1 4-10z"/></svg>',
  database: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
}

import { getMcpToolI18n } from '@/utils/mcpToolI18n'

function toolIconSvg(name: string): string | null {
  if (!name) return null
  if (name.startsWith('skill__')) {
    return TOOL_ICONS.create_skill
  }
  // MCP 工具：优先用静态映射表的 icon，否则用通用 fallback
  const mcpI18n = getMcpToolI18n(name)
  if (mcpI18n?.icon) {
    return TOOL_ICONS[mcpI18n.icon] || TOOL_ICONS.fetch_webpage
  }
  return TOOL_ICONS[name] || null
}

function formatToolName(name: string): string {
  if (!name) return t('chat.toolCall')
  const map: Record<string, string> = {
    edit_file: t('chat.toolEditFile'),
    list_files: t('chat.toolListFiles'),
    read_file: t('chat.toolReadFile'),
    parse_file: t('chat.toolParseFile'),
    search_files: t('chat.toolSearchFiles'),
    search_and_replace: t('chat.toolSearchAndReplace'),
    search_file_with_name: t('chat.toolSearchFileWithName'),
    open_terminal: t('chat.toolOpenTerminal'),
    emit_pet_action: t('chat.toolEmitPetAction'),
    check_agent_status: t('chat.toolCheckAgentStatus'),
    play_status_animation: t('chat.toolPlayStatusAnimation'),
    create_skill: t('chat.toolCreateSkill'),
    fetch_webpage: t('chat.toolFetchWebpage'),
    search_online: t('chat.toolSearchOnline'),
    create_file: t('chat.toolCreateFile'),
    write_file: t('chat.toolWriteFile'),
    delete_file: t('chat.toolDeleteFile'),
    execute_command: t('chat.toolExecuteCommand'),
    ask_clarifying_question: t('chat.toolAskClarifyingQuestion'),
    delegate_task: t('chat.toolDelegateTask'),
    delegate_tasks: t('chat.toolDelegateTasks'),
  }
  if (map[name]) return map[name]
  if (name.startsWith('skill__')) return `${t('chat.toolSkill')}: ${name.replace(/^skill__/, '')}`
  // MCP 工具：优先用静态映射表的中文名
  const mcpI18n = getMcpToolI18n(name)
  if (mcpI18n) return mcpI18n.name
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

/** 子 Agent 委派类工具:结果放宽截断阈值,并格式化成缩进 JSON 便于阅读 */
const DELEGATE_TOOLS = ['delegate_task', 'delegate_tasks']
const DELEGATE_RESULT_LIMIT = 4000

function formatStepResult(step: any): string {
  const raw = String(step?.result || '')
  if (!raw) return t('chat.emptyResult')
  if (!DELEGATE_TOOLS.includes(step?.name)) return truncateResult(raw)
  const pretty = formatJson(raw)
  if (pretty.length > DELEGATE_RESULT_LIMIT) {
    return pretty.slice(0, DELEGATE_RESULT_LIMIT) + '\n\n... ' + t('chat.resultTruncated', { count: pretty.length })
  }
  return pretty
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
  max-width: min(78%, 640px);     /* 原本 72%/760, 凑窄 unicode 内容仍造氣 */
  padding: 8px 12px;              /* 原 12 18，减少内边距 */
  border-radius: var(--radius-md, 8px);
  color: var(--text-primary);
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.5;               /* 原 1.65，收紧多行间隙 */
  font-size: 13px;               /* 原 14，微缩信息密度 */
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
  margin: 0.5em 0 0.3em;          /* 原 0.75 0 0.4，更紧凑 */
  line-height: 1.3;
  font-weight: 600;
  color: var(--text-primary);
}
.msg-markdown :deep(h1) { font-size: 1.2em; }  /* 原 1.25 */
.msg-markdown :deep(h2) { font-size: 1.1em; }  /* 原 1.15 */
.msg-markdown :deep(h3) { font-size: 1.0em; }  /* 原 1.05 */
.msg-markdown :deep(ul),
.msg-markdown :deep(ol) {
  margin: 0.25em 0;              /* 原 0.4 */
  padding-left: 1.2em;            /* 原 1.35 */
}
.msg-markdown :deep(li) {
  margin: 0.1em 0;                /* 原 0.15 */
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
  padding: 10px 12px;            /* 原 12 14，代码块更显紧凑 */
  margin: 6px 0;
  overflow-x: auto;             /* 长代码仍可横滑但不拉宽bubble外层 */
  white-space: pre-wrap;        /* 超长行自动换行，避免出现需要拖才能看全 */
  word-break: break-word;
  font-size: 12.5px;             /* 原 13px */
  line-height: 1.5;
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
  width: min(72%, 760px);
  min-width: 200px;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.edit-input {
  width: 100%;
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

/* ---- Steps Block — 紧凑卡片 ---- */
.steps-block {
  max-width: min(72%, 760px);
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.step-card {
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  overflow: hidden;
  transition: border-color var(--duration-base, 180ms) ease;
}
.step-card.done {
  border-color: rgba(78, 154, 110, 0.35);
  background: rgba(78, 154, 110, 0.08);
}
.step-card.pending, .step-card.running {
  border-color: var(--accent-border);
  background: var(--accent-soft);
}
.step-card.awaiting_approval {
  border-color: rgba(216, 155, 60, 0.4);
  background: rgba(216, 155, 60, 0.08);
  animation: pulse-approval 2s infinite;
}
.step-card.rejected {
  border-color: rgba(211, 85, 90, 0.35);
  background: rgba(211, 85, 90, 0.08);
}
@keyframes pulse-approval {
  0%, 100% { border-color: rgba(216, 155, 60, 0.35); }
  50% { border-color: rgba(216, 155, 60, 0.65); }
}


.step-header {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 10px;
  cursor: pointer;
  user-select: none;
  transition: background 0.12s;
}
.step-header:hover {
  background: rgba(255, 255, 255, 0.03);
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
  font-weight: 500;
  color: var(--text-primary);
  flex: 1;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.step-name .tool-icon {
  display: inline-flex;
  flex-shrink: 0;
  color: var(--text-muted, currentColor);
  transition: color var(--duration-base, 180ms) var(--ease-standard, ease);
}
.step-name .tool-icon :deep(svg) {
  display: block;
}
.step-card.done .step-name .tool-icon { 
  color: var(--success, #4E9A6E); 
}
.step-card.running .step-name .tool-icon,
.step-card.pending .step-name .tool-icon { 
  color: var(--accent-500, #EF6B6E); 
}
.step-card.awaiting_approval .step-name .tool-icon { 
  color: var(--warning, #D89B3C); 
}
.step-card.rejected .step-name .tool-icon { 
  color: var(--error, #D3555A); 
}
.step-card.done .step-name { 
  color: var(--text-secondary); 
}
.step-card.running .step-name, .step-card.pending .step-name { 
  color: var(--text-primary); 
}

.step-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px 6px 30px;
  font-size: 11px;
  color: var(--text-muted, currentColor);
}
.step-progress-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent-500, #EF6B6E);
  flex-shrink: 0;
  animation: step-progress-pulse 1.2s ease-in-out infinite;
}
@keyframes step-progress-pulse {
  0%, 100% { opacity: 0.35; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1.15); }
}

.step-badge {
  font-size: 10px;
  padding: 0 5px;
  border-radius: var(--radius-full, 999px);
  line-height: 16px;
  flex-shrink: 0;
  color: var(--text-muted);
  background: var(--surface-hover);
}
.step-badge.done { 
  color: var(--success, #4E9A6E); background: rgba(78, 154, 110, 0.12); 
}
.step-badge.pending, .step-badge.running { 
  color: var(--accent-500, #EF6B6E); background: var(--accent-soft); 
}
.step-badge.awaiting_approval { 
  color: var(--warning, #D89B3C); background: rgba(216, 155, 60, 0.12); 
}
.step-badge.rejected { 
  color: var(--error, #D3555A); background: rgba(211, 85, 90, 0.12); 
}

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
  padding: 8px 10px 10px 28px;
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

/* ---- Question Block (Agent 向用户提问) ---- */
.question-block {
  max-width: min(72%, 760px);
  margin-bottom: 8px;
  padding: 12px 14px;
  border-radius: var(--radius-md, 8px);
  border: 1px solid rgba(87, 155, 252, 0.4);
  background: rgba(87, 155, 252, 0.08);
}

.question-hint {
  font-size: 12px;
  color: var(--accent-500, #579BFC);
  margin-bottom: 6px;
  font-weight: 600;
}

.question-text {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.5;
  margin-bottom: 6px;
}

.question-context {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
  margin-bottom: 8px;
  opacity: 0.9;
  white-space: pre-wrap;
}

/* 待办清单确认卡:换成待办色,清单本身用等宽缩进先得清楚 */
.plan-block {
  border-color: rgba(246, 173, 85, 0.45);
  background: rgba(246, 173, 85, 0.08);
}

.plan-block .question-hint {
  color: var(--warning-500, #F6AD55);
}

.plan-block .question-context {
  font-size: 13px;
  font-family: ui-monospace, Consolas, monospace;
  line-height: 1.7;
  opacity: 1;
}

.question-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.suggestion-btn {
  border-radius: 14px;
}

.question-custom {
  display: flex;
  gap: 6px;
  align-items: center;
}

.question-custom .n-input {
  flex: 1;
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
