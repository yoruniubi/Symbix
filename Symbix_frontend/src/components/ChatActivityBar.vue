<template>
  <div class="activity-bar">
    <div class="activity-bar-top">
      <n-tooltip v-for="item in panelItems" :key="item.panel" placement="right" trigger="hover">
        <template #trigger>
          <div class="activity-btn" :class="{ active: activePanel === item.panel }" @click="emit('toggle', item.panel)">
            <svg v-if="item.panel === 'files'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M3 9h18"/>
            </svg>
            <svg v-else-if="item.panel === 'skill'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2"/>
              <line x1="12" y1="22" x2="12" y2="15.5"/>
              <polyline points="22 8.5 12 15.5 2 8.5"/>
            </svg>
            <svg v-else-if="item.panel === 'mcp'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
              <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
              <line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>
            </svg>
            <svg v-else width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
            </svg>
          </div>
        </template>
        {{ item.label }}
      </n-tooltip>
    </div>
    <div class="activity-bar-bottom">
      <n-tooltip placement="right" trigger="hover">
        <template #trigger>
          <div class="activity-btn" @click="router.push('/model_setting')">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </div>
        </template>
        {{ $t('activityBar.modelSettings') }}
      </n-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

type Panel = 'files' | 'skill' | 'mcp' | 'native_tools'

defineProps<{ activePanel: Panel | null }>()

const emit = defineEmits<{ (e: 'toggle', panel: Panel): void }>()
const router = useRouter()
const { t } = useI18n()
const panelItems: { panel: Panel; label: string }[] = [
  { panel: 'files', label: t('activityBar.files') },
  { panel: 'skill', label: t('activityBar.skill') },
  { panel: 'mcp', label: t('activityBar.mcp') },
  { panel: 'native_tools', label: t('activityBar.nativeTools') },
]
</script>

<style scoped>
.activity-bar { width: 48px; display: flex; flex-direction: column; align-items: center; justify-content: space-between; padding: 12px 0; background: var(--activity-bar-bg); backdrop-filter: blur(12px); border-right: 1px solid var(--border); flex-shrink: 0; z-index: 10; }
.activity-bar-top, .activity-bar-bottom { display: flex; flex-direction: column; align-items: center; gap: 6px; }
.activity-bar-bottom { margin-top: auto; padding-bottom: 8px; }
.activity-btn { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; border-radius: var(--radius-md, 8px); color: var(--text-secondary); cursor: pointer; transition: all var(--duration-base, 180ms) var(--ease-standard, ease); position: relative; transform: translateY(-15px); }
.activity-btn:hover { color: var(--text-primary); background: var(--surface-hover); }
.activity-btn.active { color: var(--accent-500, #EF6B6E); background: var(--accent-soft); }
.activity-btn.active::before { content: ''; position: absolute; left: 0; top: 10px; bottom: 10px; width: 2px; background: var(--symbix-gradient-soft, linear-gradient(135deg, #F7A85B 0%, #E85C93 100%)); border-radius: 0 2px 2px 0; }
</style>
