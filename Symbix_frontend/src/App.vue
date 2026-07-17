<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="themeOverrides">
    <n-message-provider :container-style="{ top: '48px' }">
      <router-view />
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useTheme } from '@/composables/useTheme'

const { naiveTheme, themeOverrides, initTheme } = useTheme()

onMounted(() => {
  // Re-apply persisted mode so CSS vars + Naive stay in sync
  initTheme()
})
</script>

<style>
html, body, #app {
  background: transparent !important;
  color: var(--text-primary);
  margin: 0;
  padding: 0;
  overflow: hidden;
  font-family: var(--font-sans, "Inter", -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif);
}

/* Smooth theme transition for major surfaces */
html {
  transition: color-scheme 0.2s ease;
}

/* 调整 Naive UI message 位置，避免被 TitleBar 遮挡 */
.n-message-container {
  top: 48px !important;
}
</style>
