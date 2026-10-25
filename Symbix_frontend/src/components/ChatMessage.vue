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

        <!-- pet-forge 预览:Agent 写一次 base.svg 就刷新一次,方便直观看到形象 -->
        <div v-if="rigPath && !rigMissing" class="rig-preview">
          <div class="rig-preview-head">
            <span class="rig-preview-title">{{ t('chat.rigPreview') }}</span>
            <span v-if="rigName" class="rig-preview-name">{{ rigName }}</span>
          </div>
          <div class="rig-preview-body">
            <img v-if="rigUrl" class="rig-preview-img" :src="rigUrl" :alt="rigName || 'base.svg'" />
            <div v-else-if="rigLoading" class="rig-preview-hint">
              {{ t('chat.rigPreviewLoading') }}
            </div>
          </div>
          <div class="rig-preview-path" :title="rigPath">{{ rigPath }}</div>
        </div>

        <!-- MCP 图片预览:pixeldraw 这类绘图工具的返回图,直接看效果 -->
        <div v-if="mcpImgPath" class="rig-preview">
          <div class="rig-preview-head">
            <span class="rig-preview-title">{{ t('chat.mcpImagePreview') }}</span>
          </div>
          <div class="rig-preview-body">
            <img v-if="mcpImgUrl" class="rig-preview-img" :src="mcpImgUrl" :alt="t('chat.mcpImagePreview')" />
            <div v-else-if="mcpImgLoading" class="rig-preview-hint">
              {{ t('chat.mcpImageLoading') }}
            </div>
          </div>
        </div>

        <!-- 提问卡:Agent 向用户提问,选项/输入回答后继续。kind=plan 时为待办清单确认卡 -->
        <div v-if="msg.pending_question" class="question-block"
          :class="{ 'plan-block': msg.pending_question.kind === 'plan', 'question-block-expired': msg.approval_expired === true }">
          <div class="question-hint">
            {{ msg.approval_expired ? t('chat.questionExpired') : (msg.pending_question.kind === 'plan' ? t('chat.planConfirm') : t('chat.agentQuestion')) }}
          </div>
          <div class="question-text">{{ msg.pending_question.question }}</div>
          <div v-if="msg.pending_question.context" class="question-context">
            {{ msg.pending_question.context }}
          </div>
          <div v-if="questionOptions.length" class="question-options">
            <div
              v-for="(opt, oi) in questionOptions"
              :key="oi"
              class="q-option"
              :class="{ 'q-option-picked': pickedOption === oi, 'q-option-disabled': msg.approval_pending === true || msg.approval_expired === true }"
              @click="pickOption(opt, oi)"
            >
              <span class="q-option-idx">{{ oi + 1 }}.</span>
              <div class="q-option-body">
                <div class="q-option-label">{{ opt.label }}</div>
                <div v-if="opt.description" class="q-option-desc">{{ opt.description }}</div>
              </div>
            </div>
          </div>
          <div class="question-custom">
            <n-input
              ref="answerInputRef"
              v-model:value="answerText"
              :placeholder="msg.pending_question.kind === 'plan' ? t('chat.planAnswerPlaceholder') : t('chat.answerPlaceholder')"
              size="small"
              :disabled="msg.approval_pending === true || msg.approval_expired === true"
              @keydown.enter.prevent="submitAnswer"
            />
            <n-button
              size="small"
              type="primary"
              :loading="msg.approval_pending === true"
              :disabled="!answerText.trim() || msg.approval_expired === true"
              @click="submitAnswer"
            >
              {{ t('chat.submitAnswer') }}
            </n-button>
            <n-button
              size="small"
              tertiary
              :disabled="msg.approval_pending === true || msg.approval_expired === true"
              @click="emit('approve', false)"
            >
              {{ msg.pending_question.kind === 'plan' ? t('chat.planReject') : t('chat.rejectQuestion') }}
            </n-button>
          </div>
          <div v-if="msg.approval_expired" class="question-expired-note">{{ t('chat.approvalExpiredNote') }}</div>
          <div v-else-if="questionOptions.length" class="question-foot">
            {{ msg.pending_question.kind === 'plan' ? t('chat.planPickHint') : t('chat.questionPickHint') }}
          </div>
        </div>

        <!-- 审批按钮;审批态已失效(后端重启/挂起态被清理)时只展示原因,不再给可点的按钮 -->
        <div v-if="(msg.approval_id || msg.approval_expired) && !msg.pending_question" class="approval-block"
          :class="{ 'approval-block-expired': msg.approval_expired === true }">
          <div class="approval-hint">{{ msg.approval_expired ? t('chat.approvalExpired') : t('chat.awaitingApproval') }}</div>
          
          <!-- 风险等级显示 -->
          <div v-if="msg.risk_level" class="risk-info">
            <span class="risk-badge" :class="'risk-' + msg.risk_level">
              {{ t('chat.riskLevel' + msg.risk_level.charAt(0).toUpperCase() + msg.risk_level.slice(1)) }}
            </span>
            <span v-if="msg.risk_reason" class="risk-reason">
              {{ t('chat.riskReason') }}: {{ msg.risk_reason }}
            </span>
          </div>
          
          <div v-if="msg.approval_expired" class="approval-expired-note">{{ t('chat.approvalExpiredNote') }}</div>
          <div v-else class="approval-actions">
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

        <!-- 上游中断重试提示:后端发 content_reset 时带上原因;重试吐出内容后由 delta/done 清掉 -->
        <div v-if="msg.retryHint" class="retry-hint">
          <svg class="retry-hint-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          <span>{{ t('chat.retrying') }}</span>
          <span class="retry-hint-reason">{{ msg.retryHint }}</span>
        </div>

        <!-- 主动搭话开场气泡:不是对用户的回复,加角标区分 -->
        <div v-if="msg.proactive" class="act-mode-row">
          <span class="act-mode-badge proactive">{{ t('chat.proactiveBadge') }}</span>
        </div>

        <!-- 执行模式角标:后端自动判决的 act_mode(reactive / plan_solve) -->
        <div v-if="actModeLabel" class="act-mode-row">
          <span class="act-mode-badge" :class="msg.act_mode" :title="actModeTip">{{ actModeLabel }}</span>
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
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import MarkdownRender from 'markstream-vue'
import { useTheme } from '@/composables/useTheme'
import { useI18n } from 'vue-i18n'
import { BACKEND_URL } from '@/utils/backend'
import { pickPreviewRigPath, rigFolderName } from '@/utils/petRig'
import { toolIconSvg } from '@/utils/toolIcons'
import { getMcpToolI18n } from '@/utils/mcpToolI18n'

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
const answerInputRef = ref<any>(null)
/** 被选中的选项下标(仅 action=fill 时高亮,提示用户接着改/发) */
const pickedOption = ref(-1)

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

/** 提问卡换了一条待回答消息时清掉上一条的输入与选中态 */
watch(
  () => props.msg?.pending_question?.question,
  () => {
    answerText.value = ''
    pickedOption.value = -1
  },
)

/** 提交自定义回答(提问卡)。 */
function submitAnswer() {
  if (props.msg?.approval_expired === true) return
  const a = answerText.value.trim()
  if (!a) return
  emit('answer', a)
}

/** 执行模式角标:后端自动判决的 act_mode(reactive / plan_solve);历史消息没有该字段则不显示 */
const actModeLabel = computed(() => {
  if (props.msg?.act_mode === 'plan_solve') return t('chat.actModePlan')
  if (props.msg?.act_mode === 'reactive') return t('chat.actModeReactive')
  return ''
})
const actModeTip = computed(() => {
  if (props.msg?.act_mode === 'plan_solve') return t('chat.actModePlanTip')
  if (props.msg?.act_mode === 'reactive') return t('chat.actModeReactiveTip')
  return ''
})

/**
 * pet-forge 预览:取本轮**写出的** base.svg(详见 utils/petRig.ts 的 pickPreviewRigPath)。
 * 读模板 / 列目录 / 调 skill 都会在参数里带 base.svg,但那些不是「生成完成」,
 * 过去会让预览卡从一开始就挂着 skill 自带的模板图,容易被误认为用户的桌宠。
 */
const rigPath = computed(() => pickPreviewRigPath(props.msg?.steps))
const rigName = computed(() => rigFolderName(rigPath.value))
/** 最后一步的状态:落 done 往往意味着一批文件刚写完,值得重读一次 base.svg */
const lastStepStatus = computed(() => {
  const steps: any[] = props.msg?.steps || []
  return steps.length ? steps[steps.length - 1]?.status || '' : ''
})

const rigUrl = ref('')
const rigLoading = ref(false)
/** 读不到(路径根本不存在 / 后端 404)时:卡片静默隐藏,不再补一句「读取失败」占着位置 */
const rigMissing = ref(false)
/** 路径 → 上次失败时间:一轮 pet-forge 里步骤状态会变好几次,不节流就会把同一个 404 刷满后端日志 */
const rigFailAt = new Map<string, number>()
const RIG_RETRY_MS = 5000
/** 已渲染进 <img> 的 SVG 文本:内容没变就不重建 Blob URL,避免闪烁 */
let rigText = ''
/** 在途请求令牌:只认最后一次结果,防止旧请求覆盖新预览 */
let rigToken = 0

function releaseRig() {
  rigText = ''
  if (rigUrl.value) {
    URL.revokeObjectURL(rigUrl.value)
    rigUrl.value = ''
  }
}

/** 读 base.svg 文本 → Blob URL(SVG 走 <img> 而不是 v-html,避免脚本注入);文件没写出来时静默隐藏 */
async function loadRig(path: string) {
  if (!path) {
    rigToken++
    releaseRig()
    rigLoading.value = false
    rigMissing.value = false
    return
  }
  const failedAt = rigFailAt.get(path)
  if (failedAt && Date.now() - failedAt < RIG_RETRY_MS) {
    // 刚失败过:静默藏着,别再去打扰后端(下次步骤状态变化时再试)
    rigMissing.value = true
    return
  }
  const token = ++rigToken
  rigLoading.value = true
  try {
    const res = await fetch(`${BACKEND_URL}/api/files/read?path=${encodeURIComponent(path)}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    const text = typeof data?.content === 'string' ? data.content : ''
    if (token !== rigToken) return
    if (text && text !== rigText) {
      rigText = text
      const next = URL.createObjectURL(new Blob([text], { type: 'image/svg+xml' }))
      if (rigUrl.value) URL.revokeObjectURL(rigUrl.value)
      rigUrl.value = next
    }
    rigFailAt.delete(path)
    rigMissing.value = false
  } catch {
    if (token === rigToken) {
      releaseRig()
      rigMissing.value = true
    }
    rigFailAt.set(path, Date.now())
  } finally {
    if (token === rigToken) rigLoading.value = false
  }
}

// 路径变了 / 步骤数变了 / 最后一步落状态(文件刚写完)都重读一次
watch(
  [rigPath, () => (props.msg?.steps || []).length, lastStepStatus],
  () => { void loadRig(rigPath.value) },
  { immediate: true },
)

// ---- MCP 图片预览 ----
// 工具输出里的 `[Image saved: <绝对路径>]`:connector 把 MCP 返回的图片内容(pixeldraw
// 这类绘图工具每次都返回 8x 预览 PNG)落盘后打的标记。从「完成」步骤里倒序找最新一张,
// 经 /api/files/raw 拉字节渲染 —— 草稿迭代时每画一笔都能直接看到当前画面。
const mcpImgPath = computed(() => {
  const steps = props.msg?.steps || []
  for (let i = steps.length - 1; i >= 0; i--) {
    const st: any = steps[i]
    if (st?.status !== 'done') continue
    const m = /\[Image saved: ([^\]\r\n]+?)\]/.exec(String(st.result || ''))
    if (m) return m[1].trim()
  }
  return ''
})
const mcpImgUrl = ref('')
const mcpImgLoading = ref(false)
let mcpImgToken = 0

function releaseMcpImg() {
  if (mcpImgUrl.value) {
    URL.revokeObjectURL(mcpImgUrl.value)
    mcpImgUrl.value = ''
  }
}

async function loadMcpImg(path: string) {
  const token = ++mcpImgToken
  if (!path) {
    releaseMcpImg()
    mcpImgLoading.value = false
    return
  }
  mcpImgLoading.value = true
  try {
    const res = await fetch(`${BACKEND_URL}/api/files/raw?path=${encodeURIComponent(path)}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    if (token !== mcpImgToken) return
    const next = URL.createObjectURL(blob)
    if (mcpImgUrl.value) URL.revokeObjectURL(mcpImgUrl.value)
    mcpImgUrl.value = next
  } catch {
    // 读取失败就静默不显示(路径被清理/后端重启都是正常情况)
    if (token === mcpImgToken) releaseMcpImg()
  } finally {
    if (token === mcpImgToken) mcpImgLoading.value = false
  }
}

watch(mcpImgPath, (p) => { void loadMcpImg(p) }, { immediate: true })

onUnmounted(() => {
  rigToken++
  releaseRig()
  mcpImgToken++
  releaseMcpImg()
})

/** 提问卡选项:优先用后端给的 options(带描述/动作),旧消息回退到 suggestions 纯文本。 */
// 显式声明返回类型:否则 v-for 的索引会被推成 string | number,oi + 1 与 pickOption(…, oi) 都会报类型错
const questionOptions = computed<{ label: string; description?: string; action?: string }[]>(() => {
  const q = props.msg?.pending_question
  if (!q) return []
  const opts = Array.isArray(q.options) ? q.options : []
  const list = opts.length
    ? opts
    : (Array.isArray(q.suggestions) ? q.suggestions : []).map((s: string) => ({ label: s, description: '', action: '' }))
  return list.filter((o: any) => o && o.label)
})

/** 点选项分流:reject=直接拒绝 / fill=填进输入框待改写 / 其余=直接提交答案。 */
function pickOption(opt: { label: string; action?: string }, index: number) {
  if (props.msg?.approval_pending === true || props.msg?.approval_expired === true) return
  const action = opt.action || ''
  if (action === 'reject') {
    emit('approve', false)
    return
  }
  if (action === 'fill') {
    pickedOption.value = index
    answerText.value = opt.label
    answerInputRef.value?.focus?.()
    return
  }
  emit('answer', opt.label)
}

function toggleStep(i: number) {
  expandedSteps.value[i] = !expandedSteps.value[i]
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
    propose_plan: t('chat.toolProposePlan'),
    create_schedule_job: t('chat.toolCreateScheduleJob'),
    list_schedule_jobs: t('chat.toolListScheduleJobs'),
    cancel_schedule_job: t('chat.toolCancelScheduleJob'),
    save_memory: t('chat.toolSaveMemory'),
    search_memories: t('chat.toolSearchMemories'),
    doc_to_markdown: t('chat.toolDocToMarkdown'),
    doc_to_markdown_file: t('chat.toolDocToMarkdownFile'),
    md_to_docx: t('chat.toolMdToDocx'),
    md_to_xlsx: t('chat.toolMdToXlsx'),
    md_to_pptx: t('chat.toolMdToPptx'),
    md_to_pdf: t('chat.toolMdToPdf'),
    download_file: t('chat.toolDownloadFile'),
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
  min-width: 0;              /* 窄窗口下整行必须能收缩,否则长内容会把聊天区撑出横向滚动条 */
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
  min-width: 0;              /* flex 子项默认 min-width:auto,不放开就压不下去 */
  max-width: 100%;           /* 子元素里的百分比 max-width 才有意义 */
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
  min-width: 0;
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
/* 图片/媒体必须有宽度上限:markdown 里的原图动辄 1024px,没有任何约束时会把
   bubble 撑到 max-width 上限,缩小窗口就直接溢出(真实浏览器实测:气泡右侧溢出 351px、消息列表横滚 765px)。 */
.msg-markdown :deep(img),
.msg-markdown :deep(video),
.msg-markdown :deep(iframe),
.msg-markdown :deep(canvas) {
  max-width: 100%;
  height: auto;
}
/* 行间公式/图表可能比窗口还宽,让它们自己横滑而不是撑破气泡 */
.msg-markdown :deep(.katex-display) {
  max-width: 100%;
  overflow-x: auto;
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

/* ---- 执行模式角标(默认淡显,悬停更亮) ---- */
.act-mode-row {
  display: flex;
  margin-top: 4px;
  margin-left: 2px;
}
.act-mode-badge {
  font-size: 11px;
  line-height: 16px;
  padding: 0 6px;
  border-radius: 999px;
  border: 1px solid var(--border);
  color: var(--text-muted);
  opacity: 0.85;
  cursor: default;
}
.act-mode-badge.proactive {
  border-color: rgba(233, 150, 199, 0.5);
  background: rgba(233, 150, 199, 0.1);
}
.act-mode-badge.plan_solve {
  border-color: rgba(246, 173, 85, 0.45);
  background: rgba(246, 173, 85, 0.08);
  color: var(--warning-500, #F6AD55);
  opacity: 1;
}
.act-mode-row:hover .act-mode-badge {
  opacity: 1;
}

/* ---- pet-forge 预览卡 ---- */
.rig-preview {
  width: min(72%, 760px);
  max-width: 100%;
  margin-bottom: 8px;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  padding: 8px 10px;
}
.rig-preview-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.rig-preview-title {
  font-size: 12px;
  color: var(--text-secondary);
}
.rig-preview-name {
  font-size: 11px;
  line-height: 16px;
  padding: 0 6px;
  border-radius: 999px;
  border: 1px solid var(--accent-border);
  color: var(--accent-500, #EF6B6E);
}
.rig-preview-body {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 96px;
  background: var(--bg-surface);
  border-radius: var(--radius-sm, 6px);
}
.rig-preview-img {
  max-height: 180px;
  max-width: 100%;
  object-fit: contain;
}
.rig-preview-hint {
  font-size: 12px;
  color: var(--text-muted);
  padding: 24px 0;
}
.rig-preview-path {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
/* 自动高度由隐藏的 mirror 量出来:文本域 / mirror / 占位符的字号、行高、内边距必须一致,
   否则 mirror 量出的高度偏小 → 文字被裁、光标与占位符错位 */
.edit-input :deep(.n-input__textarea-el),
.edit-input :deep(.n-input__textarea-mirror),
.edit-input :deep(.n-input__placeholder) {
  padding: 10px 14px !important;
  font-size: 14px;
  line-height: 1.55;
}
.edit-input :deep(.n-input__textarea-el) {
  color: var(--text-primary) !important;
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

/* 选项清单(pi 风格):编号 + 标签 + 可选描述,点一下即回答 */
.question-options {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}

.q-option {
  display: flex;
  gap: 6px;
  padding: 5px 8px;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.q-option:hover {
  background: rgba(87, 155, 252, 0.12);
  border-color: rgba(87, 155, 252, 0.35);
}

.plan-block .q-option:hover {
  background: rgba(246, 173, 85, 0.14);
  border-color: rgba(246, 173, 85, 0.4);
}

.q-option-picked {
  background: rgba(87, 155, 252, 0.16);
  border-color: rgba(87, 155, 252, 0.45);
}

.q-option-disabled {
  opacity: 0.5;
  pointer-events: none;
}

.q-option-idx {
  font-size: 12px;
  line-height: 1.5;
  min-width: 16px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.q-option-body {
  flex: 1;
  min-width: 0;
}

.q-option-label {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary);
}

.q-option-desc {
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-secondary);
  opacity: 0.85;
  margin-top: 1px;
}

.question-foot {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-secondary);
  opacity: 0.75;
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

/* 上游中断重试中的行内提示(不抢眼,但能解释「内容怎么突然没了」) */
.retry-hint {
  max-width: min(72%, 760px);
  margin-top: 4px;
  padding: 6px 10px;
  border-radius: var(--radius-md, 8px);
  border: 1px dashed var(--accent-border);
  background: var(--accent-soft);
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.retry-hint-icon {
  color: var(--accent-500, #EF6B6E);
  flex-shrink: 0;
  animation: spin 1.2s linear infinite;
}

.retry-hint-reason {
  opacity: 0.7;
  font-size: 11px;
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

/* 审批/提问已失效:只留一行说明,不给可点的按钮 */
.approval-expired-note,
.question-expired-note {
  margin-top: 6px;
  padding: 6px 10px;
  border-radius: var(--radius-sm, 6px);
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
  background: rgba(127, 127, 127, 0.1);
  border: 1px dashed rgba(127, 127, 127, 0.35);
}

.approval-block-expired,
.question-block-expired {
  opacity: 0.85;
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
