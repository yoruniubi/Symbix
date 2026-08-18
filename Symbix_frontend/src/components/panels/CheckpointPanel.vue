<template>
  <transition name="panel-slide">
    <div class="side-panel" :class="{ 'is-resizing': isResizing }" :style="{ width: `${panelWidth}px` }" v-if="activePanel === 'checkpoint'">
      <div class="panel-resize-handle" :title="$t('common.pullToResize')" @mousedown="startResize" />
      <div class="side-panel-header">
        <span class="side-panel-title">{{ $t('checkpointPanel.title') }}</span>
        <div class="side-panel-actions">
          <n-button quaternary size="tiny" class="panel-icon-btn" :title="$t('common.refresh')" @click="loadSummary">
            <svg :class="['refresh-icon', { spinning: loading }]" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
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
            <span v-if="summary.tool_call_n" class="cp-tag-mini">🔧 {{ summary.tool_call_n }}</span>
            <span v-if="summary.file_op_n" class="cp-tag-mini">📄 {{ summary.file_op_n }}</span>
            <span v-if="summary.command_n" class="cp-tag-mini">⌨ {{ summary.command_n }}</span>
            <span v-if="summary.mcp_call_n" class="cp-tag-mini">🔌 {{ summary.mcp_call_n }}</span>
          </div>
        </div>

        <!-- 时间线（按 round 折叠） -->
        <div class="cp-timeline" v-if="roundsWithEvents.length">
          <div v-for="(round, ri) in roundsWithEvents" :key="ri" class="cp-round">
            <div class="cp-round-header" @click="toggleRound(round.round_id)">
              <span class="cp-round-marker" :class="{ expanded: round.expanded }">▸</span>
              <div class="cp-round-title">
                <div class="cp-round-user" v-if="round.user_msg">{{ round.user_msg }}</div>
                <div class="cp-round-id" v-else>#{{ round.round_id }}</div>
              </div>
              <span class="cp-pill chip-mini">{{ round.events.length }}</span>
            </div>

            <div class="cp-round-body" v-if="round.expanded">
              <div v-for="(ev, ei) in round.events" :key="ev.id || ei" class="cp-event">
                <span class="cp-event-icon">
                  <span v-if="ev.kind === 'tool_call' && risk(ev) === 'high'" class="dot dot-high">●</span>
                  <span v-else-if="ev.kind === 'tool_call' && risk(ev) === 'medium'" class="dot dot-mid">●</span>
                  <span v-else-if="ev.status === 'error'" class="dot dot-err">●</span>
                  <span v-else-if="ev.kind === 'round'" class="dot dot-round">◆</span>
                  <span v-else class="dot dot-safe">●</span>
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
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useResizablePanel } from '@/composables/useResizablePanel'

const { t } = useI18n() as any

const props = defineProps<{
  activePanel: 'files' | 'skill' | 'mcp' | 'native_tools' | 'checkpoint' | null
  activeSessionId?: string | null
}>()

const emit = defineEmits<{ (e: 'update:activePanel', value: 'files' | 'skill' | 'mcp' | 'native_tools' | 'checkpoint' | null): void }>()

const BACKEND_URL = (import.meta as any).env?.VITE_BACKEND_URL || 'http://localhost:8000'

const { width: panelWidth, isResizing, startResize } = useResizablePanel({
  storageKey: 'symbix-panel-width-checkpoint',
})

const loading = ref(false)
const records = ref<any[]>([])
const summary = ref<any>(null)
const expanded = ref<Set<string>>(new Set())

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
  if (!activeSession.value) {
    records.value = []
    return
  }
  loading.value = true
  try {
    const res = await fetch(
      `${BACKEND_URL}/sessions/${encodeURIComponent(activeSession.value)}/timeline?limit=2000`,
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
  if (!activeSession.value) {
    summary.value = null
    records.value = []
    return
  }
  loading.value = true
  try {
    const res = await fetch(
      `${BACKEND_URL}/sessions/${encodeURIComponent(activeSession.value)}/timeline/summary`,
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

function handleClose() {
  emit('update:activePanel', null)
}
</script>

<style scoped>
.side-panel {
  position: absolute; left: 0; top: 0; bottom: 0;
  display: flex; flex-direction: column;
  background: var(--panel-bg, #fff);
  border-right: 1px solid var(--border);
  overflow: hidden; z-index: 10;
}
.side-panel.is-resizing { user-select: none; }
.side-panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.side-panel-title { font-size: 14px; font-weight: 600; }
.side-panel-actions { display: flex; gap: 4px; align-items: center; }
.panel-icon-btn { width: 28px; height: 28px; padding: 0; border-radius: 6px; }
.close-btn { cursor: pointer; }
.refresh-icon.spinning { animation: cp-rot 0.9s linear infinite; }
@keyframes cp-rot { from { transform: rotate(0); } to { transform: rotate(360deg); } }

.side-panel-body { flex: 1; overflow-y: auto; padding: 10px 12px 16px; }

.cp-summary { margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.cp-summary-row { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.cp-summary-row.sub { margin-top: 4px; font-size: 11px; color: var(--text-secondary); }
.cp-pill { padding: 2px 8px; border-radius: 10px; font-size: 11px; background: rgba(127,127,127,0.08); }
.cp-pill.chip-ok { color: #34d399; background: rgba(52,211,153,0.12); }
.cp-pill.chip-err { color: #c0392b; background: rgba(239,107,110,0.12); }
.cp-pill.chip-info { color: #3b82f6; background: rgba(59,130,246,0.12); }
.cp-pill.chip-mini { font-size: 10px; padding: 1px 6px; }
.cp-pill.st-ok-pill { color: #34d399; }
.cp-pill.st-err-pill { color: #ef4444; }
.cp-tag-mini { white-space: nowrap; }

.cp-timeline { display: flex; flex-direction: column; gap: 6px; }
.cp-round { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.cp-round-header { display: flex; align-items: center; gap: 8px; padding: 6px 8px; cursor: pointer; background: var(--surface-soft, rgba(127,127,127,0.04)); }
.cp-round-header:hover { background: var(--surface-hover); }
.cp-round-marker { color: var(--text-secondary); transition: transform 0.15s ease; font-size: 10px; width: 10px; }
.cp-round-marker.expanded { transform: rotate(90deg); }
.cp-round-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.cp-round-user { color: var(--text-primary); }
.cp-round-id { color: var(--text-secondary); font-family: ui-monospace, monospace; font-size: 11px; }

.cp-round-body { padding: 4px 10px 6px 14px; display: flex; flex-direction: column; gap: 0; }
.cp-event { display: flex; gap: 6px; align-items: flex-start; padding: 4px 0; font-size: 12px; border-bottom: 1px solid rgba(127,127,127,0.08); }
.cp-event:last-child { border-bottom: none; }
.cp-event-icon { padding-top: 2px; font-size: 8px; }
.dot { font-size: 10px; }
.dot-safe { color: #34d399; }
.dot-mid { color: #f59e0b; }
.dot-high { color: #ef4444; }
.dot-err { color: #ef4444; }
.dot-round { color: #8b5cf6; }
.cp-event-main { flex: 1; min-width: 0; }
.cp-event-line1 { display: flex; gap: 6px; align-items: baseline; }
.cp-ev-kind { font-size: 10px; color: var(--text-secondary); text-transform: uppercase; }
.cp-ev-name { font-weight: 600; }
.cp-ev-status { font-size: 9px; padding: 0 4px; border-radius: 6px; }
.st-ok { color: #34d399; }
.st-error { color: #ef4444; }
.st-skipped { color: #f59e0b; }
.cp-ev-detail { font-size: 11px; color: var(--text-secondary); margin-top: 2px; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.cp-path { font-family: ui-monospace, monospace; font-size: 11px; background: rgba(127,127,127,0.08); padding: 0 4px; border-radius: 3px; color: var(--text-primary); max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cp-delta { font-size: 10px; }
.cp-delta.plus { color: #34d399; }
.cp-delta.minus { color: #ef4444; }
.cp-snippet { opacity: 0.65; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
