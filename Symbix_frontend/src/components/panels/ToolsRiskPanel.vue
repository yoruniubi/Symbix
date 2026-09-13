<template>
  <transition name="panel-slide">
    <div class="side-panel" :class="{ 'is-resizing': isResizing }" :style="{ width: `${panelWidth}px` }" v-if="activePanel === 'risk'">
      <div class="panel-resize-handle" :title="$t('common.pullToResize')" @mousedown="startResize" />
      <div class="side-panel-header">
        <span class="side-panel-title">{{ $t('riskPanel.title') }}</span>
        <div class="side-panel-actions">
          <n-button quaternary size="tiny" class="panel-icon-btn" :title="$t('common.refresh')" @click="loadAll">
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
        <!-- ========== 区块1:会话信任(auto-pilot 开关)========== -->
        <div class="risk-section">
          <div class="risk-section-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            <span>{{ $t('riskPanel.sessionTrustTitle') }}</span>
          </div>
          <div v-if="sessionId" class="trust-card">
            <div class="trust-row">
              <div class="trust-info">
                <div class="trust-mode-label">
                  {{ trust?.mode === 'auto' ? $t('riskPanel.modeAuto') : $t('riskPanel.modeNormal') }}
                </div>
                <div class="trust-mode-hint">
                  {{ trust?.mode === 'auto' ? $t('riskPanel.modeAutoHint') : $t('riskPanel.modeNormalHint') }}
                </div>
              </div>
              <n-switch :value="trust?.mode === 'auto'" size="small" :disabled="!sessionId"
                @update:value="(v: boolean) => setTrustMode(v ? 'auto' : 'normal')" />
            </div>
            <!-- 已生效 grants(永久记住,面板手动清除) -->
            <div v-if="grantList.length" class="trust-grants">
              <div class="grant-title">{{ $t('riskPanel.activeGrants') }}</div>
              <div v-for="g in grantList" :key="g.channel" class="grant-chip">
                <span class="grant-channel">{{ channelLabel(g.channel) }}</span>
                <span class="grant-server">{{ g.server_id }}</span>
                <span class="grant-ttl">{{ $t('riskPanel.grantPermanent') }}</span>
              </div>
              <div class="clear-grants-row">
                <n-button size="tiny" quaternary type="warning" @click="clearGrants">{{ $t('riskPanel.clearGrants') }}</n-button>
              </div>
            </div>
          </div>
          <div v-else class="trust-empty">{{ $t('riskPanel.noSession') }}</div>
        </div>

        <!-- ========== 区块2:通道策略 ========== -->
        <div class="risk-section">
          <div class="risk-section-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
            <span>{{ $t('riskPanel.channelPolicyTitle') }}</span>
          </div>
          <div class="channel-card">
            <div v-for="ch in channelMeta" :key="ch.key" class="channel-row">
              <span class="channel-dot" :style="{ background: ch.color }"></span>
              <span class="channel-name">{{ $t(ch.label) }}</span>
              <span class="channel-policy">{{ $t(ch.policyKey) }}</span>
            </div>
          </div>
          <div class="channel-hint">{{ $t('riskPanel.channelHint') }}</div>
        </div>

        <!-- ========== 区块3:MCP server 信任 ========== -->
        <div v-if="mcpServers.length" class="risk-section">
          <div class="risk-section-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2"/><line x1="8" y1="2" x2="8" y2="22"/></svg>
            <span>{{ $t('riskPanel.serverTrustTitle') }}</span>
          </div>
          <div class="server-trust-list">
            <div v-for="srv in mcpServers" :key="srv.server_id" class="server-trust-row">
              <span class="server-trust-name" :title="srv.server_id">{{ srv.server_id }}</span>
              <span class="server-trust-tag" :class="srv.trusted ? 'is-trusted' : ''">
                {{ srv.trusted ? $t('riskPanel.trusted') : $t('riskPanel.untrusted') }}
              </span>
              <n-switch :value="!!srv.trusted" size="small"
                @update:value="(v: boolean) => toggleServerTrust(srv.server_id, v)" />
            </div>
          </div>
        </div>

        <!-- ========== 区块4:工具级例外(高级,默认收起)========== -->
        <div class="risk-section">
          <div class="risk-section-title clickable" @click="showAdvanced = !showAdvanced">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
            <span>{{ $t('riskPanel.advancedTitle') }}</span>
            <svg class="risk-expand-icon" :class="{ expanded: showAdvanced }" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="9,5 18,12 9,19"/></svg>
          </div>

          <template v-if="showAdvanced">
            <div class="advanced-actions">
              <n-button size="tiny" type="primary" class="add-entry-btn" @click="startAdd">
                <template #icon>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                  </svg>
                </template>
                {{ $t('riskPanel.addOverride') }}
              </n-button>
            </div>

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

            <!-- 工具清单:按来源 + 通道分组 -->
            <div v-for="sgroup in sourceGroups" :key="sgroup.source" class="risk-source-section">
              <div class="risk-source-header">
                <span class="risk-source-title">{{ $t(sgroup.label) }}</span>
                <span class="risk-source-count">{{ sgroup.tools.length }}</span>
              </div>
              <div v-for="tool in sgroup.tools" :key="tool.name" class="tool-override-row">
                <div class="tool-override-main" @click="toggleTool(tool.name)">
                  <svg class="risk-expand-icon sm" :class="{ expanded: expandedTools.has(tool.name) }" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="9,5 18,12 9,19"/></svg>
                  <span class="tool-override-name">{{ tool.name }}</span>
                  <span class="tool-channel-tag">{{ channelShort(tool.rule.channel) }}</span>
                </div>
                <div class="tool-override-ops" @click.stop>
                  <n-dropdown trigger="click" size="small" :options="levelMenuOptions" @select="(k: string) => applyLevel(tool.name, k as Level)">
                    <n-button size="tiny" quaternary class="level-btn" :class="`level-${tool.rule.level}`">
                      <span class="risk-level-dot" :style="{ background: levelColor(tool.rule.level) }"></span>
                      {{ levelLabel(tool.rule.level) }}
                      <svg class="level-btn-arrow" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="6,9 12,15 18,9"/></svg>
                    </n-button>
                  </n-dropdown>
                  <n-button v-if="tool.rule.levelSource === 'override'" size="tiny" quaternary type="error" class="panel-icon-btn sm"
                    :title="$t('riskPanel.deleteOverride')" @click="removeOverride(tool.name)">
                    <template #icon>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>
                      </svg>
                    </template>
                  </n-button>
                </div>
                <div v-if="expandedTools.has(tool.name)" class="risk-tool-detail">
                  {{ tool.rule.reason || $t('riskPanel.noReason') }}
                </div>
              </div>
            </div>
          </template>
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
type TrustMode = 'normal' | 'auto'
type ToolRule = { name: string; rule: any; source: string; server_id: string }

const props = defineProps<{
  activePanel: Panel | null
  activeSessionId?: string | null
  nativeToolList?: { type: string; function: { name: string; description?: string; parameters?: any } }[]
  skillToolList?: { type: string; function: { name: string; description?: string; parameters?: any } }[]
  mcpToolList?: { type: string; function: { name: string; description?: string; parameters?: any } }[]
  mcpServerGroups?: { server_id: string; tool_count: number; tools: { type: string; function: { name: string } }[]; error?: string }[]
}>()
const emit = defineEmits<{ (e: 'update:activePanel', value: Panel | null): void }>()
const { t } = useI18n()
const BACKEND_URL = (import.meta as any).env?.VITE_BACKEND_URL || 'http://localhost:8000'
const { width: panelWidth, isResizing, startResize } = useResizablePanel({ storageKey: 'symbix-panel-width-risk' })

const sessionId = computed(() => props.activeSessionId || null)
const loading = ref(false)
const adding = ref(false)
const saving = ref(false)
const showAdvanced = ref(false)
const expandedTools = ref<Set<string>>(new Set())
const trust = ref<{ mode: TrustMode; grants: Record<string, any> } | null>(null)
const rules = ref<Record<string, any>>({})
const mcpServers = ref<{ server_id: string; trusted: boolean }[]>([])
const form = ref({ tool_name: '', level: 'medium', reason: '' })

const levelOptions = [
  { label: 'Safe', value: 'safe' },
  { label: 'Medium', value: 'medium' },
  { label: 'High', value: 'high' },
]

const groupMeta: Record<Level, { label: string; color: string }> = {
  safe: { label: 'riskPanel.groupSafe', color: 'var(--ok, #4ade80)' },
  medium: { label: 'riskPanel.groupMedium', color: 'var(--warn, #facc15)' },
  high: { label: 'riskPanel.groupHigh', color: 'var(--error, #f87171)' },
}
const validLevels: Level[] = ['safe', 'medium', 'high']

const channelMeta = [
  { key: 'read', label: 'riskPanel.channelRead', color: 'var(--ok,#4ade80)', policyKey: 'riskPanel.policyRead' },
  { key: 'write', label: 'riskPanel.channelWrite', color: 'var(--warn,#facc15)', policyKey: 'riskPanel.policyWrite' },
  { key: 'exec', label: 'riskPanel.channelExec', color: 'var(--warn,#facc15)', policyKey: 'riskPanel.policyExec' },
  { key: 'delete', label: 'riskPanel.channelDelete', color: 'var(--error,#f87171)', policyKey: 'riskPanel.policyDelete' },
  { key: 'network', label: 'riskPanel.channelNetwork', color: 'var(--error,#f87171)', policyKey: 'riskPanel.policyNetwork' },
]

const sourceMeta: Record<string, { label: string }> = {
  native: { label: 'riskPanel.groupNative' },
  skill: { label: 'riskPanel.groupSkill' },
  mcp: { label: 'riskPanel.groupMcp' },
}

const grantList = computed(() => {
  if (!trust.value) return []
  return Object.entries(trust.value.grants || {}).map(([channel, g]: [string, any]) => ({
    channel, server_id: g.server_id || '',
  }))
})

function channelLabel(ch: string) {
  const m = channelMeta.find((c) => c.key === ch)
  return m ? t(m.label) : ch
}
function channelShort(ch?: string) {
  return (ch || 'write').toUpperCase()
}

const sourceGroups = computed(() => {
  const buckets: Record<string, ToolRule[]> = {}
  for (const [name, rule] of Object.entries(rules.value)) {
    const r = rule as any
    const b = buckets[r.source] || (buckets[r.source] = [])
    b.push({ name, rule: r, source: r.source, server_id: r.server_id || '' })
  }
  return Object.keys(buckets).map((source) => ({
    source,
    label: (sourceMeta as any)[source]?.label || 'riskPanel.groupMcp',
    tools: buckets[source],
  }))
})

async function fetchJson(url: string, opts?: RequestInit) {
  const res = await fetch(url, opts)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

// ---- 会话信任 ----
async function loadTrust() {
  if (!sessionId.value) { trust.value = null; return }
  try {
    const data = await fetchJson(`${BACKEND_URL}/risk/session-trust/${encodeURIComponent(sessionId.value)}`)
    trust.value = data || { mode: 'normal', grants: {} }
  } catch { trust.value = null }
}
async function setTrustMode(mode: TrustMode) {
  if (!sessionId.value) return
  try {
    await fetchJson(`${BACKEND_URL}/risk/session-trust/mode`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId.value, mode }),
    })
    await loadTrust()
    ;(window as any).$message?.success?.(t(mode === 'auto' ? 'riskPanel.autoOn' : 'riskPanel.autoOff'))
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('riskPanel.modeFail', { msg: e.message }))
  }
}

/** 清除当前会话全部永久授权(grant 永久记住后,必须能手动撤销)。 */
async function clearGrants() {
  if (!sessionId.value) return
  try {
    const d = await fetchJson(`${BACKEND_URL}/risk/session-trust/${encodeURIComponent(sessionId.value)}`, { method: 'DELETE' })
    if (d && d.status === 'ok') {
      trust.value = { mode: 'normal', grants: {} }
      ;(window as any).$message?.success?.(t('riskPanel.grantsCleared'))
    }
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('riskPanel.modeFail', { msg: e.message }))
  }
}

// ---- MCP server 信任 ----
async function loadServerTrust() {
  const sids = (props.mcpServerGroups || []).map((g) => g.server_id).filter(Boolean)
  const out: { server_id: string; trusted: boolean }[] = []
  for (const sid of sids) {
    try {
      const d = await fetchJson(`${BACKEND_URL}/risk/server-trust/${encodeURIComponent(sid)}`)
      out.push({ server_id: sid, trusted: !!d.trusted })
    } catch { out.push({ server_id: sid, trusted: false }) }
  }
  mcpServers.value = out
}
async function toggleServerTrust(serverId: string, trusted: boolean) {
  try {
    await fetchJson(`${BACKEND_URL}/risk/server-trust/${encodeURIComponent(serverId)}`, {
      method: 'PUT', body: JSON.stringify({ server_id: serverId, trusted }),
      headers: { 'Content-Type': 'application/json' },
    })
    await loadServerTrust()
    ;(window as any).$message?.success?.(t('riskPanel.serverTrustChanged', { server: serverId }))
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('riskPanel.serverTrustFail', { msg: e.message }))
  }
}

// ---- 工具规则 ----
async function loadRules() {
  try {
    const sourceMap: Record<string, { source: string; server_id: string }> = {}
    for (const t of props.nativeToolList || []) { const n = t?.function?.name; if (n) sourceMap[n] = { source: 'native', server_id: '' } }
    for (const t of props.skillToolList || []) { const n = t?.function?.name; if (n) sourceMap[n] = { source: 'skill', server_id: '' } }
    for (const t of props.mcpToolList || []) { const n = t?.function?.name; if (n) sourceMap[n] = { source: 'mcp', server_id: '' } }
    for (const g of props.mcpServerGroups || []) {
      for (const t of g?.tools || []) {
        const n = t?.function?.name
        if (n && sourceMap[n]?.source === 'mcp') sourceMap[n].server_id = g.server_id
      }
    }
    const toolNames = Object.keys(sourceMap)
    let rulesData: Record<string, any> = {}
    if (toolNames.length > 0) {
      const data = await fetchJson(`${BACKEND_URL}/risk/rules/full`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool_names: toolNames }),
      })
      rulesData = data.rules || {}
    }
    const merged: Record<string, any> = {}
    for (const [name, rule] of Object.entries(rulesData)) {
      const meta = sourceMap[name] || { source: 'native', server_id: '' }
      merged[name] = { ...rule, levelSource: rule.source, source: meta.source, server_id: meta.server_id }
    }
    rules.value = merged
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('riskPanel.loadFail', { msg: e.message }))
  }
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadTrust(), loadRules(), loadServerTrust()])
  } finally { loading.value = false }
}

function startAdd() { form.value = { tool_name: '', level: 'medium', reason: '' }; adding.value = true }
async function saveOverride() {
  saving.value = true
  try {
    await fetchJson(`${BACKEND_URL}/risk/override`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form.value),
    })
    await loadRules(); adding.value = false
    ;(window as any).$message?.success?.(t('riskPanel.addSuccess'))
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('riskPanel.addFail', { msg: e.message }))
  } finally { saving.value = false }
}
async function removeOverride(name: string) {
  try {
    await fetchJson(`${BACKEND_URL}/risk/override/${encodeURIComponent(name)}`, { method: 'DELETE' })
    await loadRules()
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('riskPanel.deleteFail', { msg: e.message }))
  }
}
async function applyLevel(toolName: string, level: Level) {
  const prev = rules.value[toolName] || ({} as any)
  const reason = prev?.levelSource === 'override' ? (prev?.reason || '') : ''
  try {
    await fetchJson(`${BACKEND_URL}/risk/override`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool_name: toolName, level, reason }),
    })
    await loadRules()
    ;(window as any).$message?.success?.(t('riskPanel.levelChanged', { tool: toolName, level: t(groupMeta[level].label) }))
  } catch (e: any) {
    ;(window as any).$message?.error?.(t('riskPanel.levelFail', { msg: e.message }))
    await loadRules()
  }
}
function levelLabel(level: string) { return t((groupMeta as any)[level]?.label || 'riskPanel.groupSafe') }
function levelColor(level: string) { return (groupMeta as any)[level]?.color || 'var(--text-muted)' }
function toggleTool(name: string) {
  if (expandedTools.value.has(name)) expandedTools.value.delete(name)
  else expandedTools.value.add(name)
}
const levelMenuOptions = validLevels.map((lv) => ({ label: t(groupMeta[lv].label), key: lv }))
function handleClose() { emit('update:activePanel', null) }

watch(() => props.activePanel, (p) => { if (p === 'risk') loadAll() })
watch(() => props.activeSessionId, () => { if (props.activePanel === 'risk') loadTrust() })
watch(
  () => [props.nativeToolList?.length ?? 0, props.skillToolList?.length ?? 0, props.mcpToolList?.length ?? 0, props.mcpServerGroups?.length ?? 0],
  () => { if (props.activePanel === 'risk') loadAll() }
)
defineExpose({ refresh: loadAll })
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
.side-panel-body:hover { scrollbar-color:var(--scrollbar) transparent; }
.side-panel-body::-webkit-scrollbar { width:4px; }
.side-panel-body::-webkit-scrollbar-track { background:transparent; }
.side-panel-body::-webkit-scrollbar-thumb { background:transparent; border-radius:4px; }
.side-panel-body:hover::-webkit-scrollbar-thumb { background:var(--scrollbar); }
.side-panel-body::-webkit-scrollbar-thumb:hover { background:var(--scrollbar-hover); }
.panel-icon-btn {
  width:28px!important;
  height:28px!important;
  min-width:28px!important;
  padding:0!important;
  border-radius:8px!important;
  flex-shrink:0;
}
.panel-icon-btn.sm { width:24px!important; height:24px!important; min-width:24px!important; }
.panel-icon-btn :deep(.n-button__icon) { margin:0!important; }
.add-entry-btn { height:32px; font-size:12px; font-weight:600!important; white-space:nowrap; }
.close-btn:hover { color:var(--error,#ef4444)!important; }
.refresh-icon { transition:transform var(--duration-fast,120ms) var(--ease-standard,ease); }
.refresh-icon.spinning { animation: panel-refresh-spin 1s linear infinite; }
@keyframes panel-refresh-spin { 0% { transform:rotate(0deg); } 100% { transform:rotate(360deg); } }

/* 区块 */
.risk-section { margin-top:16px; }
.risk-section-title {
  display:flex;
  align-items:center;
  gap:6px;
  padding:2px 2px 8px;
  font-size:12px;
  font-weight:600;
  letter-spacing:.3px;
  color:var(--text-secondary);
}
.risk-section-title.clickable { cursor:pointer; user-select:none; }
.risk-section-title svg { color:var(--accent-300); flex-shrink:0; }
.risk-section-title .risk-expand-icon { margin-left:auto; transition:transform .15s ease; }
.risk-section-title .risk-expand-icon.expanded { transform:rotate(90deg); }
.risk-expand-icon { flex-shrink:0; transition:transform 0.15s ease; opacity:.75; }
.risk-expand-icon.expanded { transform:rotate(90deg); }
.risk-expand-icon.sm { opacity:.5; }

/* 会话信任卡 */
.trust-card {
  padding:12px;
  border-radius:var(--radius-md,8px);
  background:var(--surface-hover);
  border:1px solid var(--border);
}
.trust-row { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.trust-info { min-width:0; }
.trust-mode-label { font-size:13px; font-weight:600; color:var(--text-primary); }
.trust-mode-hint { margin-top:2px; font-size:11px; color:var(--text-muted); line-height:1.4; }
.trust-grants { margin-top:10px; padding-top:8px; border-top:1px dashed var(--border); }
.grant-title { font-size:11px; color:var(--text-muted); margin-bottom:6px; }
.grant-chip {
  display:inline-flex;
  align-items:center;
  gap:6px;
  margin:2px 6px 2px 0;
  padding:2px 8px;
  border-radius:10px;
  background:color-mix(in srgb,var(--warn,#facc15) 14%, var(--surface-hover));
  font-size:11px;
}
.grant-channel { font-weight:600; color:var(--text-primary); }
.grant-server { color:var(--text-muted); }
.grant-ttl { color:var(--text-muted); font-size:10px; }
.clear-grants-row { margin-top:6px; display:flex; justify-content:flex-end; }
.trust-empty { padding:10px; font-size:12px; color:var(--text-muted); }

/* 通道策略 */
.channel-card {
  border-radius:var(--radius-md,8px);
  background:var(--surface-hover);
  border:1px solid var(--border);
  overflow:hidden;
}
.channel-row {
  display:flex;
  align-items:center;
  gap:8px;
  padding:8px 12px;
  font-size:12px;
}
.channel-row + .channel-row { border-top:1px solid var(--border); }
.channel-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.channel-name { font-weight:600; color:var(--text-primary); min-width:70px; }
.channel-policy { color:var(--text-muted); }
.channel-hint { margin-top:6px; font-size:11px; color:var(--text-muted); line-height:1.4; }

/* MCP server 信任 */
.server-trust-list { display:flex; flex-direction:column; gap:6px; }
.server-trust-row {
  display:flex;
  align-items:center;
  gap:8px;
  padding:8px 10px;
  border-radius:var(--radius-md,8px);
  background:var(--surface-hover);
  border:1px solid var(--border);
  font-size:12px;
}
.server-trust-name {
  flex:1;
  min-width:0;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  color:var(--text-primary);
  font-weight:500;
}
.server-trust-tag {
  font-size:10px;
  padding:1px 8px;
  border-radius:10px;
  background:var(--surface-raised);
  color:var(--text-muted);
  flex-shrink:0;
}
.server-trust-tag.is-trusted { background:color-mix(in srgb,var(--ok,#4ade80) 16%, var(--surface-hover)); color:var(--ok,#4ade80); }

/* 高级区 */
.advanced-actions { margin-bottom:8px; }
.risk-form { margin:10px 0; padding:12px; border:1px solid var(--border); border-radius:var(--radius-md); background:var(--surface-hover); }
.risk-form-field { margin-bottom:10px; }
.risk-label { display:block; margin-bottom:6px; font-size:12px; font-weight:600; color:var(--text-secondary); }
.risk-form-actions { display:flex; align-items:center; gap:8px; margin-top:12px; }
.risk-source-section { margin-top:10px; }
.risk-source-header { display:flex; align-items:center; gap:6px; padding:2px 2px 6px; }
.risk-source-title { font-size:12px; font-weight:600; color:var(--text-primary); }
.risk-source-count { margin-left:auto; font-size:11px; color:var(--text-muted); background:var(--surface-hover); padding:1px 8px; border-radius:10px; flex-shrink:0; }
.tool-override-row {
  display:flex;
  flex-wrap:wrap;
  align-items:center;
  gap:6px;
  padding:6px 8px;
  border-radius:var(--radius-md,8px);
  background:var(--surface-hover);
  border:1px solid transparent;
  margin-top:4px;
}
.tool-override-row:hover { background:var(--surface-raised); }
.tool-override-main { display:flex; align-items:center; gap:5px; cursor:pointer; flex:1; min-width:0; }
.tool-override-name {
  font-size:12px;
  color:var(--accent-300,#F7A85B);
  line-height:1.3;
  min-width:0;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.tool-channel-tag {
  font-size:9px;
  font-weight:700;
  padding:1px 5px;
  border-radius:6px;
  background:var(--surface-raised);
  color:var(--text-muted);
  flex-shrink:0;
}
.tool-override-ops { display:flex; align-items:center; gap:2px; flex-shrink:0; }
.level-btn { height:24px!important; font-size:12px!important; padding:0 6px!important; border-radius:6px!important; color:var(--text-secondary)!important; }
.level-btn .risk-level-dot { margin:0 4px 0 0; }
.level-btn-arrow { margin-left:2px; opacity:.7; }
.level-btn.level-safe { color:var(--ok,#4ade80)!important; }
.level-btn.level-medium { color:var(--warn,#facc15)!important; }
.level-btn.level-high { color:var(--error,#f87171)!important; }
.risk-level-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.risk-tool-detail { font-size:12px; color:var(--text-muted); margin-top:6px; margin-left:24px; line-height:1.45; white-space:pre-wrap; flex-basis:100%; }

.panel-slide-enter-active { transition:all var(--duration-base,180ms) var(--ease-standard,ease); }
.panel-slide-leave-active { transition:all var(--duration-fast,120ms) var(--ease-standard,ease); }
.panel-slide-enter-from { opacity:0; transform:translateX(-20px); }
.panel-slide-leave-to { opacity:0; transform:translateX(-12px); }
</style>
