<template>
  <transition name="panel-slide">
    <div class="side-panel" :class="{ 'is-resizing': isResizing }" :style="{ width: `${panelWidth}px` }" v-if="activePanel === 'skill'">
      <div class="panel-resize-handle" :title="$t('common.pullToResize')" @mousedown="startResize" />
      <div class="side-panel-header">
        <span class="side-panel-title">{{ $t('skillPanel.title') }}</span>
        <div class="side-panel-actions">
          <n-button size="tiny" type="primary" class="add-entry-btn" @click="handleOpenAddChooser">
            <template #icon>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </template>
            {{ $t('skillPanel.add') }}
          </n-button>
          <n-button quaternary size="tiny" class="panel-icon-btn close-btn" @click="handleClose">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </n-button>
        </div>
      </div>
      <div class="side-panel-body">
        <n-text depth="3" style="font-size:13px;">{{ $t('skillPanel.installed', { count: skillList.length, toolCount: skillToolList.length }) }}</n-text>
        <div v-for="skill in skillList" :key="skill.name" class="skill-card">
          <div class="skill-card-head">
            <div class="skill-card-info">
              <div class="skill-card-name">{{ skill.display_name || skill.name }}</div>
              <div class="skill-card-desc">{{ skill.description }}</div>
              <div v-if="getSkillTool(skill.name)" class="skill-card-tool">
                {{ $t('skillPanel.tool', { name: 'skill__' + skill.name }) }}
              </div>
            </div>
            <n-button
              size="small"
              quaternary
              type="error"
              class="panel-icon-btn"
              :title="$t('skillPanel.delete')"
              @click="handleRemoveSkill(skill.name)"
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
        <n-empty v-if="skillList.length === 0" :description="$t('skillPanel.empty')" size="small" style="margin-top:20px;" />
      </div>
      <div class="side-panel-footer">
        <n-button size="medium" secondary block class="panel-footer-btn" @click="handleRefresh">
          <template #icon>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
          </template>
          {{ $t('skillPanel.refresh') }}
        </n-button>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { useResizablePanel } from '@/composables/useResizablePanel'

const props = defineProps<{
  activePanel: 'files' | 'skill' | 'mcp' | 'native_tools' | null
  skillList: any[]
  skillToolList: any[]
}>()

const emit = defineEmits<{
  (e: 'update:activePanel', value: 'skill' | 'mcp' | 'native_tools' | null): void
  (e: 'openAddChooser', kind: 'skill'): void
  (e: 'removeSkill', skillName: string): void
  (e: 'refreshSkillList'): void
}>()

const { width: panelWidth, isResizing, startResize } = useResizablePanel({
  storageKey: 'symbix-panel-width-skill',
})

function getSkillTool(skillName: string) {
  return props.skillToolList.find((t: any) => t._skill_name === skillName)
}

function handleClose() {
  emit('update:activePanel', null)
}

function handleOpenAddChooser() {
  emit('openAddChooser', 'skill')
}

function handleRemoveSkill(skillName: string) {
  emit('removeSkill', skillName)
}

function handleRefresh() {
  emit('refreshSkillList')
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
.skill-card {
  margin-top: 10px;
  padding: 12px;
  border-radius: 10px;
  background: var(--surface-hover);
  border: 1px solid transparent;
  transition: border-color var(--duration-fast, 120ms) ease, background var(--duration-fast, 120ms) ease;
}
.skill-card:hover {
  border-color: var(--border);
  background: var(--bg-elevated, var(--surface-hover));
}
.skill-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.skill-card-info {
  flex: 1;
  min-width: 0;
}
.skill-card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.35;
  word-break: break-word;
}
.skill-card-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  line-height: 1.4;
  word-break: break-word;
}
.skill-card-tool {
  margin-top: 6px;
  font-size: 11px;
  color: var(--accent-300);
  padding-left: 2px;
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
.panel-footer-btn {
  height: 36px !important;
  font-weight: 600 !important;
  white-space: nowrap;
}
.panel-footer-btn :deep(.n-button__content) {
  white-space: nowrap;
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
.close-btn:hover {
  color: var(--error, #ef4444) !important;
}
</style>