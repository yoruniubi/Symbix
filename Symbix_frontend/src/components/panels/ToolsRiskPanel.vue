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
          <n-button quaternary size="tiny" class="panel-icon-btn" :title="$t('common.refresh')" @click="loadRules">
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
        <!-- 新增/编辑 override 表单 -->
        <div v-if="adding" class="risk-form">
          <div class="risk-form-field">
            <label class="risk-label">{{ $t('riskPanel.toolName') }}</label>
            <n-input v-model:value="form.tool_name" size="small" placeholder="read_file" @keyup.enter="saveOverride" />
          </div>
          <div class="risk-form-field">
            <label class="risk-label">{{ $t('riskPanel.level') }}</label>
            <n-select v-model:value="form.level" size="small" :options="levelOptions" />
          </div>
          <div class="risk-form-field">
            <label class="risk-label">{{ $t('riskPanel.reason') }}</label>
            <n-input v-model:value="form.reason" size="small" :placeholder="$t('riskPanel.reason')" />
          </div>
          <div class="risk-form-actions">
            <n-button size="small" type="primary" :loading="saving" @click="saveOverride">{{ $t('riskPanel.save') }}</n-button>
            <n-button size="small" @click="adding = false">{{ $t('riskPanel.cancel') }}</n-button>
          </div>
        </div>

        <template v-else>
          <div class="risk-summary">
            <n-text depth="3" class="risk-summary-text">{{ $t('riskPanel.summary', { n: effectiveCount }) }}</n-text>
            <div class="risk-hint">{{ $t('riskPanel.levelHint') }}</div>
          </div>
        </template>

        <!-- 按来源分组,每组下再按等级分组卡片 -->
        <div v-for="sgroup in sourceGroups" :key="sgroup.source" class="risk-source-section">
          <div class="risk-source-header">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="2" y1="12" x2="22" y2="12"/>
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
            </svg>
            <span class="risk-source-title">{{ $t(sgroup.label) }}</span>
            <span class="risk-source-count">{{ sgroup.levelGroups.reduce((acc, g) => acc + g.items.length, 0) }}</span>
          </div>
          <div v-for="group in sgroup.levelGroups" :key="group.level" class="risk-card">
            <div class="risk-card-header" :class="`level-${group.level}`" @click="toggleLevel(group.level)">
              <svg class="risk-expand-icon" :class="{ expanded: expandedLevels.has(group.level) }" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="9,5 18,12 9,19"/></svg>
              <span class="risk-level-dot" :style="{ background: group.color }"></span>
              <span class="risk-card-title">{{ $t(group.label) }}</span>
              <span class="risk-tool-count">{{ group.items.length }}</span>
            </div>
            <div v-if="expandedLevels.has(group.level)"
                 :data-level="group.level"
                 class="risk-card-tools">
              <div v-for="entry in group.items" :key="entry.name" :data-tool="entry.name" class="risk-tool-item">
                <div class="risk-tool-head" @click="toggleTool(entry.name)">
                  <svg class="risk-expand-icon sm" :class="{ expanded: expandedTools.has(entry.name) }" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="9,5 18,12 9,19"/></svg>
                  <svg class="risk-tool-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                  </svg>
                  <span class="risk-tool-name">{{ entry.name }}</span>
                  <div class="risk-tool-ops" @click.stop>
                    <n-dropdown trigger="click" size="small" :options="levelMenuOptions" @select="(k: string) => changeLevel(entry.name, k as Level)">
                      <n-button size="tiny" quaternary class="level-btn" :class="`level-${entry.rule.level}`">
                        <span class="risk-level-dot" :style="{ background: levelColor(entry.rule.level) }"></span>
                        {{ levelLabel(entry.rule.level) }}
                        <svg class="level-btn-arrow" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="6,9 12,15 18,9"/></svg>
                      </n-button>
                    </n-dropdown>
                    <n-button v-if="entry.rule.levelSource === 'override'" size="tiny" quaternary type="error" class="panel-icon-btn sm"
                      :title="$t('riskPanel.deleteOverride')" @click="removeOverride(entry.name)">
                      <template #icon>
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>
                        </svg>
                      </template>
                    </n-button>
                  </div>
                </div>
                <div v-if="expandedTools.has(entry.name)" class="risk-tool-detail">
                  {{ entry.rule.reason || $t('riskPanel.noReason') }}
                </div>
              </div>
            </div>
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
type Panel = 'files' | 'skill' | 'mcp' | 'native_tools' | 'checkpoint' | 'risk' | 'jobs'
type Level = 'safe' | 'medium' | 'high'
type RuleEntry = { name: string; rule: any; source: string; server_id: string }
type SourceGroup = { source: string; label: string; levelGroups: { level: Level; label: string; color: string; items: RuleEntry[] }[] }
const props = defineProps<{
  activePanel: Panel | null
  nativeToolList?: { type: string; function: { name: string; description?: string; parameters?: any } }[]
  skillToolList?: { type: string; function: { name: string; description?: string; parameters?: any } }[]
  mcpToolList?: { type: string; function: { name: string; description?: string; parameters?: any } }[]
  mcpServerGroups?: { server_id: string; tool_count: number; tools: { type: string; function: { name: string } }[]; error?: string }[]
}>()
const emit = defineEmits<{ (e: 'update:activePanel', value: Panel | null): void }>()
const { t } = useI18n()
const BACKEND_URL = (import.meta as any).env?.VITE_BACKEND_URL || 'http://localhost:8000'
const { width: panelWidth, isResizing, startResize } = useResizablePanel({ storageKey: 'symbix-panel-width-risk' })
const rules = ref<Record<string, any>>({})
const loading = ref(false)
const adding = ref(false)
const saving = ref(false)
const expandedLevels = ref<Set<Level>>(new Set(['safe', 'medium', 'high']))
const expandedTools = ref<Set<string>>(new Set())
const form = ref({ tool_name: '', level: 'medium', reason: '' })
const levelOptions = [
  { label: 'Safe', value: 'safe' },
  { label: 'Medium', value: 'medium' },
  { label: 'High', value: 'high' },
]

const effectiveCount = computed(() => Object.keys(rules.value).length)

const groupMeta: Record<Level, { label: string; color: string }> = {
  safe: { label: 'riskPanel.groupSafe', color: 'var(--ok, #4ade80)' },
  medium: { label: 'riskPanel.groupMedium', color: 'var(--warn, #facc15)' },
  high: { label: 'riskPanel.groupHigh', color: 'var(--error, #f87171)' },
}

const validLevels: Level[] = ['safe', 'medium', 'high']

const sourceMeta: Record<string, { label: string; icon: string }> = {
  native: { label: 'riskPanel.groupNative', icon: 'plugins' },
  skill: { label: 'riskPanel.groupSkill', icon: 'thunderbolt' },
  mcp: { label: 'riskPanel.groupMcp', icon: 'link' },
}

function buildLevelGroups(entries: RuleEntry[]) {
  return validLevels.map((level) => {
    const items = entries.filter((e) => e.rule.level === level)
    return { level, label: groupMeta[level].label, color: groupMeta[level].color, items }
  }).filter((g) => g.items.length > 0)
}

const sourceGroups = computed<SourceGroup[]>(() => {
  const buckets: Record<string, { name: string; rule: any; source: string; server_id: string }[]> = {}
  for (const [name, rule] of Object.entries(rules.value)) {
    const r = rule as any
    const src = buckets[r.source] || (buckets[r.source] = [])
    src.push({ name, rule: r, source: r.source, server_id: r.server_id || '' })
  }
  return Object.keys(buckets).map((source) => {
    const meta = sourceMeta[source] || { label: 'riskPanel.groupMcp', icon: 'link' }
    return { source, label: meta.label, levelGroups: buildLevelGroups(buckets[source]) }
  })
})

function changeLevel(toolName: string, level: Level) {
  applyLevel(toolName, level)
}
const levelMenuOptions = validLevels.map((lv) => ({
  label: t(groupMeta[lv].label),
  key: lv,
}))
async function applyLevel(toolName: string, level: Level, reason?: string) {
  const prev = rules.value[toolName] || ({} as any)
  const r = reason !== undefined ? reason : (prev?.levelSource === 'override' ? (prev?.reason || '') : '')
  try {
    const res = await fetch(`${BACKEND_URL}/risk/override`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool_name: toolName, level, reason: r }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    await loadRules()
    ;(window as any).$message?.success?.(t('riskPanel.levelChanged', { tool: toolName, level: t(groupMeta[level].label) }))
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('riskPanel.levelFail', { msg: e.message }))
    await loadRules()
  }
}
function levelLabel(level: string) {
  return t((groupMeta as any)[level]?.label || 'riskPanel.groupSafe')
}

function toggleLevel(level: Level) {
  if (expandedLevels.value.has(level)) expandedLevels.value.delete(level)
  else expandedLevels.value.add(level)
}

function toggleTool(name: string) {
  if (expandedTools.value.has(name)) expandedTools.value.delete(name)
  else expandedTools.value.add(name)
}

async function loadRules() {
  loading.value = true
  try {
    // 汇总三份工具清单,建立 { name -> { source, server_id } }
    const sourceMap: Record<string, { source: string; server_id: string }> = {}
    for (const t of props.nativeToolList || []) {
      const n = t?.function?.name
      if (n) sourceMap[n] = { source: 'native', server_id: '' }
    }
    for (const t of props.skillToolList || []) {
      const n = t?.function?.name
      if (n) sourceMap[n] = { source: 'skill', server_id: '' }
    }
    for (const t of props.mcpToolList || []) {
      const n = t?.function?.name
      if (n) sourceMap[n] = { source: 'mcp', server_id: '' }
    }
    // 若能拿到 server 归属信息则补充 server_id
    for (const g of props.mcpServerGroups || []) {
      for (const t of g?.tools || []) {
        const n = t?.function?.name
        if (n && sourceMap[n]?.source === 'mcp') sourceMap[n].server_id = g.server_id
      }
    }

    const toolNames = Object.keys(sourceMap)
    let rulesData: Record<string, any> = {}
    if (toolNames.length > 0) {
      const res = await fetch(`${BACKEND_URL}/risk/rules/full`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool_names: toolNames }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      rulesData = data.rules || {}
    }
    // 合并:levelSource = 等级来源(default/override,来自后端);source = 工具来源(native/skill/mcp,本地判定)
    const merged: Record<string, any> = {}
    for (const [name, rule] of Object.entries(rulesData)) {
      const meta = sourceMap[name] || { source: 'native', server_id: '' }
      merged[name] = {
        ...rule,
        levelSource: rule.source,          // 后端等级来源
        source: meta.source,               // 工具来源,native/skill/mcp
        server_id: meta.server_id,
      }
    }
    rules.value = merged
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('riskPanel.loadFail', { msg: e.message }))
  } finally {
    loading.value = false
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
    await loadRules()
    adding.value = false
    ;(window as any).$message?.success?.(t('riskPanel.addSuccess'))
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('riskPanel.addFail', { msg: e.message }))
  } finally {
    saving.value = false
  }
}

async function removeOverride(name: string) {
  try {
    const res = await fetch(`${BACKEND_URL}/risk/override/${encodeURIComponent(name)}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    await loadRules()
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('riskPanel.deleteFail', { msg: e.message }))
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
})
// 工具清单可能后于面板打开而异步到达,清单变化时若面板开着则重载
watch(
  () => [
    props.nativeToolList?.length ?? 0,
    props.skillToolList?.length ?? 0,
    props.mcpToolList?.length ?? 0,
  ],
  () => {
    if (props.activePanel === 'risk') loadRules()
  }
)
defineExpose({ refresh: loadRules })
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
  gap:6px;
}
.side-panel-body {
  flex:1;
  min-height:0;
  padding:16px 16px 20px;
  overflow-x:hidden;
  overflow-y:auto;
  overscroll-behavior:contain;
  scrollbar-width:thin;
  scrollbar-color:transparent transparent;
}
.side-panel-body:hover {
  scrollbar-color:var(--scrollbar) transparent;
}
.side-panel-body::-webkit-scrollbar {
  width:4px;
}
.side-panel-body::-webkit-scrollbar-track {
  background:transparent;
}
.side-panel-body::-webkit-scrollbar-thumb {
  background:transparent;
  border-radius:4px;
}
.side-panel-body:hover::-webkit-scrollbar-thumb {
  background:var(--scrollbar);
}
.side-panel-body::-webkit-scrollbar-thumb:hover {
  background:var(--scrollbar-hover);
}
.panel-icon-btn {
  width:28px!important;
  height:28px!important;
  min-width:28px!important;
  padding:0!important;
  border-radius:8px!important;
  flex-shrink:0;
}
.panel-icon-btn.sm {
  width:24px!important;
  height:24px!important;
  min-width:24px!important;
}
.panel-icon-btn :deep(.n-button__icon) {
  margin:0!important;
}
.add-entry-btn {
  height:32px;
  font-size:12px;
  font-weight:600!important;
  white-space:nowrap;
}
.add-entry-btn :deep(.n-button__content) {
  white-space:nowrap;
}
.close-btn:hover {
  color:var(--error,#ef4444)!important;
}
.refresh-icon {
  transition:transform var(--duration-fast,120ms) var(--ease-standard,ease);
}
.refresh-icon.spinning {
  animation: panel-refresh-spin 1s linear infinite;
}
@keyframes panel-refresh-spin {
  0% { transform:rotate(0deg); }
  100% { transform:rotate(360deg); }
}
.risk-summary {
  margin-bottom:6px;
}
.risk-summary-text {
  font-size:13px;
}
.risk-hint {
  margin-top:4px;
  font-size:12px;
  color:var(--text-muted);
  line-height:1.45;
}
.risk-form {
  margin:12px 0;
  padding:12px;
  border:1px solid var(--border);
  border-radius:var(--radius-md);
  background:var(--surface-hover);
}
.risk-form-field {
  margin-bottom:10px;
}
.risk-label {
  display:block;
  margin-bottom:6px;
  font-size:12px;
  font-weight:600;
  color:var(--text-secondary);
}
.risk-form-actions {
  display:flex;
  align-items:center;
  gap:8px;
  margin-top:12px;
}
/* 等级卡片 */
.risk-source-section {
  margin-top:12px;
}
.risk-source-header {
  display:flex;
  align-items:center;
  gap:6px;
  padding:2px 2px 6px;
  color:var(--text-secondary);
  font-size:12px;
  font-weight:600;
  letter-spacing:.3px;
}
.risk-source-header svg {
  flex-shrink:0;
  color:var(--accent-300);
}
.risk-source-title {
  color:var(--text-primary);
}
.risk-source-count {
  margin-left:auto;
  font-size:12px;
  color:var(--text-muted);
  background:var(--surface-hover);
  padding:1px 8px;
  border-radius:10px;
  flex-shrink:0;
}
.risk-card {
  margin-top:10px;
}
.risk-card-header {
  display:flex;
  align-items:center;
  gap:6px;
  padding:10px 10px 10px 12px;
  border-radius:var(--radius-md,8px);
  background:var(--accent-soft);
  color:var(--text-secondary);
  font-size:12px;
  user-select:none;
  cursor:pointer;
  transition:background var(--duration-fast) ease;
}
.risk-card-header:hover {
  background:var(--accent-soft-hover);
}
.risk-card-header.level-safe {
  background:color-mix(in srgb,var(--ok,#4ade80) 12%, var(--accent-soft));
}
.risk-card-header.level-medium {
  background:color-mix(in srgb,var(--warn,#facc15) 16%, var(--accent-soft));
}
.risk-card-header.level-high {
  background:color-mix(in srgb,var(--error,#f87171) 14%, var(--accent-soft));
}
.risk-expand-icon {
  flex-shrink:0;
  transition:transform 0.15s ease;
  opacity:.75;
}
.risk-expand-icon.expanded {
  transform:rotate(90deg);
}
.risk-expand-icon.sm {
  opacity:.5;
}
.risk-level-dot {
  width:8px;
  height:8px;
  border-radius:50%;
  flex-shrink:0;
  margin-left:1px;
}
.risk-card-title {
  font-weight:600;
  font-size:13px;
  color:var(--text-primary);
}
.risk-tool-count {
  margin-left:auto;
  font-size:12px;
  color:var(--accent-300);
  padding-right:2px;
  flex-shrink:0;
}
/* 工具条目（仿 mcp-tool-item） */
.risk-card-tools {
  padding:6px 4px 2px 14px;
}
.risk-tool-item {
  margin-top:8px;
  padding:8px;
  border-radius:var(--radius-md);
  background:var(--surface-hover);
  border:1px solid transparent;
}
.risk-tool-item:hover {
  background:var(--surface-raised);
}
.risk-tool-head {
  display:flex;
  align-items:center;
  gap:5px;
  cursor:pointer;
  min-width:0;
}
.risk-tool-head:active {
  cursor:default;
}
.risk-tool-icon {
  flex-shrink:0;
  color:var(--accent-300,#F7A85B);
  margin-left:2px;
}
.risk-tool-name {
  font-size:13px;
  color:var(--accent-300,#F7A85B);
  line-height:1.35;
  min-width:0;
  flex:1 1 auto;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.risk-tool-ops {
  display:flex;
  align-items:center;
  gap:2px;
  flex-shrink:0;
  margin-left:auto;
  white-space:nowrap;
}
.level-btn {
  height:24px!important;
  font-size:12px!important;
  padding:0 6px!important;
  border-radius:6px!important;
  color:var(--text-secondary)!important;
}
.level-btn .risk-level-dot {
  margin:0 4px 0 0;
}
.level-btn-arrow {
  margin-left:2px;
  opacity:.7;
}
.level-btn.level-safe {
  color:var(--ok,#4ade80)!important;
}
.level-btn.level-medium {
  color:var(--warn,#facc15)!important;
}
.level-btn.level-high {
  color:var(--error,#f87171)!important;
}
.risk-tool-detail {
  font-size:12px;
  color:var(--text-muted);
  margin-top:6px;
  margin-left:26px;
  line-height:1.45;
  white-space:pre-wrap;
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
