<template>
  <transition name="panel-slide">
    <div class="side-panel" :class="{ 'is-resizing': isResizing }" :style="{ width: `${panelWidth}px` }" v-if="activePanel === 'native_tools'">
      <div class="panel-resize-handle" :title="$t('common.pullToResize')" @mousedown="startResize" />
      <div class="side-panel-header">
        <span class="side-panel-title">{{ $t('nativeToolsPanel.title') }}</span>
        <n-button text size="tiny" class="close-btn" @click="handleClose">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </n-button>
      </div>
      <div class="side-panel-body">
        <n-text depth="3" style="font-size:13px;">{{ $t('nativeToolsPanel.summary', { count: nativeToolList.length }) }}</n-text>
        <div v-for="tool in nativeToolList" :key="tool.function.name" class="mcp-tool-item">
          <div class="mcp-tool-name">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0; margin-right:6px;">
              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
            </svg>
            {{ tool.function.name }}
          </div>
          <div style="font-size:11px; color:var(--text-muted); margin-top:2px; padding-left:20px;">{{ tool.function.description }}</div>
        </div>
        <n-empty v-if="nativeToolList.length === 0" :description="$t('nativeToolsPanel.empty')" size="small" style="margin-top:20px;" />
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { useResizablePanel } from '@/composables/useResizablePanel'

const props = defineProps<{
  activePanel: 'files' | 'skill' | 'mcp' | 'native_tools' | null
  nativeToolList: { type: string; function: { name: string; description: string; parameters: any } }[]
}>()

const emit = defineEmits<{
  (e: 'update:activePanel', value: 'files' | 'skill' | 'mcp' | 'native_tools' | null): void
}>()

const { width: panelWidth, isResizing, startResize } = useResizablePanel({
  storageKey: 'symbix-panel-width-native-tools',
})

function handleClose() {
  emit('update:activePanel', null)
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
.close-btn {
  color: var(--text-muted) !important;
}
.close-btn:hover {
  color: var(--text-secondary) !important;
  background: var(--surface-hover) !important;
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
</style>