<template>
  <transition name="panel-slide">
    <div v-if="activePanel === 'jobs'" class="side-panel" :class="{ 'is-resizing': isResizing }" :style="{ width: `${panelWidth}px` }">
      <div class="panel-resize-handle" :title="$t('common.pullToResize')" @mousedown="startResize" />
      <div class="side-panel-header">
        <span class="side-panel-title">{{ $t('jobPanel.title') }}</span>
        <div class="side-panel-actions">
          <n-button size="medium" type="primary" class="add-entry-btn" @click="startCreate">
            <template #icon>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </template>
            {{ $t('jobPanel.add') }}
          </n-button>
          <n-button quaternary size="tiny" class="panel-icon-btn" :title="$t('common.refresh')" @click="loadJobs">
            <svg :class="['refresh-icon', { spinning: loading }]" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
          </n-button>
          <n-button quaternary size="tiny" class="panel-icon-btn close-btn" :title="$t('common.close')" @click="emit('update:activePanel', null)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </n-button>
        </div>
      </div>
      <div class="side-panel-body">
        <div v-if="editing" class="job-form">
          <div class="job-field"><span>{{ $t('jobPanel.name') }}</span><n-input v-model:value="form.name" size="small" /></div>
          <div class="job-field"><span>{{ $t('jobPanel.prompt') }}</span><n-input v-model:value="form.prompt" type="textarea" :rows="4" size="small" /></div>

          <!-- 一句话填时间:交给后端 humanize 解析,省得用户自己拼 cron -->
          <div class="job-field">
            <span>{{ $t('jobPanel.naturalInput') }}</span>
            <div class="job-natural">
              <n-input v-model:value="naturalText" size="small" :placeholder="$t('jobPanel.naturalPlaceholder')" @keyup.enter="applyNatural" />
              <n-button size="small" :loading="naturalLoading" @click="applyNatural">{{ $t('jobPanel.naturalApply') }}</n-button>
            </div>
          </div>

          <div class="job-field"><span>{{ $t('jobPanel.freq') }}</span><n-select v-model:value="mode" size="small" :options="modeOptions" /></div>

          <!-- 每隔 N 分钟/小时/天/周 -->
          <div v-if="mode === 'interval'" class="job-field">
            <span>{{ $t('jobPanel.freqInterval') }}</span>
            <div class="job-inline">
              <n-input-number v-model:value="intervalCount" size="small" :min="1" :max="999" style="width:84px" />
              <n-select v-model:value="intervalUnit" size="small" :options="intervalUnitOptions" style="flex:1" />
            </div>
          </div>

          <!-- 每天 HH:mm -->
          <div v-if="mode === 'daily'" class="job-field">
            <span>{{ $t('jobPanel.atTime') }}</span>
            <n-time-picker v-model:formatted-value="dailyTime" size="small" format="HH:mm" value-format="HH:mm" style="width:100%" />
          </div>

          <!-- 每周 + 时间 -->
          <template v-if="mode === 'weekly'">
            <div class="job-field">
              <div class="job-label-row">
                <span>{{ $t('jobPanel.weekdays') }}</span>
                <div class="job-quick">
                  <button type="button" class="link-btn" @click="weeklyDays = [0, 1, 2, 3, 4]">{{ $t('jobPanel.weekdayWorkdays') }}</button>
                  <button type="button" class="link-btn" @click="weeklyDays = [5, 6]">{{ $t('jobPanel.weekdayWeekend') }}</button>
                </div>
              </div>
              <n-checkbox-group v-model:value="weeklyDays" size="small">
                <div class="job-weekdays">
                  <n-checkbox v-for="d in 7" :key="d" :value="d - 1" :label="weekdayShort(d - 1)" />
                </div>
              </n-checkbox-group>
            </div>
            <div class="job-field">
              <span>{{ $t('jobPanel.atTime') }}</span>
              <n-time-picker v-model:formatted-value="weeklyTime" size="small" format="HH:mm" value-format="HH:mm" style="width:100%" />
            </div>
          </template>

          <!-- 每月 X 号 / 最后一天 + 时间 -->
          <template v-if="mode === 'monthly'">
            <div class="job-field">
              <div class="job-label-row">
                <span>{{ $t('jobPanel.monthlyDay') }}</span>
                <div class="job-quick">
                  <n-switch v-model:value="monthlyLast" size="small" />
                  <span class="quick-text">{{ $t('jobPanel.monthlyLastDay') }}</span>
                </div>
              </div>
              <n-input-number v-if="!monthlyLast" v-model:value="monthlyDay" size="small" :min="1" :max="31" style="width:100%" />
            </div>
            <div class="job-field">
              <span>{{ $t('jobPanel.atTime') }}</span>
              <n-time-picker v-model:formatted-value="monthlyTime" size="small" format="HH:mm" value-format="HH:mm" style="width:100%" />
            </div>
          </template>

          <!-- 只运行一次 -->
          <div v-if="mode === 'once'" class="job-field">
            <span>{{ $t('jobPanel.onceAt') }}</span>
            <n-date-picker
              v-model:formatted-value="onceAt"
              type="datetime"
              size="small"
              clearable
              format="yyyy-MM-dd HH:mm"
              value-format="yyyy-MM-dd'T'HH:mm:ss"
              style="width:100%"
            />
          </div>

          <!-- 高级:Cron -->
          <div v-if="mode === 'cron'" class="job-field">
            <span>{{ $t('jobPanel.cronExpression') }}</span>
            <n-input v-model:value="cronText" size="small" placeholder="0 9 * * 1-5" />
            <div class="job-hint">{{ $t('jobPanel.cronHint') }}</div>
          </div>

          <!-- 实时预览:人话回显 + 接下来 3 次运行时间 -->
          <div class="job-preview" :class="{ 'is-error': !!previewError }">
            <span class="job-preview-key">{{ $t('jobPanel.preview') }}</span>
            <span v-if="previewError" class="job-preview-error">{{ $t('jobPanel.previewInvalid', { msg: previewError }) }}</span>
            <span v-else-if="previewLoading" class="job-preview-muted">{{ $t('jobPanel.previewLoading') }}</span>
            <template v-else-if="previewLabel">
              <span class="job-preview-label">{{ previewLabel }}</span>
              <span v-if="previewRuns.length" class="job-preview-runs">{{ $t('jobPanel.previewNext') }} {{ previewRuns.map(shortTime).join(' · ') }}</span>
              <span v-else class="job-preview-muted">{{ $t('jobPanel.previewNone') }}</span>
            </template>
          </div>

          <div class="job-switch"><span>{{ $t('jobPanel.enabled') }}</span><n-switch v-model:value="form.enabled" size="small" /></div>
          <div class="job-switch"><span>{{ $t('jobPanel.autoSafe') }}</span><n-switch v-model:value="form.auto_safe" size="small" /></div>
          <div class="job-form-actions">
            <n-button size="small" type="primary" :loading="saving" @click="saveJob">{{ $t('jobPanel.save') }}</n-button>
            <n-button size="small" @click="editing = false">{{ $t('jobPanel.cancel') }}</n-button>
          </div>
        </div>

        <template v-else>
          <div v-for="job in jobs" :key="job.id" class="job-item">
            <div class="job-item-head">
              <span class="job-name" :title="job.name">{{ job.name }}</span>
              <div class="job-badges">
                <!-- 运行状态徽章 -->
                <span v-if="job.completed" class="job-state completed">
                  <svg class="badge-dot" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="3"/></svg>
                  {{ $t('jobPanel.completed') }}
                </span>
                <span v-else class="job-state" :class="job.enabled ? 'enabled' : 'paused'">
                  <svg class="badge-dot" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="3"/></svg>
                  {{ job.enabled ? $t('jobPanel.active') : $t('jobPanel.paused') }}
                </span>
                <!-- 最近一次执行状态徽章 -->
                <span v-if="job.last_status" class="job-state last" :class="`status-${job.last_status}`" :title="job.last_error || ''">
                  <svg class="badge-dot" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="3"/></svg>
                  {{ statusLabel(job.last_status) }}
                </span>
              </div>
            </div>
            <div class="job-prompt">{{ job.prompt }}</div>
            <div class="job-meta">
              <span class="job-meta-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                {{ triggerLabel(job) }}
              </span>
              <span class="job-meta-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
                {{ $t('jobPanel.nextRun', { time: job.next_run_time ? formatDate(job.next_run_time) : $t('jobPanel.neverRun') }) }}
              </span>
              <span v-if="job.last_run_time" class="job-meta-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 12 7 12 7 8 11 8 11 4 13 4 13 16 17 16"/><polyline points="3 17 3 20"/><line x1="7" y1="20" x2="7" y2="24"/><line x1="11" y1="20" x2="11" y2="24"/><line x1="15" y1="20" x2="15" y2="24"/></svg>
                {{ $t('jobPanel.lastRun', { time: formatDate(job.last_run_time) }) }}
              </span>
            </div>
            <div class="job-actions">
              <n-button size="tiny" quaternary class="panel-icon-btn sm" :class="{ 'has-error': !!job.last_error }" :title="$t('jobPanel.edit')" @click="startEdit(job)">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              </n-button>
              <n-button size="tiny" quaternary class="panel-icon-btn sm" :title="$t('jobPanel.runNow')" @click="runNow(job.id)">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              </n-button>
              <n-button size="tiny" quaternary class="panel-icon-btn sm" :title="job.enabled ? $t('jobPanel.pause') : $t('jobPanel.resume')" @click="toggleJob(job)">
                <svg v-if="job.enabled" width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21"/></svg>
              </n-button>
              <n-button size="tiny" quaternary class="panel-icon-btn sm" :title="$t('jobPanel.history')" @click="openHistory(job.id)">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v5h5"/><path d="M3.05 13A9 9 0 1 0 6 5.3L3 8"/><polyline points="12 7 12 12 17 14"/></svg>
              </n-button>
              <n-button size="tiny" quaternary type="error" class="panel-icon-btn sm" :title="$t('jobPanel.delete')" @click="deleteJob(job.id)">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
              </n-button>
            </div>
          </div>
          <n-empty v-if="!loading && jobs.length === 0" :description="$t('jobPanel.empty')" size="small" style="margin-top:32px" />
        </template>
      </div>

      <n-modal v-model:show="historyVisible" preset="card" :title="$t('jobPanel.history')" class="job-history-modal" style="width:min(640px,92vw)">
        <div class="history-list">
          <div v-for="item in history" :key="`${item.run_time}-${item.job_id}`" class="history-item">
            <div class="history-head">
              <span class="job-state last" :class="`status-${item.status}`">
                <svg class="badge-dot" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="3"/></svg>
                {{ statusLabel(item.status) }}
              </span>
              <span class="history-time">{{ formatDate(item.run_time) }}</span>
            </div>
            <div v-if="item.output_snippet" class="history-output">{{ item.output_snippet }}</div>
            <div v-if="item.error" class="history-error">{{ item.error }}</div>
          </div>
          <n-empty v-if="history.length === 0" :description="$t('jobPanel.noHistory')" size="small" />
        </div>
      </n-modal>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useResizablePanel } from '@/composables/useResizablePanel'

type Panel = 'files' | 'skill' | 'mcp' | 'native_tools' | 'checkpoint' | 'risk' | 'jobs'
type TriggerType = 'cron' | 'interval' | 'date'
/** 表单里的「重复方式」:比 raw trigger_type 更贴近日常说法 */
type Mode = 'interval' | 'daily' | 'weekly' | 'monthly' | 'once' | 'cron'
type IntervalUnit = 'minutes' | 'hours' | 'days' | 'weeks'
type Job = { id: string; name: string; prompt: string; trigger_type: TriggerType; trigger_config: Record<string, any>; enabled: boolean; auto_safe: boolean; next_run_time?: string; last_run_time?: string; last_status?: 'ok' | 'error' | 'skipped'; last_error?: string; trigger_label?: string; completed?: boolean }
type History = { job_id: string; run_time: string; status: 'ok' | 'error' | 'skipped'; output_snippet: string; error: string }

const props = defineProps<{ activePanel: Panel | null }>()
const emit = defineEmits<{ (e: 'update:activePanel', value: Panel | null): void }>()
const { t } = useI18n()
const BACKEND_URL = (import.meta as any).env?.VITE_BACKEND_URL || 'http://localhost:8000'
const { width: panelWidth, isResizing, startResize } = useResizablePanel({ storageKey: 'symbix-panel-width-jobs' })
const jobs = ref<Job[]>([])
const history = ref<History[]>([])
const loading = ref(false)
const saving = ref(false)
const editing = ref(false)
const historyVisible = ref(false)
const editingId = ref<string | null>(null)

// ── 表单状态 ──
const form = ref({ name: '', prompt: '', enabled: true, auto_safe: true })
const mode = ref<Mode>('daily')
const naturalText = ref('')
const naturalLoading = ref(false)
const intervalCount = ref(1)
const intervalUnit = ref<IntervalUnit>('hours')
const dailyTime = ref('09:00')
const weeklyDays = ref<number[]>([0])
const weeklyTime = ref('09:00')
const monthlyLast = ref(false)
const monthlyDay = ref(1)
const monthlyTime = ref('09:00')
const onceAt = ref<string | null>(null)
const cronText = ref('0 9 * * *')

// ── 预览状态 ──
const previewLoading = ref(false)
const previewLabel = ref('')
const previewRuns = ref<string[]>([])
const previewError = ref('')
let previewTimer: ReturnType<typeof setTimeout> | null = null

const modeOptions = computed(() => [
  { label: t('jobPanel.freqInterval'), value: 'interval' },
  { label: t('jobPanel.freqDaily'), value: 'daily' },
  { label: t('jobPanel.freqWeekly'), value: 'weekly' },
  { label: t('jobPanel.freqMonthly'), value: 'monthly' },
  { label: t('jobPanel.freqOnce'), value: 'once' },
  { label: t('jobPanel.freqAdvanced'), value: 'cron' },
])
const intervalUnitOptions = computed(() => [
  { label: t('jobPanel.intervalUnitMinute'), value: 'minutes' },
  { label: t('jobPanel.intervalUnitHour'), value: 'hours' },
  { label: t('jobPanel.intervalUnitDay'), value: 'days' },
  { label: t('jobPanel.intervalUnitWeek'), value: 'weeks' },
])
const WEEKDAY_LABELS = ['日', '一', '二', '三', '四', '五', '六']

async function request(path: string, options?: RequestInit): Promise<any> {
  const res = await fetch(`${BACKEND_URL}${path}`, options)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
  return data
}

async function loadJobs() {
  loading.value = true
  try {
    jobs.value = await request('/jobs')
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('jobPanel.loadFail', { msg: e.message }))
  } finally {
    loading.value = false
  }
}

// ── 时间 → trigger 组装 / 反填 ──

function padClock(value: any): string {
  const n = Number(value)
  return Number.isFinite(n) ? String(n).padStart(2, '0') : '00'
}

function timeToClock(time: string): { hour: string; minute: string } {
  const [h = '9', m = '0'] = (time || '09:00').split(':')
  return { hour: String(Number(h)), minute: String(Number(m)) }
}

function cronConfig(minute: string, hour: string, day = '*', month = '*', dayOfWeek = '*'): Record<string, string> {
  return { minute, hour, day, month, day_of_week: dayOfWeek }
}

/** 表单 → { trigger_type, trigger_config };字段不完整时抛错(错误文案直接给用户看) */
function buildTrigger(): { trigger_type: TriggerType; trigger_config: Record<string, any> } {
  if (mode.value === 'interval') {
    const count = Math.max(1, Math.floor(Number(intervalCount.value) || 1))
    return { trigger_type: 'interval', trigger_config: { [intervalUnit.value]: count } }
  }
  if (mode.value === 'daily') {
    const { hour, minute } = timeToClock(dailyTime.value)
    return { trigger_type: 'cron', trigger_config: cronConfig(minute, hour) }
  }
  if (mode.value === 'weekly') {
    if (!weeklyDays.value.length) throw new Error(t('jobPanel.weekdaysRequired'))
    const { hour, minute } = timeToClock(weeklyTime.value)
    const dow = [...weeklyDays.value].sort((a, b) => a - b).join(',')
    return { trigger_type: 'cron', trigger_config: cronConfig(minute, hour, '*', '*', dow) }
  }
  if (mode.value === 'monthly') {
    const { hour, minute } = timeToClock(monthlyTime.value)
    const day = monthlyLast.value ? 'last' : String(Math.min(31, Math.max(1, Math.floor(Number(monthlyDay.value) || 1))))
    return { trigger_type: 'cron', trigger_config: cronConfig(minute, hour, day) }
  }
  if (mode.value === 'once') {
    if (!onceAt.value) throw new Error(t('jobPanel.onceRequired'))
    return { trigger_type: 'date', trigger_config: { run_date: onceAt.value } }
  }
  const parts = cronText.value.trim().split(/\s+/)
  if (parts.length !== 5) throw new Error(t('jobPanel.cronHint'))
  const [minute = '*', hour = '*', day = '*', month = '*', day_of_week = '*'] = parts
  return { trigger_type: 'cron', trigger_config: cronConfig(minute, hour, day, month, day_of_week) }
}

/** trigger → 表单反填(编辑已有任务、或「一句话」识别成功后调用) */
function applyTrigger(triggerType: TriggerType, config: Record<string, any>) {
  const cfg = config || {}
  if (triggerType === 'interval') {
    const key = (Object.keys(cfg)[0] || 'hours') as IntervalUnit
    mode.value = 'interval'
    intervalUnit.value = (['minutes', 'hours', 'days', 'weeks'] as string[]).includes(key) ? key : 'hours'
    intervalCount.value = Math.max(1, Number(cfg[intervalUnit.value]) || 1)
    return
  }
  if (triggerType === 'date') {
    mode.value = 'once'
    onceAt.value = cfg.run_date ? String(cfg.run_date).slice(0, 19) : null
    return
  }
  const dow = String(cfg.day_of_week ?? '*')
  const day = String(cfg.day ?? '*')
  const month = String(cfg.month ?? '*')
  const clockOk = /^\d+$/.test(String(cfg.hour ?? '')) && /^\d+$/.test(String(cfg.minute ?? ''))
  const time = `${padClock(cfg.hour)}:${padClock(cfg.minute)}`
  if (clockOk && dow !== '*' && day === '*' && month === '*') {
    mode.value = 'weekly'
    weeklyDays.value = expandDayOfWeek(dow)
    weeklyTime.value = time
    return
  }
  if (clockOk && dow === '*' && day !== '*' && month === '*') {
    mode.value = 'monthly'
    monthlyLast.value = day === 'last'
    monthlyDay.value = monthlyLast.value ? 1 : Math.min(31, Math.max(1, Number(day) || 1))
    monthlyTime.value = time
    return
  }
  if (clockOk && dow === '*' && day === '*' && month === '*' && cfg.hour !== '*' && cfg.minute !== '*') {
    mode.value = 'daily'
    dailyTime.value = time
    return
  }
  // 表达不了的(按月 + 星期、带 month 限制等)→ 落到高级模式,原样展示
  mode.value = 'cron'
  cronText.value = [String(cfg.minute ?? '*'), String(cfg.hour ?? '*'), day, month, dow].join(' ')
}

/** '1-5' / '0,2,4' → [1,2,3,4,5] / [0,2,4] */
function expandDayOfWeek(value: string): number[] {
  const out = new Set<number>()
  for (const part of value.split(',')) {
    const range = part.trim().split('-')
    if (range.length === 2) {
      const start = Number(range[0])
      const end = Number(range[1].trim())
      if (Number.isFinite(start) && Number.isFinite(end)) {
        for (let i = Math.min(start, end); i <= Math.max(start, end); i++) if (i >= 0 && i <= 6) out.add(i)
      }
    } else if (Number.isFinite(Number(range[0]))) {
      const n = Number(range[0])
      if (n >= 0 && n <= 6) out.add(n)
    }
  }
  return [...out].sort((a, b) => a - b)
}

// ── 预览 ──

async function runPreview() {
  let built: { trigger_type: TriggerType; trigger_config: Record<string, any> }
  try {
    built = buildTrigger()
  } catch (e: any) {
    previewError.value = e.message
    previewLabel.value = ''
    previewRuns.value = []
    return
  }
  previewLoading.value = true
  try {
    const data = await request('/jobs/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trigger_type: built.trigger_type, trigger_config: built.trigger_config, count: 3 }),
    })
    previewLabel.value = data.label || ''
    previewRuns.value = data.next_runs || []
    previewError.value = ''
  } catch (e: any) {
    previewError.value = e.message
    previewLabel.value = ''
    previewRuns.value = []
  } finally {
    previewLoading.value = false
  }
}

function schedulePreview(delay = 250) {
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(runPreview, delay)
}

async function applyNatural() {
  const text = naturalText.value.trim()
  if (!text) return
  naturalLoading.value = true
  try {
    const data = await request('/jobs/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ schedule: text, count: 3 }),
    })
    applyTrigger(data.trigger_type, data.trigger_config || {})
    previewLabel.value = data.label || ''
    previewRuns.value = data.next_runs || []
    previewError.value = ''
  } catch (e: any) {
    previewError.value = e.message
    previewLabel.value = ''
    previewRuns.value = []
  } finally {
    naturalLoading.value = false
  }
}

// ── 新建 / 编辑 / 保存 ──

function startCreate() {
  editingId.value = null
  form.value = { name: '', prompt: '', enabled: true, auto_safe: true }
  naturalText.value = ''
  mode.value = 'daily'
  intervalCount.value = 1
  intervalUnit.value = 'hours'
  dailyTime.value = '09:00'
  weeklyDays.value = [0]
  weeklyTime.value = '09:00'
  monthlyLast.value = false
  monthlyDay.value = 1
  monthlyTime.value = '09:00'
  onceAt.value = null
  cronText.value = '0 9 * * *'
  previewLabel.value = ''
  previewRuns.value = []
  previewError.value = ''
  editing.value = true
  schedulePreview(0)
}

function startEdit(job: Job) {
  editingId.value = job.id
  form.value = { name: job.name, prompt: job.prompt, enabled: job.enabled, auto_safe: job.auto_safe }
  naturalText.value = ''
  applyTrigger(job.trigger_type, job.trigger_config || {})
  previewLabel.value = ''
  previewRuns.value = []
  previewError.value = ''
  editing.value = true
  schedulePreview(0)
}

async function saveJob() {
  saving.value = true
  try {
    const built = buildTrigger()
    const payload: any = { ...form.value, ...built }
    if (!payload.name.trim() || !payload.prompt.trim()) throw new Error(t('jobPanel.required'))
    await (editingId.value
      ? request(`/jobs/${editingId.value}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      : request('/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }))
    const wasEdit = !!editingId.value
    editing.value = false
    await loadJobs()
    ;(window as any).$message?.success?.(wasEdit ? t('jobPanel.updateSuccess') : t('jobPanel.createSuccess'))
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('jobPanel.saveFail', { msg: e.message }))
  } finally {
    saving.value = false
  }
}

async function runNow(id: string) {
  try {
    await request(`/jobs/${id}/run`, { method: 'POST' })
    ;(window as any).$message?.success?.(t('jobPanel.runSuccess'))
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('jobPanel.runFail', { msg: e.message }))
  }
}

async function toggleJob(job: Job) {
  try {
    await request(`/jobs/${job.id}/${job.enabled ? 'pause' : 'resume'}`, { method: 'POST' })
    await loadJobs()
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('jobPanel.saveFail', { msg: e.message }))
  }
}

async function deleteJob(id: string) {
  ;(window as any).$dialog?.warning?.({
    title: t('jobPanel.delete'),
    content: t('jobPanel.deleteConfirm'),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await request(`/jobs/${id}`, { method: 'DELETE' })
        await loadJobs()
        ;(window as any).$message?.success?.(t('jobPanel.deleteSuccess'))
      } catch (e: any) {
        ;(window as any).$message?.error?.(t('jobPanel.deleteFail', { msg: e.message }))
      }
    },
  })
}

async function openHistory(id: string) {
  try {
    history.value = await request(`/jobs/${id}/history`)
    historyVisible.value = true
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('jobPanel.historyFail', { msg: e.message }))
  }
}

// ── 展示 ──

function triggerLabel(job: Job) {
  if (job.trigger_label) return job.trigger_label
  if (job.trigger_type === 'interval') return `${t('jobPanel.triggerInterval')}: ${Object.entries(job.trigger_config).map(([k, v]) => `${v} ${k}`).join(', ')}`
  if (job.trigger_type === 'date') return `${t('jobPanel.triggerDate')}: ${job.trigger_config.run_date}`
  return `Cron: ${[job.trigger_config.minute, job.trigger_config.hour, job.trigger_config.day, job.trigger_config.month, job.trigger_config.day_of_week].join(' ')}`
}

function weekdayShort(index: number) {
  return WEEKDAY_LABELS[index] ?? String(index)
}

/** 2026-10-05T08:30:00+08:00 → 10-05 08:30 */
function shortTime(value: string) {
  const d = new Date(value)
  if (Number.isNaN(d.valueOf())) return value
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function statusLabel(status: string) {
  return status === 'ok' ? t('jobPanel.statusOk') : status === 'error' ? t('jobPanel.statusError') : t('jobPanel.statusSkipped')
}

function formatDate(value: string) {
  const d = new Date(value)
  return Number.isNaN(d.valueOf()) ? value : d.toLocaleString()
}

watch(
  [mode, intervalCount, intervalUnit, dailyTime, weeklyDays, weeklyTime, monthlyLast, monthlyDay, monthlyTime, onceAt, cronText],
  () => { if (editing.value) schedulePreview() },
  { deep: true },
)
watch(() => props.activePanel, (panel) => { if (panel === 'jobs') loadJobs() }, { immediate: true })
defineExpose({ refresh: loadJobs })
</script>

<style scoped>
.side-panel {
  position:absolute;
  left:0;
  top:0;
  bottom:0;
  min-width:var(--panel-min-width);
  max-width:min(var(--panel-max-width),70vw);
  height:100%;
  min-height:0;
  display:flex;
  flex-direction:column;
  overflow:hidden;
  z-index:20;
  background:var(--panel-bg);
  backdrop-filter:blur(16px);
  border-right:1px solid var(--border);
  box-shadow:var(--shadow-md);
}
.panel-resize-handle {
  position:absolute;
  top:0;
  right:calc(var(--panel-resize-handle-width) / -2);
  width:var(--panel-resize-handle-width);
  height:100%;
  cursor:col-resize;
  z-index:2;
}
.panel-resize-handle:hover, .is-resizing .panel-resize-handle {
  background:var(--accent-500);
  opacity:.35;
}
.side-panel-header {
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:14px 16px;
  border-bottom:1px solid var(--border);
  flex:0 0 auto;
}
.side-panel-title {
  font-size:13px;
  font-weight:600;
  color:var(--text-primary);
  text-transform:uppercase;
  letter-spacing:.5px;
}
.side-panel-actions {
  display:flex;
  align-items:center;
  gap:4px;
}
.side-panel-body {
  flex:1;
  min-height:0;
  padding:16px;
  overflow-y:auto;
}
.panel-icon-btn {
  width:32px!important;
  height:32px!important;
  min-width:32px!important;
  padding:0!important;
  border-radius:8px!important;
}
.panel-icon-btn :deep(.n-button__icon) {
  margin:0!important;
}
.refresh-icon {
  transition: transform var(--duration-fast,120ms) var(--ease-standard,ease);
}
.refresh-icon.spinning {
  animation: panel-refresh-spin 1s linear infinite;
}
@keyframes panel-refresh-spin {
  0% { transform:rotate(0deg); }
  100% { transform:rotate(360deg); }
}
.close-btn:hover {
  color:var(--error,#ef4444)!important;
}
.add-entry-btn {
  height:32px;
  font-size:12px;
}
.job-form, .job-item {
  margin-bottom:12px;
  padding:12px;
  border:1px solid var(--border);
  border-radius:var(--radius-md);
  background:var(--surface-hover);
  transition: border-color var(--duration-fast,120ms) ease, background var(--duration-fast,120ms) ease;
}
.job-item:hover {
  border-color:var(--accent-border);
  background:var(--surface-raised);
}
.job-field {
  margin-bottom:10px;
}
.job-field > span, .job-switch > span {
  display:block;
  margin-bottom:5px;
  font-size:11px;
  font-weight:600;
  color:var(--text-secondary);
}
.job-label-row {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:8px;
  margin-bottom:5px;
}
.job-label-row > span {
  font-size:11px;
  font-weight:600;
  color:var(--text-secondary);
}
.job-quick {
  display:inline-flex;
  align-items:center;
  gap:4px;
}
.quick-text {
  font-size:10px;
  color:var(--text-muted);
}
.link-btn {
  padding:0;
  border:none;
  background:none;
  font-size:10px;
  color:var(--accent-500,#EF6B6E);
  cursor:pointer;
}
.link-btn:hover {
  text-decoration:underline;
}
.job-inline, .job-natural {
  display:flex;
  align-items:center;
  gap:6px;
}
.job-weekdays {
  display:flex;
  flex-wrap:wrap;
  gap:4px 10px;
}
.job-hint {
  margin-top:4px;
  font-size:10px;
  line-height:1.4;
  color:var(--text-muted);
}
.job-preview {
  display:flex;
  flex-wrap:wrap;
  align-items:center;
  gap:4px 8px;
  margin:2px 0 10px;
  padding:7px 9px;
  border:1px solid var(--border);
  border-radius:var(--radius-sm,6px);
  background:var(--surface-raised);
  font-size:11px;
  line-height:1.4;
}
.job-preview.is-error {
  border-color:color-mix(in srgb,var(--error,#f87171) 40%,transparent);
}
.job-preview-key {
  font-size:10px;
  font-weight:600;
  color:var(--text-muted);
  text-transform:uppercase;
}
.job-preview-label {
  font-weight:600;
  color:var(--text-primary);
}
.job-preview-runs {
  color:var(--text-secondary);
}
.job-preview-muted {
  color:var(--text-muted);
}
.job-preview-error {
  color:var(--error,#f87171);
}
.job-switch {
  display:flex;
  justify-content:space-between;
  align-items:center;
  margin:10px 0;
}
.job-switch > span {
  margin:0;
}
.job-form-actions {
  display:flex;
  flex-wrap:wrap;
  gap:5px;
  margin-top:10px;
}
.job-item-head {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:8px;
  font-size:13px;
  color:var(--text-primary);
}
.job-name {
  font-weight:600;
  min-width:0;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.job-badges {
  display:flex;
  align-items:center;
  gap:4px;
  flex-shrink:0;
}
.job-state {
  display:inline-flex;
  align-items:center;
  gap:4px;
  padding:2px 7px;
  border-radius:20px;
  font-size:10px;
  font-weight:600;
  white-space:nowrap;
}
.job-state.last {
  font-weight:500;
}
.badge-dot {
  width:6px;
  height:6px;
  fill:currentColor;
}
.enabled, .status-ok {
  color:var(--ok,#4ade80);
  background:color-mix(in srgb,var(--ok,#4ade80) 14%,transparent);
}
.paused {
  color:var(--text-muted);
  background:var(--surface-raised);
}
.completed {
  color:var(--accent,#60a5fa);
  background:color-mix(in srgb,var(--accent,#60a5fa) 14%,transparent);
}
.status-skipped {
  color:var(--warn,#facc15);
  background:color-mix(in srgb,var(--warn,#facc15) 14%,transparent);
}
.status-error {
  color:var(--error,#f87171);
  background:color-mix(in srgb,var(--error,#f87171) 14%,transparent);
}
.job-prompt, .history-output {
  margin-top:7px;
  font-size:12px;
  line-height:1.45;
  white-space:pre-wrap;
  color:var(--text-secondary);
}
.job-meta {
  display:flex;
  flex-wrap:wrap;
  gap:4px 12px;
  margin-top:7px;
  font-size:11px;
  color:var(--text-muted);
}
.job-meta-item {
  display:inline-flex;
  align-items:center;
  gap:4px;
  min-width:0;
}
.job-meta-item svg {
  width:11px;
  height:11px;
  flex-shrink:0;
  opacity:.8;
}
.job-actions {
  display:flex;
  align-items:center;
  gap:2px;
  margin-top:8px;
  padding-top:8px;
  border-top:1px solid var(--border);
}
.job-actions .panel-icon-btn {
  width:24px!important;
  height:24px!important;
  min-width:24px!important;
  border-radius:6px!important;
}
.job-actions .panel-icon-btn:hover {
  color:var(--accent-500,#EF6B6E)!important;
  background:var(--accent-soft)!important;
}
.job-actions .panel-icon-btn[type="error"]:hover {
  color:var(--error,#f87171)!important;
}
.history-item {
  padding:10px 0;
  border-bottom:1px solid var(--border);
  font-size:12px;
}
.history-item:last-child {
  border-bottom:none;
}
.history-head {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:8px;
}
.history-time {
  font-size:11px;
  color:var(--text-muted);
}
.history-error {
  margin-top:6px;
  font-size:11px;
  color:var(--error,#f87171);
}
.job-actions .panel-icon-btn.has-error {
  color:var(--warn,#facc15)!important;
}
.job-history-modal :deep(.n-card-header) {
  font-weight:600;
}
.job-history-modal .history-list {
  max-height:60vh;
  overflow-y:auto;
}
.job-history-modal .history-output {
  font-family:var(--font-mono, monospace);
  background:var(--surface-hover);
  border:1px solid var(--border);
  border-radius:var(--radius-sm,6px);
  padding:8px 10px;
  margin-top:6px;
  font-size:11px;
  line-height:1.5;
  max-height:200px;
  overflow-y:auto;
}
.panel-slide-enter-active {
  transition:all var(--duration-base,180ms) var(--ease-standard,ease);
}
.panel-slide-leave-active {
  transition:all var(--duration-fast,120ms) var(--ease-standard,ease);
}
.panel-slide-enter-from {
  opacity:0;
  transform:translateX(-20px);
}
.panel-slide-leave-to {
  opacity:0;
  transform:translateX(-12px);
}
</style>
