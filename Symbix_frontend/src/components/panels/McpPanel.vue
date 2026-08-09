<template>
  <transition name="panel-slide">
    <div class="side-panel" :class="{ 'is-resizing': isResizing }" :style="{ width: `${panelWidth}px` }" v-if="activePanel === 'mcp'">
      <div class="panel-resize-handle" title="拖动调整面板宽度" @mousedown="startResize" />
      <div class="side-panel-header">
        <span class="side-panel-title">{{ $t('mcpPanel.title') }}</span>
        <div class="side-panel-actions">
          <n-button size="tiny" type="primary" class="add-entry-btn" @click="handleOpenAddChooser">
            <template #icon>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </template>
            {{ $t('mcpPanel.add') }}
          </n-button>
          <n-button text size="tiny" class="close-btn" @click="handleClose">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </n-button>
        </div>
      </div>

      <div class="side-panel-body">
        <div style="font-size:12px; color:var(--text-muted); margin-bottom:10px;">
          {{ $t('mcpPanel.summary', { count: mcpServerGroups.length, toolCount: mcpToolList.length }) }}
        </div>
        <!-- 每组一个可折叠 Server -->
        <div v-for="group in mcpServerGroups" :key="group.server_id" class="mcp-server-card">
          <div class="mcp-server-group-header">
            <div class="mcp-server-title" @click="handleToggleMcpServer(group.server_id)">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="currentColor"
                class="mcp-expand-icon"
                :style="{ transform: expandedMcpServers.has(group.server_id) ? 'rotate(90deg)' : 'rotate(0deg)' }"
              >
                <polygon points="9,5 18,12 9,19"/>
              </svg>
              <span class="mcp-server-name">{{ group.server_id }}</span>
              <span class="mcp-status-dot" :class="mcpStatusClass(group.server_id)" :title="mcpStatusLabel(group.server_id)"></span>
              <span class="mcp-tool-count">{{ group.tool_count }} {{ $t('mcpPanel.toolUnit') }}</span>
            </div>
            <div class="mcp-server-ops" @click.stop>
              <n-button
                size="small"
                quaternary
                class="panel-icon-btn"
                :title="$t('mcpPanel.reconnect')"
                @click="handleReconnectMcp(group.server_id)"
              >
                <template #icon>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                  </svg>
                </template>
              </n-button>
              <n-button
                size="small"
                quaternary
                type="error"
                class="panel-icon-btn"
                :title="$t('mcpPanel.delete')"
                @click="handleRemoveMcp(group.server_id)"
              >
                <template #icon>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    <line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>
                  </svg>
                </template>
              </n-button>
            </div>
          </div>

          <div v-if="expandedMcpServers.has(group.server_id)" class="mcp-server-tools">
            <div v-if="group.error" class="mcp-server-error">⚠ {{ group.error }}</div>
            <div v-else v-for="tool in group.tools" :key="tool.function.name" class="mcp-tool-item">
              <div class="mcp-tool-name">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0; margin-right:6px;">
                  <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                </svg>
                {{ tool.function.name }}
              </div>
              <div class="mcp-tool-desc">{{ tool.function.description }}</div>
            </div>
          </div>
        </div>
        <n-empty v-if="mcpServerGroups.length === 0" :description="$t('mcpPanel.empty')" size="small" style="margin-top:20px;" />
      </div>
      <div class="side-panel-footer">
        <n-button size="medium" secondary block class="panel-footer-btn" @click="handleTestMcpConnection">
          <template #icon>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </template>
          {{ $t('mcpPanel.testConnection') }}
        </n-button>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useResizablePanel } from '@/composables/useResizablePanel'

const props = defineProps<{
  activePanel: 'files' | 'skill' | 'mcp' | 'native_tools' | null
  mcpServerGroups: { server_id: string; tool_count: number; tools: any[]; error?: string }[]
  mcpToolList: any[]
  expandedMcpServers: Set<string>
  mcpStatusMap: Record<string, { status: string; tools_count?: number; error?: string; transport?: string }>
}>()

const emit = defineEmits<{
  (e: 'update:activePanel', value:'files'| 'skill' | 'mcp' | 'native_tools' | null): void
  (e: 'toggleMcpServer', serverId: string): void
  (e: 'reconnectMcp', serverId: string): void
  (e: 'removeMcp', serverId: string): void
  (e: 'testMcpConnection'): void
  (e: 'openAddChooser', kind: 'mcp'): void
}>()

const { t } = useI18n()
const { width: panelWidth, isResizing, startResize } = useResizablePanel({
  storageKey: 'symbix-panel-width-mcp',
})

function mcpStatusClass(serverId: string) {
  const st = props.mcpStatusMap[serverId]?.status
  if (st === 'connected') return 'ok'
  if (st === 'error') return 'err'
  return 'off'
}

function mcpStatusLabel(serverId: string) {
  const info = props.mcpStatusMap[serverId]
  if (!info) return t('mcpPanel.statusUnknown')
  if (info.status === 'connected') return t('mcpPanel.statusConnected', { count: info.tools_count ?? 0 })
  if (info.status === 'error') return info.error || t('mcpPanel.statusError')
  return info.status || t('mcpPanel.statusOffline')
}

function handleClose() {
  emit('update:activePanel', null)
}

function handleOpenAddChooser() {
  emit('openAddChooser', 'mcp')
}

function handleToggleMcpServer(serverId: string) {
  emit('toggleMcpServer', serverId)
}

function handleReconnectMcp(serverId: string) {
  emit('reconnectMcp', serverId)
}

function handleRemoveMcp(serverId: string) {
  emit('removeMcp', serverId)
}

function handleTestMcpConnection() {
  emit('testMcpConnection')
}
</script>

<style scoped>
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
.add-entry-btn {
  font-weight: 600 !important;
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
.side-panel-footer {
  flex: 0 0 auto;
  flex-shrink: 0;
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom, 0px));
  border-top: 1px solid var(--border);
  background: var(--panel-bg);
  z-index: 1;
}
.panel-footer-btn {
  height: 36px !important;
  font-weight: 600 !important;
  white-space: nowrap;
}
.panel-footer-btn :deep(.n-button__content) {
  white-space: nowrap;
}
.close-btn {
  color: var(--text-muted) !important;
}
.close-btn:hover {
  color: var(--text-secondary) !important;
  background: var(--surface-hover) !important;
}
.mcp-server-card {
  margin-bottom: 10px;
}
.mcp-server-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 10px 10px 12px;
  border-radius: var(--radius-md, 8px);
  background: var(--accent-soft);
  color: var(--text-secondary);
  font-size: 12px;
  user-select: none;
  transition: background var(--duration-fast) ease;
}
.mcp-server-group-header:hover {
  background: var(--accent-soft-hover);
}
.mcp-server-title {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  cursor: pointer;
  gap: 4px;
}
.mcp-expand-icon {
  flex-shrink: 0;
  transition: transform 0.15s ease;
  opacity: 0.75;
}
.mcp-server-name {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 110px;
}
.mcp-tool-count {
  font-size: 11px;
  color: var(--accent-300);
  margin-left: auto;
  flex-shrink: 0;
  padding-right: 2px;
}
.mcp-server-ops {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.mcp-server-tools {
  padding: 6px 4px 2px 14px;
}
.mcp-server-error {
  font-size: 12px;
  color: var(--error, #ef4444);
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.08);
}
.mcp-tool-item {
  margin-top: 8px;
  padding: 8px;
  border-radius: var(--radius-md);
  background: var(--surface-hover);
  border: 1px solid transparent;
}
.mcp-tool-name {
  font-size: 13px;
  color: var(--accent-300, #F7A85B);
  display: flex;
  align-items: flex-start;
  gap: 2px;
  line-height: 1.35;
  word-break: break-word;
  overflow-wrap: anywhere;
}
.mcp-tool-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
  padding-left: 20px;
  line-height: 1.4;
}
.mcp-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-left: 4px;
  background: #888;
  flex-shrink: 0;
}
.mcp-status-dot.ok { background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,0.55); }
.mcp-status-dot.err { background: #ef4444; }
.mcp-status-dot.off { background: #9ca3af; }
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
</style>