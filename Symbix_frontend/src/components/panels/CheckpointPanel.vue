<template>
  <transition name="panel-slide">
    <div class="side-panel" :class="{ 'is-resizing': isResizing }" :style="{ width: `${panelWidth}px` }" v-if="activePanel === 'checkpoint'">
      <div class="panel-resize-handle" :title="$t('common.pullToResize')" @mousedown="startResize" />
      <div class="side-panel-header">
        <span class="side-panel-title">{{ $t('checkpointPanel.title') }}</span>
        <div class="side-panel-actions">
          <n-button quaternary size="tiny" class="panel-icon-btn" :title="$t('common.refresh')" @click="loadSummary">
            <svg :class="['refresh-icon', { spinning: loading }]" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
          </n-button>
          <n-button quaternary size="tiny" class="panel-icon-btn close-btn" @click="handleClose">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </n-button>
        </div>
      </div>
      <div class="side-panel-body">
        <!-- 头部统计 -->
        <div class="cp-summary" v-if="summary && summary.total">
          <div class="cp-summary-row">
            <span class="cp-pill chip-ok">{{ summary.total }} {{ $t('checkpointPanel.events') }}</span>
            <span class="cp-pill chip-info" v-if="summary.round_n">{{ summary.round_n }} {{ $t('checkpointPanel.rounds') }}</span>
            <span class="cp-pill chip-err" v-if="summary.error_n">{{ summary.error_n }} {{ $t('checkpointPanel.errors') }}</span>
          </div>
          <div class="cp-summary-row sub" v-if="summary.tool_call_n || summary.file_op_n || summary.command_n || summary.mcp_call_n">
            <span v-if="summary.tool_call_n" class="cp-tag-mini">
              <svg class="cp-tag-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
              {{ summary.tool_call_n }}
            </span>
            <span v-if="summary.file_op_n" class="cp-tag-mini">
              <svg class="cp-tag-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              {{ summary.file_op_n }}
            </span>
            <span v-if="summary.command_n" class="cp-tag-mini">
              <svg class="cp-tag-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/><rect x="2" y="3" width="20" height="18" rx="2"/></svg>
              {{ summary.command_n }}
            </span>
            <span v-if="summary.mcp_call_n" class="cp-tag-mini">
              <svg class="cp-tag-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
              {{ summary.mcp_call_n }}
            </span>
          </div>
        </div>

        <!-- 时间线（按 round 折叠） -->
        <div class="cp-timeline" v-if="roundsWithEvents.length">
          <div v-for="(round, ri) in roundsWithEvents" :key="ri" class="cp-round">
            <div class="cp-round-header" @click="toggleRound(round.round_id)">
              <svg class="cp-round-marker" :class="{ expanded: round.expanded }" width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="9,5 18,12 9,19"/></svg>
              <div class="cp-round-title">
                <div class="cp-round-user" v-if="round.user_msg">{{ round.user_msg }}</div>
                <div class="cp-round-id" v-else>#{{ round.round_id }}</div>
              </div>
              <span class="cp-pill chip-mini">{{ round.events.length }}</span>
            </div>

            <div class="cp-round-body" v-if="round.expanded">
              <div v-for="(ev, ei) in round.events" :key="ev.id || ei" class="cp-event">
                <span class="cp-event-icon">
                  <svg v-if="ev.kind === 'tool_call' && risk(ev) === 'high'" class="dot dot-high" width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="8"/></svg>
                  <svg v-else-if="ev.kind === 'tool_call' && risk(ev) === 'medium'" class="dot dot-mid" width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="8"/></svg>
                  <svg v-else-if="ev.status === 'error'" class="dot dot-err" width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="8"/></svg>
                  <svg v-else-if="ev.kind === 'round'" class="dot dot-round" width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
                  <svg v-else class="dot dot-safe" width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="8"/></svg>
                </span>
                <div class="cp-event-main">
                  <div class="cp-event-line1">
                    <span class="cp-ev-kind">{{ kindLabel(ev.kind) }}</span>
                    <span class="cp-ev-name">{{ ev.payload?.tool_name || ev.payload?.op || ev.payload?.cmd || '' }}</span>
                    <span class="cp-ev-status" :class="`st-${ev.status}`">{{ ev.status }}</span>
                  </div>
                  <div class="cp-ev-detail" v-if="ev.kind === 'file_op' && ev.payload">
                    <code class="cp-path">{{ ev.payload.path }}</code>
                    <span v-if="ev.payload.size_delta != null" class="cp-delta" :class="ev.payload.size_delta > 0 ? 'plus' : 'minus'">
                      {{ ev.payload.size_delta > 0 ? '+' : '' }}{{ formatBytes(ev.payload.size_delta) }}
                    </span>
                    <n-button size="tiny" quaternary class="cp-action-btn" :title="$t('checkpointPanel.viewDiff')" @click="showDiff(ev)">
                      <template #icon>
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="12" y2="17"/></svg>
                      </template>
                      {{ $t('checkpointPanel.viewDiff') }}
                    </n-button>
                  </div>
                  <div class="cp-ev-detail" v-else-if="ev.kind === 'tool_call' && ev.payload">
                    <code class="cp-path" v-if="ev.payload.arguments?.path">{{ ev.payload.arguments.path }}</code>
                    <span class="cp-snippet" v-if="ev.payload.result_snippet">{{ ev.payload.result_snippet.slice(0, 120) }}</span>
                  </div>
                  <div class="cp-ev-detail" v-else-if="ev.kind === 'command' && ev.payload">
                    <code class="cp-path">{{ ev.payload.cmd }}</code>
                    <span v-if="ev.payload.exit_code != null" class="cp-pill chip-mini" :class="ev.payload.exit_code === 0 ? 'st-ok-pill' : 'st-err-pill'">
                      exit {{ ev.payload.exit_code }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <n-empty v-else :description="activeSession ? $t('checkpointPanel.empty') : $t('checkpointPanel.noSession')" size="small" style="margin-top: 28px;" />

        <div class="cp-actions" v-if="activeSession">
          <n-button size="tiny" quaternary class="cp-prune-btn" @click="handlePrune" :loading="pruning">
            <template #icon>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
            </template>
            {{ $t('checkpointPanel.prune') }}
          </n-button>
        </div>
      </div>

      <!-- Diff 弹窗 -->
      <n-modal v-model:show="diffVisible" :title="$t('checkpointPanel.diffTitle')" preset="card" style="max-width: 90vw; width: 800px;" :mask-closable="true">
        <div class="diff-panel" v-if="diffData">
          <div class="diff-meta">
            <code class="diff-path">{{ diffData.path }}</code>
            <span class="diff-op" :class="diffData.op">{{ diffData.op }}</span>
            <span class="diff-size" v-if="diffData.size_before != null && diffData.size_after != null">
              {{ formatBytes(diffData.size_before!) }} → {{ formatBytes(diffData.size_after!) }}
            </span>
          </div>
          <div class="diff-columns" v-if="diffData.content_before != null || diffData.content_after != null">
            <div class="diff-col">
              <div class="diff-col-header">{{ $t('checkpointPanel.diffBefore') }}</div>
              <pre class="diff-content">{{ diffData.content_before ?? '(empty)' }}</pre>
            </div>
            <div class="diff-col">
              <div class="diff-col-header">{{ $t('checkpointPanel.diffAfter') }}</div>
              <pre class="diff-content">{{ diffData.content_after ?? '(empty)' }}</pre>
            </div>
          </div>
          <div v-else class="diff-no-blob">
            {{ $t('checkpointPanel.diffNoBlob') }}
          </div>
          <div class="diff-restore" v-if="diffData?.blob_stored && diffData?.op !== 'delete'">
            <n-button type="warning" size="small" @click="handleRestore" :loading="restoring">
              <template #icon>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/></svg>
              </template>
              {{ $t('checkpointPanel.restore') }}
            </n-button>
          </div>
        </div>
      </n-modal>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useResizablePanel } from '@/composables/useResizablePanel'

const { t } = useI18n() as any

const props = defineProps<{
  activePanel: 'files' | 'skill' | 'mcp' | 'native_tools' | 'checkpoint' | 'risk' | 'jobs' | null
  activeSessionId?: string | null
}>()

const emit = defineEmits<{ (e: 'update:activePanel', value: 'files' | 'skill' | 'mcp' | 'native_tools' | 'checkpoint' | 'risk' | 'jobs' | null): void }>()

const BACKEND_URL = (import.meta as any).env?.VITE_BACKEND_URL || 'http://localhost:8000'

const { width: panelWidth, isResizing, startResize } = useResizablePanel({
  storageKey: 'symbix-panel-width-checkpoint',
})

const loading = ref(false)
const records = ref<any[]>([])
const summary = ref<any>(null)
const expanded = ref<Set<string>>(new Set())

// Diff dialog
const diffVisible = ref(false)
const diffData = ref<any>(null)
const restoring = ref(false)
const pruning = ref(false)

const activeSession = computed(() => {
  const sid = props.activeSessionId
  return sid && sid !== 'default' ? sid : null
})

interface RoundGroup {
  round_id: string
  user_msg: string
  events: any[]
  expanded: boolean
}

const roundsWithEvents = computed<RoundGroup[]>(() => {
  const map = new Map<string, RoundGroup>()
  for (const r of records.value) {
    const rid = r.round_id
    if (!map.has(rid)) {
      const roundRecord = records.value.find((x) => x.round_id === rid && x.kind === 'round')
      map.set(rid, {
        round_id: rid,
        user_msg: roundRecord?.payload?.user_msg_snippet || '',
        events: [],
        expanded: expanded.value.has(rid),
      })
    }
    map.get(rid)!.events.push(r)
  }
  return Array.from(map.values())
})

function toggleRound(rid: string) {
  if (expanded.value.has(rid)) {
    expanded.value.delete(rid)
  } else {
    expanded.value.add(rid)
  }
  expanded.value = new Set(expanded.value)
}

function risk(ev: any): string {
  return ev.payload?.risk_level || 'unknown'
}

function kindLabel(k: string): string {
  const t2 = t as any
  const map: Record<string, string> = {
    tool_call: 'checkpointPanel.kindTool',
    file_op: 'checkpointPanel.kindFile',
    command: 'checkpointPanel.kindCommand',
    mcp_call: 'checkpointPanel.kindMcp',
    round: 'checkpointPanel.kindRound',
  }
  const key = k in map ? (map as any)[k] : ''
  return key ? t2(key) : k
}

function formatBytes(n: number): string {
  if (n == null) return ''
  const abs = Math.abs(n)
  if (abs < 1024) return `${n}B`
  if (abs < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`
  return `${(n / 1024 / 1024).toFixed(1)}MB`
}

async function loadTimeline() {
  const sid = activeSession.value
  if (!sid) {
    records.value = []
    return
  }
  loading.value = true
  try {
    const res = await fetch(
      `${BACKEND_URL}/sessions/${encodeURIComponent(sid)}/timeline?limit=2000`,
    )
    const data = await res.json()
    records.value = data.records || []
    // 默认展开最近一个 round
    const last = records.value[records.value.length - 1]
    if (last && last.round_id) expanded.value.add(last.round_id)
  } catch (e) {
    console.error('[checkpoint] load timeline failed', e)
    records.value = []
  } finally {
    loading.value = false
  }
}

async function loadSummary() {
  const sid = activeSession.value
  if (!sid) {
    summary.value = null
    records.value = []
    return
  }
  loading.value = true
  try {
    const res = await fetch(
      `${BACKEND_URL}/sessions/${encodeURIComponent(sid)}/timeline/summary`,
    )
    summary.value = await res.json()
  } catch (e) {
    console.error('[checkpoint] load summary failed', e)
    summary.value = null
  } finally {
    loading.value = false
  }
  await loadTimeline()
}

watch(
  () => [props.activePanel, props.activeSessionId],
  ([panel, sid]) => {
    if (panel === 'checkpoint' && sid) loadSummary()
  },
  { immediate: true },
)

async function showDiff(ev: any) {
  const sid = activeSession.value
  const recordId = ev.id
  if (!recordId || !sid) return
  try {
    const res = await fetch(
      `${BACKEND_URL}/sessions/${encodeURIComponent(sid)}/checkpoint/file-op/${recordId}/diff`,
    )
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      ;(window as any).$message?.error?.(`${t('checkpointPanel.restoreFail', { msg: err.detail || res.status }) }`)
      return
    }
    diffData.value = await res.json()
    diffVisible.value = true
  } catch (e: any) {
    ;(window as any).$message?.error?.(`${t('checkpointPanel.restoreFail', { msg: e.message }) }`)
  }
}

async function handleRestore() {
  const sid = activeSession.value
  if (!diffData.value || !sid) return
  ;(window as any).$dialog?.warning?.({
    title: t('checkpointPanel.restore'),
    content: t('checkpointPanel.restoreConfirm'),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      restoring.value = true
      try {
        const res = await fetch(
          `${BACKEND_URL}/sessions/${encodeURIComponent(sid)}/checkpoint/file-op/${diffData.value.record_id}/restore`,
          { method: 'POST' },
        )
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }))
          ;(window as any).$message?.error?.(`${t('checkpointPanel.restoreFail', { msg: err.detail || res.status }) }`)
          return
        }
        ;(window as any).$message?.success?.(t('checkpointPanel.restoreSuccess'))
        diffVisible.value = false
        await loadTimeline()
      } catch (e: any) {
        ;(window as any).$message?.error?.(`${t('checkpointPanel.restoreFail', { msg: e.message }) }`)
      } finally {
        restoring.value = false
      }
    },
  })
}

async function handlePrune() {
  const sid = activeSession.value
  if (!sid) return
  ;(window as any).$dialog?.warning?.({
    title: t('checkpointPanel.prune'),
    content: t('checkpointPanel.pruneConfirm', { n: 50 }),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      pruning.value = true
      try {
        const res = await fetch(
          `${BACKEND_URL}/sessions/${encodeURIComponent(sid)}/timeline/prune`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keep_recent_rounds: 50 }),
          },
        )
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }))
          ;(window as any).$message?.error?.(`${t('checkpointPanel.pruneFail', { msg: err.detail || res.status }) }`)
          return
        }
        const result = await res.json()
        ;(window as any).$message?.success?.(t('checkpointPanel.pruneSuccess', {
          deleted: result.deleted_records,
          blobs: result.deleted_blobs,
        }))
        await loadTimeline()
      } catch (e: any) {
        ;(window as any).$message?.error?.(`${t('checkpointPanel.pruneFail', { msg: e.message }) }`)
      } finally {
        pruning.value = false
      }
    },
  })
}

function handleClose() {
  emit('update:activePanel', null)
}
</script>

<style scoped>
/* 与 McpPanel / SkillPanel / FilePanel 通用的面板骨架，严格保持一致。   */
.side-panel {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  min-width: var(--panel-min-width);
  max-width: min(var(--panel-max-width), 70vw);
  height: 100%;
  min-height: 0;
  background: var(--panel-bg);
  backdrop-filter: blur(16px);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 20;
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.18));
}
.panel-resize-handle {
  position: absolute;
  top: 0;
  right: calc(var(--panel-resize-handle-width) / -2);
  width: var(--panel-resize-handle-width);
  height: 100%;
  cursor: col-resize;
  z-index: 2;
}
.panel-resize-handle:hover,
.is-resizing .panel-resize-handle {
  background: var(--accent-500);
  opacity: 0.35;
}
.panel-slide-enter-active {
  transition: all var(--duration-base, 180ms) var(--ease-standard, ease);
}
.panel-slide-leave-active {
  transition: all var(--duration-fast, 120ms) var(--ease-standard, ease);
}
.panel-slide-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}
.panel-slide-leave-to {
  opacity: 0;
  transform: translateX(-12px);
}
.side-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  flex: 0 0 auto;
}
.side-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.side-panel-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.panel-icon-btn {
  width: 32px !important;
  height: 32px !important;
  min-width: 32px !important;
  padding: 0 !important;
  border-radius: 8px !important;
  flex-shrink: 0;
}
.panel-icon-btn :deep(.n-button__icon) {
  margin: 0 !important;
}
.close-btn:hover {
  color: var(--error, #ef4444) !important;
}
.refresh-icon.spinning {
  animation: panel-refresh-spin 1s linear infinite;
}
@keyframes panel-refresh-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.side-panel-body {
  flex: 1 1 auto;
  min-height: 0;
  padding: 16px 16px 20px;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
}
.side-panel-body:hover {
  scrollbar-color: var(--scrollbar) transparent;
}
.side-panel-body::-webkit-scrollbar {
  width: 4px;
}
.side-panel-body::-webkit-scrollbar-track {
  background: transparent;
}
.side-panel-body::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 4px;
}
.side-panel-body:hover::-webkit-scrollbar-thumb {
  background: var(--scrollbar);
}
.side-panel-body::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-hover);
}

/* checkpoint 专属业务样式                          */

/* 头部统计 */
.cp-summary {
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.cp-summary-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.cp-summary-row.sub {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-muted);
}
.cp-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  background: var(--accent-soft);
  color: var(--text-secondary);
}
.cp-pill.chip-ok { color: var(--success, #34d399); background: rgba(52, 211, 153, 0.12); }
.cp-pill.chip-err { color: var(--error, #ef4444); background: rgba(239, 68, 68, 0.12); }
.cp-pill.chip-info { color: var(--accent-300, #F7A85B); background: var(--accent-soft); }
.cp-pill.chip-mini { font-size: 10px; padding: 1px 6px; }
.cp-pill.st-ok-pill { color: var(--success, #34d399); }
.cp-pill.st-err-pill { color: var(--error, #ef4444); }
.cp-tag-mini { white-space: nowrap; display: inline-flex; align-items: center; gap: 3px; }
.cp-tag-icon { display: block; flex-shrink: 0; }

/* 时间线（按 round 折叠） */
.cp-timeline {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cp-round {
  border-radius: var(--radius-md, 8px);
  background: var(--surface-hover);
  border: 1px solid transparent;
  overflow: hidden;
  transition: border-color var(--duration-fast, 120ms) ease, background var(--duration-fast, 120ms) ease;
}
.cp-round:hover {
  border-color: var(--border);
}
.cp-round-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 10px 10px 12px;
  cursor: pointer;
  user-select: none;
  transition: background var(--duration-fast, 120ms) ease;
}
.cp-round-header:hover {
  background: var(--accent-soft-hover);
}
.cp-round-marker {
  flex-shrink: 0;
  color: var(--text-secondary);
  width: 10px;
  height: 10px;
  transition: transform 0.15s ease;
}
.cp-round-marker.expanded { transform: rotate(90deg); }
.cp-round-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.cp-round-user { color: var(--text-primary); }
.cp-round-id {
  color: var(--text-muted);
  font-family: ui-monospace, monospace;
  font-size: 11px;
}

.cp-round-body {
  padding: 6px 12px 8px 14px;
  display: flex;
  flex-direction: column;
}
.cp-event {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  padding: 6px 0;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
}
.cp-event:last-child { border-bottom: none; }
.cp-event-icon { padding-top: 2px; display: inline-flex; align-items: center; }
.dot { display: block; }
.dot-safe  { color: var(--success, #34d399); }
.dot-mid   { color: var(--warning, #f59e0b); }
.dot-high  { color: var(--error, #ef4444); }
.dot-err   { color: var(--error, #ef4444); }
.dot-round { color: var(--accent-300, #8b5cf6); }
.cp-event-main { flex: 1; min-width: 0; }
.cp-event-line1 {
  display: flex;
  gap: 6px;
  align-items: baseline;
}
.cp-ev-kind {
  font-size: 10px;
  color: var(--text-muted);
  text-transform: uppercase;
}
.cp-ev-name {
  font-weight: 600;
  color: var(--text-primary);
}
.cp-ev-status {
  font-size: 9px;
  padding: 0 4px;
  border-radius: 6px;
}
.st-ok      { color: var(--success, #34d399); }
.st-error   { color: var(--error, #ef4444); }
.st-skipped { color: var(--warning, #f59e0b); }
.cp-ev-detail {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.cp-path {
  font-family: ui-monospace, monospace;
  font-size: 11px;
  background: var(--accent-soft);
  padding: 0 4px;
  border-radius: 4px;
  color: var(--text-primary);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cp-delta { 
  font-size: 10px; 
}
.cp-delta.plus { 
  color: var(--success, #34d399); 
}
.cp-delta.minus { 
  color: var(--error, #ef4444);
}
.cp-snippet { 
  opacity: 0.65; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; 
}

/* Diff + prune 样式 */
.cp-actions { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); display: flex; gap: 8px; }
.cp-prune-btn { color: var(--text-muted); }
.cp-action-btn { opacity: 0.75; transition: opacity var(--duration-fast, 120ms) ease; }
.cp-event:hover .cp-action-btn { opacity: 1; }
.diff-panel { display: flex; flex-direction: column; gap: 12px; }
.diff-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.diff-path { font-family: ui-monospace, monospace; font-size: 12px; background: var(--accent-soft); padding: 2px 6px; border-radius: 4px; color: var(--text-primary); }
.diff-op { font-size: 10px; text-transform: uppercase; padding: 1px 6px; border-radius: 6px; background: var(--accent-soft); color: var(--accent-300, #8b5cf6); }
.diff-size { font-size: 11px; color: var(--text-muted); }
.diff-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; min-height: 120px; }
.diff-col { border: 1px solid var(--border); border-radius: var(--radius-md, 8px); overflow: hidden; display: flex; flex-direction: column; min-width: 0; }
.diff-col-header { font-size: 11px; font-weight: 600; padding: 6px 10px; background: var(--accent-soft); border-bottom: 1px solid var(--border); color: var(--text-secondary); }
.diff-content { flex: 1; margin: 0; padding: 10px; font-family: ui-monospace, monospace; font-size: 11px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; max-height: 320px; overflow: auto; color: var(--text-primary); }
.diff-no-blob { padding: 20px 12px; text-align: center; color: var(--text-muted); font-size: 12px; border: 1px dashed var(--border); border-radius: var(--radius-md, 8px); }
.diff-restore { display: flex; justify-content: flex-end; }

</style>
