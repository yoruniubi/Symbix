<template>
  <transition name="panel-slide">
    <div class="side-panel" :class="{ 'is-resizing': isResizing }" :style="{ width: `${panelWidth}px` }" v-if="activePanel === 'risk'">
      <div class="panel-resize-handle" :title="$t('common.pullToResize')" @mousedown="startResize" />
      <div class="side-panel-header">
        <span class="side-panel-title">{{ $t('riskPanel.title') }}</span>
        <div class="side-panel-actions">
          <n-button size="medium" type="primary" class="add-entry-btn" @click="startAdd">
            <template #icon>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </template>
            {{ $t('riskPanel.addOverride') }}
          </n-button>
          <n-button quaternary size="tiny" class="panel-icon-btn close-btn" @click="handleClose">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </n-button>
        </div>
      </div>

      <div class="side-panel-body">
        <!-- 新增/编辑 override 表单 -->
        <div v-if="adding" class="risk-form">
          <div class="risk-form-field">
            <span class="risk-label">{{ $t('riskPanel.toolName') }}</span>
            <n-input v-model:value="form.tool_name" size="small" placeholder="read_file" @keyup.enter="saveOverride" />
          </div>
          <div class="risk-form-field">
            <span class="risk-label">{{ $t('riskPanel.level') }}</span>
            <n-select v-model:value="form.level" size="small" :options="levelOptions" />
          </div>
          <div class="risk-form-field">
            <span class="risk-label">{{ $t('riskPanel.reason') }}</span>
            <n-input v-model:value="form.reason" size="small" :placeholder="$t('riskPanel.reason')" />
          </div>
          <div class="risk-form-actions">
            <n-button size="small" type="primary" :loading="saving" @click="saveOverride">{{ $t('riskPanel.save') }}</n-button>
            <n-button size="small" quaternary @click="adding = false">{{ $t('riskPanel.cancel') }}</n-button>
          </div>
        </div>

        <template v-else>
          <n-text depth="3" style="font-size:13px;">{{ $t('riskPanel.summary', { n: effectiveCount }) }}</n-text>
          <div class="risk-hint">{{ $t('riskPanel.overrideHint') }}</div>
        </template>

        <!-- 按等级分组 -->
        <div v-for="group in groups" :key="group.level" class="risk-group">
          <div class="risk-group-head" :style="{ color: group.color }">
            <span class="risk-dot" :style="{ background: group.color }"></span>
            {{ $t(group.label) }}
            <span class="risk-count">({{ group.items.length }})</span>
          </div>
          <div v-for="(rule, name) in group.items" :key="name" class="risk-item">
            <div class="risk-item-info">
              <div class="risk-item-name">
                <code>{{ name }}</code>
                <span class="risk-source" :class="rule.source === 'override' ? 'src-override' : 'src-default'">
                  {{ rule.source === 'override' ? $t('riskPanel.sourceOverride') : $t('riskPanel.sourceDefault') }}
                </span>
              </div>
              <div class="risk-item-reason">{{ rule.reason }}</div>
            </div>
            <n-button v-if="rule.source === 'override'" size="tiny" quaternary type="error" class="panel-icon-btn"
              :title="$t('riskPanel.deleteOverride')" @click="removeOverride(name)">
              <template #icon>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                </svg>
              </template>
            </n-button>
          </div>
        </div>

        <!-- 试测工具 -->
        <div class="risk-test">
          <div class="risk-test-title">{{ $t('riskPanel.testTitle') }}</div>
          <div class="risk-test-row">
            <n-input v-model:value="testForm.tool_name" size="small" placeholder="run_command" style="flex:1;" />
            <n-button size="small" type="primary" secondary :loading="testing" @click="runTest">{{ $t('riskPanel.testBtn') }}</n-button>
          </div>
          <n-input v-model:value="testForm.arguments" size="small" type="textarea" :rows="2"
            placeholder='{"command": "ls -la"}' style="margin-top:8px;" />
          <div v-if="testResult" class="risk-test-result">
            <span class="risk-dot" :style="{ background: levelColor(testResult.level) }"></span>
            <code>{{ testResult.level.toUpperCase() }}</code>
            <span class="risk-item-reason">{{ testResult.reason }}</span>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useResizablePanel } from '@/composables/useResizablePanel'

const props = defineProps<{
  activePanel: 'files' | 'skill' | 'mcp' | 'native_tools' | 'checkpoint' | 'risk' | 'jobs' | null
}>()

const emit = defineEmits<{
  (e: 'update:activePanel', value: 'files' | 'skill' | 'mcp' | 'native_tools' | 'checkpoint' | 'risk' | 'jobs' | null): void
}>()

const { t } = useI18n()
const BACKEND_URL = (import.meta as any).env?.VITE_BACKEND_URL || 'http://localhost:8000'
const { width: panelWidth, isResizing, startResize } = useResizablePanel({
  storageKey: 'symbix-panel-width-risk',
})

const rules = ref<Record<string, any>>({})
const adding = ref(false)
const saving = ref(false)
const testing = ref(false)
const testResult = ref<any>(null)

const form = ref({ tool_name: '', level: 'medium', reason: '' })
const testForm = ref({ tool_name: 'run_command', arguments: '{}' })

const levelOptions = [
  { label: 'Safe', value: 'safe' },
  { label: 'Medium', value: 'medium' },
  { label: 'High', value: 'high' },
]

const effectiveCount = computed(() => Object.keys(rules.value).length)

const groupMeta: Record<string, { label: string; color: string }> = {
  safe: { label: 'riskPanel.groupSafe', color: 'var(--ok, #4ade80)' },
  medium: { label: 'riskPanel.groupMedium', color: 'var(--warn, #facc15)' },
  high: { label: 'riskPanel.groupHigh', color: 'var(--error, #f87171)' },
}

const groups = computed(() =>
  (['safe', 'medium', 'high'] as const)
    .map((level) => {
      const items: Record<string, any> = {}
      for (const [name, rule] of Object.entries(rules.value)) {
        if ((rule as any).level === level) items[name] = rule
      }
      return { level, label: groupMeta[level].label, color: groupMeta[level].color, items }
    })
    .filter((g) => Object.keys(g.items).length > 0),
)

async function loadRules() {
  try {
    const res = await fetch(`${BACKEND_URL}/risk/rules`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    rules.value = data.rules || {}
  } catch (e: any) {
    ;(window as any).$message?.error?.(`${t('riskPanel.loadFail', { msg: e.message })}`)
  }
}

function startAdd() {
  form.value = { tool_name: '', level: 'medium', reason: '' }
  adding.value = true
}

async function saveOverride() {
  saving.value = true
  try {
    const res = await fetch(`${BACKEND_URL}/risk/override`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form.value),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    rules.value = data.rules || {}
    adding.value = false
    ;(window as any).$message?.success?.(t('riskPanel.addSuccess'))
  } catch (e: any) {
    ;(window as any).$message?.error?.(`${t('riskPanel.addFail', { msg: e.message })}`)
  } finally {
    saving.value = false
  }
}

async function removeOverride(name: string) {
  try {
    const res = await fetch(`${BACKEND_URL}/risk/override/${encodeURIComponent(name)}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    rules.value = data.rules || {}
  } catch (e: any) {
    ;(window as any).$message?.error?.(`${t('riskPanel.deleteFail', { msg: e.message })}`)
  }
}

async function runTest() {
  let args: any = {}
  try {
    args = JSON.parse(testForm.value.arguments || '{}')
  } catch {
    args = {}
  }
  testing.value = true
  try {
    const res = await fetch(`${BACKEND_URL}/risk/classify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool_name: testForm.value.tool_name, arguments: args }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    testResult.value = await res.json()
  } catch (e: any) {
    ;(window as any).$message?.error?.(`${t('riskPanel.deleteFail', { msg: e.message })}`)
  } finally {
    testing.value = false
  }
}

function levelColor(level: string) {
  return (groupMeta as any)[level]?.color || 'var(--text-muted)'
}

function handleClose() {
  emit('update:activePanel', null)
}

watch(() => props.activePanel, (panel) => {
  if (panel === 'risk') loadRules()
}, { immediate: true })

defineExpose({ refresh: loadRules })
</script>

<style scoped>
.side-panel { position:absolute; left:0; top:0; bottom:0; min-width:var(--panel-min-width); max-width:min(var(--panel-max-width),70vw); height:100%; min-height:0; display:flex; flex-direction:column; overflow:hidden; z-index:20; background:var(--panel-bg); backdrop-filter:blur(16px); border-right:1px solid var(--border); box-shadow:var(--shadow-md); }
.panel-resize-handle { position:absolute; top:0; right:calc(var(--panel-resize-handle-width) / -2); width:var(--panel-resize-handle-width); height:100%; cursor:col-resize; z-index:2; }
.panel-resize-handle:hover, .is-resizing .panel-resize-handle { background:var(--accent-500); opacity:.35; }
.side-panel-header { display:flex; align-items:center; justify-content:space-between; padding:14px 16px; border-bottom:1px solid var(--border); flex:0 0 auto; }
.side-panel-title { font-size:13px; font-weight:600; color:var(--text-primary); text-transform:uppercase; letter-spacing:.5px; }
.side-panel-actions { display:flex; align-items:center; gap:4px; }
.side-panel-body { flex:1; min-height:0; padding:16px; overflow-y:auto; }
.panel-icon-btn { width:32px!important; height:32px!important; min-width:32px!important; padding:0!important; border-radius:8px!important; }
.panel-icon-btn :deep(.n-button__icon) { margin:0!important; }
.close-btn:hover { color:var(--error,#ef4444)!important; }
.add-entry-btn { height:32px; font-size:12px; }
.risk-hint, .risk-item-reason { margin-top:4px; font-size:11px; color:var(--text-muted); line-height:1.45; }
.risk-form, .risk-test { margin:12px 0; padding:12px; border:1px solid var(--border); border-radius:var(--radius-md); background:var(--surface-hover); }
.risk-form-field { margin-bottom:9px; }
.risk-label, .risk-test-title { display:block; margin-bottom:5px; font-size:11px; font-weight:600; color:var(--text-secondary); }
.risk-form-actions, .risk-test-row, .risk-test-result { display:flex; align-items:center; gap:8px; }
.risk-group { margin-top:18px; }
.risk-group-head { display:flex; align-items:center; gap:6px; padding-bottom:7px; font-size:12px; font-weight:600; border-bottom:1px solid var(--border); }
.risk-count { color:var(--text-muted); font-weight:400; }
.risk-dot { width:7px; height:7px; border-radius:50%; flex:0 0 auto; }
.risk-item { display:flex; align-items:flex-start; justify-content:space-between; gap:8px; padding:9px 2px; border-bottom:1px solid var(--border); }
.risk-item-info { min-width:0; flex:1; }
.risk-item-name { display:flex; align-items:center; gap:7px; min-width:0; }
.risk-item-name code, .risk-test-result code { font-size:12px; color:var(--accent-300); overflow-wrap:anywhere; }
.risk-source { padding:1px 5px; border-radius:4px; font-size:10px; line-height:1.4; }
.src-default { color:var(--text-muted); background:var(--surface-raised); }
.src-override { color:var(--accent-300); background:var(--accent-soft); }
.risk-test { margin-top:22px; }
.risk-test-result { margin-top:9px; padding-top:8px; border-top:1px solid var(--border); }
.panel-slide-enter-active { transition:all var(--duration-base,180ms) var(--ease-standard,ease); }
.panel-slide-leave-active { transition:all var(--duration-fast,120ms) var(--ease-standard,ease); }
.panel-slide-enter-from { opacity:0; transform:translateX(-20px); }
.panel-slide-leave-to { opacity:0; transform:translateX(-12px); }
</style>
