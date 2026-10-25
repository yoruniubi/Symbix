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
              <path d="M9.5 2.5 11 7l4.5 1.5L11 10l-1.5 4.5L8 10l-4.5-1.5L8 7 9.5 2.5Z"/>
              <path d="m18 13 0.8 2.2L21 16l-2.2.8L18 19l-0.8-2.2L15 16l2.2-.8L18 13Z"/>
              <path d="m17 3 .4 1.1L18.5 4.5l-1.1.4L17 6l-.4-1.1-1.1-.4 1.1-.4L17 3Z"/>
            </svg>
            <svg v-else-if="item.panel === 'mcp'" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" fill-rule="evenodd" xmlns="http://www.w3.org/2000/svg"><title>ModelContextProtocol</title>
              <path d="M15.688 2.343a2.588 2.588 0 00-3.61 0l-9.626 9.44a.863.863 0 01-1.203 0 .823.823 0 010-1.18l9.626-9.44a4.313 4.313 0 016.016 0 4.116 4.116 0 011.204 3.54 4.3 4.3 0 013.609 1.18l.05.05a4.115 4.115 0 010 5.9l-8.706 8.537a.274.274 0 000 .393l1.788 1.754a.823.823 0 010 1.18.863.863 0 01-1.203 0l-1.788-1.753a1.92 1.92 0 010-2.754l8.706-8.538a2.47 2.47 0 000-3.54l-.05-.049a2.588 2.588 0 00-3.607-.003l-7.172 7.034-.002.002-.098.097a.863.863 0 01-1.204 0 .823.823 0 010-1.18l7.273-7.133a2.47 2.47 0 00-.003-3.537z"></path><path d="M14.485 4.703a.823.823 0 000-1.18.863.863 0 00-1.204 0l-7.119 6.982a4.115 4.115 0 000 5.9 4.314 4.314 0 006.016 0l7.12-6.982a.823.823 0 000-1.18.863.863 0 00-1.204 0l-7.119 6.982a2.588 2.588 0 01-3.61 0 2.47 2.47 0 010-3.54l7.12-6.982z"></path>
            </svg>
            <svg v-else-if="item.panel === 'risk'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>
            </svg>
            <svg v-else-if="item.panel === 'jobs'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="4" width="18" height="17" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><path d="M12 14v3l2 1"/>
            </svg>
            <svg v-else-if="item.panel === 'checkpoint'" width="22" height="22" viewBox="0 0 1024 1024" fill="currentColor">
              <path d="M832 272c0-62.4-51-112.9-113.6-112-60.7.9-110 50.6-110.4 111.3-.3 52.6 35.6 96.8 84.2 109.2 14 3.6 23.8 16 24.1 30.4.5 27.3-4.4 57.4-22.3 82.5-28.7 40.3-80.7 54.9-126.6 67.8-29 8.1-50.1 10.2-68.7 12-26.4 2.6-51.4 5.1-82.6 23-6.6 3.8-13.1 8-19.2 12.6-5.3 4-12.8.2-12.8-6.4V241.3c0-12.2 6.8-23.5 17.7-28.9 37.1-18.4 62.6-56.8 62.3-101.1-.5-62.8-53.2-113.4-116-111.2C288.1 2.1 240 51.4 240 112c0 44 25.4 82.1 62.3 100.4 10.9 5.4 17.7 16.5 17.7 28.6v541.7c0 12.2-6.8 23.5-17.7 28.9-37.1 18.4-62.6 56.8-62.3 101.1.4 62.8 53.1 113.3 115.9 111.2C416 1021.9 464 972.5 464 912c0-44-25.4-82.1-62.3-100.4-10.9-5.4-17.7-16.5-17.7-28.6v-19.2c0-42 19.9-81.8 54.3-105.9 3.1-2.2 6.4-4.3 9.7-6.2 19.3-11.1 33.5-12.5 57-14.8 20.2-2 45.3-4.5 79.7-14.1 50.5-14.2 119.6-33.5 161.4-92.3 24-33.7 35.4-75 34.1-123-.2-6.9-.7-13.8-1.4-20.9-1.1-10.7 3.5-21 11.8-27.8 25.3-20.4 41.4-51.7 41.4-86.8zM304 112c0-26.5 21.5-48 48-48s48 21.5 48 48-21.5 48-48 48-48-21.5-48-48zm96 800c0 26.5-21.5 48-48 48s-48-21.5-48-48 21.5-48 48-48 48 21.5 48 48zm320-592c-26.5 0-48-21.5-48-48s21.5-48 48-48 48 21.5 48 48-21.5 48-48 48z"/>
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
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

type Panel = 'files' | 'skill' | 'mcp' | 'native_tools' | 'checkpoint' | 'risk' | 'jobs'

defineProps<{ activePanel: Panel | null }>()

const emit = defineEmits<{ (e: 'toggle', panel: Panel): void }>()
const router = useRouter()
const { t } = useI18n()
// 用 computed 包裹:label 依赖 i18n locale,切语言时自动重算(否则只在 setup 时求值一次,切语言不刷新)
const panelItems = computed<{ panel: Panel; label: string }[]>(() => [
  { panel: 'files', label: t('activityBar.files') },
  { panel: 'skill', label: t('activityBar.skill') },
  { panel: 'mcp', label: t('activityBar.mcp') },
  { panel: 'native_tools', label: t('activityBar.nativeTools') },
  { panel: 'checkpoint', label: t('activityBar.checkpoint') },
  { panel: 'risk', label: t('activityBar.risk') },
  { panel: 'jobs', label: t('activityBar.jobs') },
])
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
