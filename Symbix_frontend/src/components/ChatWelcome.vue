<template>
  <div class="greeting">
    <div class="greeting-icon">
      <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
        <line x1="9" y1="9" x2="9.01" y2="9"/>
        <line x1="15" y1="9" x2="15.01" y2="9"/>
      </svg>
    </div>
    <h2 class="greeting-title">{{ greeting }}</h2>
    <p class="greeting-sub">{{ t('chatWelcome.subtitle') }}</p>
    <div class="quick-actions">
      <n-button text class="quick-action" @click="emitQuickSend(t('chatWelcome.quickCode'))">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        {{ t('chatWelcome.quickCodeLabel') }}
      </n-button>
      <n-button text class="quick-action" @click="emitQuickSend(t('chatWelcome.quickExplain'))">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        {{ t('chatWelcome.quickExplainLabel') }}
      </n-button>
      <n-button text class="quick-action" @click="emitQuickSend(t('chatWelcome.quickInspire'))">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
        {{ t('chatWelcome.quickInspireLabel') }}
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ greeting: string }>()

const { t } = useI18n()

const emit = defineEmits<{
  (e: 'quickSend', text: string): void
}>()

function emitQuickSend(text: string) {
  emit('quickSend', text)
}
</script>

<style scoped>
.greeting {
  text-align: center;
  margin: auto;
  padding-bottom: 24px;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: auto;
  animation: fade-up 0.5s var(--ease-standard, ease);
}
.greeting-icon {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: var(--accent-soft);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
  color: var(--accent-500, #EF6B6E);
}
.greeting-title {
  font-size: 24px;
  font-weight: 600;
  background: var(--symbix-gradient, linear-gradient(135deg, #F7A85B 0%, #F2657A 55%, #E85C93 100%));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin: 0 0 8px;
}
.greeting-sub { font-size: 14px; color: var(--text-secondary); margin: 0 0 32px; }
.quick-actions { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
.quick-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px !important;
  border-radius: var(--radius-full) !important;
  border: 1px solid var(--border) !important;
  color: var(--text-secondary) !important;
  font-size: 13px !important;
  transition: all var(--duration-base) var(--ease-standard);
}
.quick-action:hover {
  border-color: var(--accent-border) !important;
  color: var(--text-primary) !important;
  background: var(--accent-soft) !important;
  transform: translateY(-1px);
}
@keyframes fade-up {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
