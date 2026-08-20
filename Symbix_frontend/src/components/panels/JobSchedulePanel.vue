<template>
  <transition name="panel-slide">
    <div v-if="activePanel === 'jobs'" class="side-panel" :class="{ 'is-resizing': isResizing }" :style="{ width: `${panelWidth}px` }">
      <div class="panel-resize-handle" :title="$t('common.pullToResize')" @mousedown="startResize" />
      <div class="side-panel-header">
        <span class="side-panel-title">{{ $t('jobPanel.title') }}</span>
        <div class="side-panel-actions">
          <n-button size="medium" type="primary" class="add-entry-btn" @click="startCreate">{{ $t('jobPanel.add') }}</n-button>
          <n-button quaternary size="tiny" class="panel-icon-btn" :title="$t('common.refresh')" @click="loadJobs">↻</n-button>
          <n-button quaternary size="tiny" class="panel-icon-btn close-btn" @click="emit('update:activePanel', null)">×</n-button>
        </div>
      </div>
      <div class="side-panel-body">
        <div v-if="editing" class="job-form">
          <div class="job-field"><span>{{ $t('jobPanel.name') }}</span><n-input v-model:value="form.name" size="small" /></div>
          <div class="job-field"><span>{{ $t('jobPanel.prompt') }}</span><n-input v-model:value="form.prompt" type="textarea" :rows="4" size="small" /></div>
          <div class="job-field"><span>{{ $t('jobPanel.triggerType') }}</span><n-select v-model:value="form.trigger_type" size="small" :options="triggerOptions" /></div>
          <div v-if="form.trigger_type === 'interval'" class="job-field">
            <span>{{ $t('jobPanel.triggerInterval') }}</span>
            <n-select v-model:value="intervalPreset" size="small" :options="intervalOptions" @update:value="setInterval" />
          </div>
          <div v-if="form.trigger_type === 'cron'" class="job-field"><span>{{ $t('jobPanel.cronExpression') }}</span><n-input v-model:value="cronText" size="small" placeholder="0 9 * * 1-5" /></div>
          <div v-if="form.trigger_type === 'date'" class="job-field"><span>{{ $t('jobPanel.runDate') }}</span><n-input v-model:value="dateText" size="small" placeholder="2026-01-01T09:00:00" /></div>
          <div class="job-switch"><span>{{ $t('jobPanel.enabled') }}</span><n-switch v-model:value="form.enabled" size="small" /></div>
          <div class="job-switch"><span>{{ $t('jobPanel.autoSafe') }}</span><n-switch v-model:value="form.auto_safe" size="small" /></div>
          <div class="job-form-actions">
            <n-button size="small" type="primary" :loading="saving" @click="saveJob">{{ $t('jobPanel.save') }}</n-button>
            <n-button size="small" quaternary @click="editing = false">{{ $t('jobPanel.cancel') }}</n-button>
          </div>
        </div>

        <template v-else>
          <div v-for="job in jobs" :key="job.id" class="job-item">
            <div class="job-item-head"><strong>{{ job.name }}</strong><span class="job-state" :class="job.enabled ? 'enabled' : 'paused'">{{ job.enabled ? $t('jobPanel.active') : $t('jobPanel.paused') }}</span></div>
            <div class="job-prompt">{{ job.prompt }}</div>
            <div class="job-meta">{{ triggerLabel(job) }}</div>
            <div class="job-meta">{{ job.next_run_time ? $t('jobPanel.nextRun', { time: formatDate(job.next_run_time) }) : $t('jobPanel.neverRun') }}</div>
            <div v-if="job.last_status" class="job-last" :class="`status-${job.last_status}`">{{ statusLabel(job.last_status) }}<span v-if="job.last_error"> · {{ job.last_error }}</span></div>
            <div class="job-actions">
              <n-button size="tiny" quaternary @click="startEdit(job)">{{ $t('jobPanel.edit') }}</n-button>
              <n-button size="tiny" quaternary @click="runNow(job.id)">{{ $t('jobPanel.runNow') }}</n-button>
              <n-button size="tiny" quaternary @click="toggleJob(job)">{{ job.enabled ? $t('jobPanel.pause') : $t('jobPanel.resume') }}</n-button>
              <n-button size="tiny" quaternary @click="openHistory(job.id)">{{ $t('jobPanel.history') }}</n-button>
              <n-button size="tiny" quaternary type="error" @click="deleteJob(job.id)">{{ $t('jobPanel.delete') }}</n-button>
            </div>
          </div>
          <n-empty v-if="!loading && jobs.length === 0" :description="$t('jobPanel.empty')" size="small" style="margin-top:32px" />
        </template>
      </div>

      <n-modal v-model:show="historyVisible" preset="card" :title="$t('jobPanel.history')" style="width:min(560px,90vw)">
        <div v-for="item in history" :key="`${item.run_time}-${item.job_id}`" class="history-item">
          <div><span :class="`status-${item.status}`">{{ statusLabel(item.status) }}</span> · {{ formatDate(item.run_time) }}</div>
          <div v-if="item.output_snippet" class="history-output">{{ item.output_snippet }}</div>
          <div v-if="item.error" class="history-error">{{ item.error }}</div>
        </div>
        <n-empty v-if="history.length === 0" :description="$t('jobPanel.noHistory')" size="small" />
      </n-modal>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useResizablePanel } from '@/composables/useResizablePanel'

type Panel = 'files' | 'skill' | 'mcp' | 'native_tools' | 'checkpoint' | 'risk' | 'jobs'
type TriggerType = 'cron' | 'interval' | 'date'
type Job = { id: string; name: string; prompt: string; trigger_type: TriggerType; trigger_config: Record<string, any>; enabled: boolean; auto_safe: boolean; next_run_time?: string; last_status?: 'ok' | 'error' | 'skipped'; last_error?: string }
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
const intervalPreset = ref('hour')
const cronText = ref('0 9 * * *')
const dateText = ref('')
const form = ref({ name: '', prompt: '', trigger_type: 'interval' as TriggerType, trigger_config: { hours: 1 } as Record<string, any>, enabled: true, auto_safe: true })
const triggerOptions = [{ label: t('jobPanel.triggerInterval'), value: 'interval' }, { label: t('jobPanel.triggerCron'), value: 'cron' }, { label: t('jobPanel.triggerDate'), value: 'date' }]
const intervalOptions = [{ label: t('jobPanel.everyMinute'), value: 'minute' }, { label: t('jobPanel.everyHour'), value: 'hour' }, { label: t('jobPanel.everyDay'), value: 'day' }, { label: t('jobPanel.everyWeek'), value: 'week' }]

async function request(path: string, options?: RequestInit): Promise<any> { const res = await fetch(`${BACKEND_URL}${path}`, options); const data = await res.json().catch(() => ({})); if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`); return data }
async function loadJobs() { loading.value = true; try { jobs.value = await request('/jobs') } catch (e: any) { (window as any).$message?.error?.(t('jobPanel.loadFail', { msg: e.message })) } finally { loading.value = false } }
function startCreate() { editingId.value = null; intervalPreset.value = 'hour'; cronText.value = '0 9 * * *'; dateText.value = ''; form.value = { name: '', prompt: '', trigger_type: 'interval', trigger_config: { hours: 1 }, enabled: true, auto_safe: true }; editing.value = true }
function startEdit(job: Job) { editingId.value = job.id; form.value = { name: job.name, prompt: job.prompt, trigger_type: job.trigger_type, trigger_config: { ...job.trigger_config }, enabled: job.enabled, auto_safe: job.auto_safe }; if (job.trigger_type === 'cron') cronText.value = [job.trigger_config.minute ?? '*', job.trigger_config.hour ?? '*', job.trigger_config.day ?? '*', job.trigger_config.month ?? '*', job.trigger_config.day_of_week ?? '*'].join(' '); if (job.trigger_type === 'date') dateText.value = job.trigger_config.run_date ?? ''; if (job.trigger_type === 'interval') intervalPreset.value = Object.keys(job.trigger_config)[0]?.replace(/s$/, '') || 'hour'; editing.value = true }
function setInterval(value: string) { const cfg: Record<string, number> = { minute: 1, hour: 1, day: 1, week: 1 }; const keys: Record<string, string> = { minute: 'minutes', hour: 'hours', day: 'days', week: 'weeks' }; form.value.trigger_config = { [keys[value]]: cfg[value] } }
function preparePayload() { const payload: any = { ...form.value }; if (payload.trigger_type === 'cron') { const [minute='*', hour='*', day='*', month='*', day_of_week='*'] = cronText.value.trim().split(/\s+/); payload.trigger_config = { minute, hour, day, month, day_of_week } } if (payload.trigger_type === 'date') payload.trigger_config = { run_date: dateText.value }; return payload }
async function saveJob() { saving.value = true; try { const payload = preparePayload(); if (!payload.name.trim() || !payload.prompt.trim()) throw new Error('name and prompt are required'); const data = editingId.value ? await request(`/jobs/${editingId.value}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) : await request('/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); editing.value = false; await loadJobs(); (window as any).$message?.success?.(editingId.value ? t('jobPanel.updateSuccess') : t('jobPanel.createSuccess')); return data } catch (e: any) { (window as any).$message?.error?.(t('jobPanel.saveFail', { msg: e.message })) } finally { saving.value = false } }
async function runNow(id: string) { try { await request(`/jobs/${id}/run`, { method: 'POST' }); (window as any).$message?.success?.(t('jobPanel.runNow')) } catch (e: any) { (window as any).$message?.error?.(t('jobPanel.runFail', { msg: e.message })) } }
async function toggleJob(job: Job) { try { await request(`/jobs/${job.id}/${job.enabled ? 'pause' : 'resume'}`, { method: 'POST' }); await loadJobs() } catch (e: any) { (window as any).$message?.error?.(t('jobPanel.saveFail', { msg: e.message })) } }
async function deleteJob(id: string) { if (!window.confirm(t('jobPanel.deleteConfirm'))) return; try { await request(`/jobs/${id}`, { method: 'DELETE' }); await loadJobs(); (window as any).$message?.success?.(t('jobPanel.deleteSuccess')) } catch (e: any) { (window as any).$message?.error?.(t('jobPanel.deleteFail', { msg: e.message })) } }
async function openHistory(id: string) { try { history.value = await request(`/jobs/${id}/history`); historyVisible.value = true } catch (e: any) { (window as any).$message?.error?.(t('jobPanel.historyFail', { msg: e.message })) } }
function triggerLabel(job: Job) { if (job.trigger_type === 'interval') return `${t('jobPanel.triggerInterval')}: ${Object.entries(job.trigger_config).map(([k, v]) => `${v} ${k}`).join(', ')}`; if (job.trigger_type === 'date') return `${t('jobPanel.triggerDate')}: ${job.trigger_config.run_date}`; return `Cron: ${[job.trigger_config.minute, job.trigger_config.hour, job.trigger_config.day, job.trigger_config.month, job.trigger_config.day_of_week].join(' ')}` }
function statusLabel(status: string) { return status === 'ok' ? t('jobPanel.statusOk') : status === 'error' ? t('jobPanel.statusError') : t('jobPanel.statusSkipped') }
function formatDate(value: string) { const d = new Date(value); return Number.isNaN(d.valueOf()) ? value : d.toLocaleString() }
watch(() => props.activePanel, (panel) => { if (panel === 'jobs') loadJobs() }, { immediate: true })
defineExpose({ refresh: loadJobs })
</script>

<style scoped>
.side-panel { position:absolute; left:0; top:0; bottom:0; min-width:var(--panel-min-width); max-width:min(var(--panel-max-width),70vw); display:flex; flex-direction:column; overflow:hidden; z-index:20; background:var(--panel-bg); backdrop-filter:blur(16px); border-right:1px solid var(--border); box-shadow:var(--shadow-md); }
.panel-resize-handle { position:absolute; top:0; right:calc(var(--panel-resize-handle-width) / -2); width:var(--panel-resize-handle-width); height:100%; cursor:col-resize; z-index:2; }.panel-resize-handle:hover,.is-resizing .panel-resize-handle{background:var(--accent-500);opacity:.35}.side-panel-header{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid var(--border)}.side-panel-title{font-size:13px;font-weight:600;color:var(--text-primary);text-transform:uppercase;letter-spacing:.5px}.side-panel-actions{display:flex;align-items:center;gap:4px}.side-panel-body{flex:1;min-height:0;padding:16px;overflow-y:auto}.panel-icon-btn{width:32px!important;height:32px!important;min-width:32px!important;padding:0!important;font-size:20px}.close-btn:hover{color:var(--error,#ef4444)!important}.add-entry-btn{height:32px;font-size:12px}.job-form,.job-item{margin-bottom:12px;padding:12px;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-hover)}.job-field{margin-bottom:10px}.job-field>span,.job-switch>span{display:block;margin-bottom:5px;font-size:11px;font-weight:600;color:var(--text-secondary)}.job-switch{display:flex;justify-content:space-between;align-items:center;margin:10px 0}.job-switch>span{margin:0}.job-form-actions,.job-actions{display:flex;flex-wrap:wrap;gap:5px;margin-top:10px}.job-item-head{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:13px;color:var(--text-primary)}.job-state{padding:2px 6px;border-radius:5px;font-size:10px}.enabled,.status-ok{color:var(--ok,#4ade80);background:color-mix(in srgb,var(--ok,#4ade80) 12%,transparent)}.paused,.status-skipped{color:var(--text-muted);background:var(--surface-raised)}.job-prompt,.history-output{margin-top:7px;font-size:12px;line-height:1.45;white-space:pre-wrap;color:var(--text-secondary)}.job-meta,.job-last{margin-top:5px;font-size:11px;color:var(--text-muted)}.status-error,.history-error{color:var(--error,#f87171)}.history-item{padding:9px 0;border-bottom:1px solid var(--border);font-size:12px}.panel-slide-enter-active{transition:all var(--duration-base,180ms) var(--ease-standard,ease)}.panel-slide-leave-active{transition:all var(--duration-fast,120ms) var(--ease-standard,ease)}.panel-slide-enter-from{opacity:0;transform:translateX(-20px)}.panel-slide-leave-to{opacity:0;transform:translateX(-12px)}
</style>
