<template>
  <n-config-provider :theme="darkTheme">
    <n-message-provider :container-style="{ top: '48px' }">
      <router-view />
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { darkTheme } from 'naive-ui'
</script>

<style>
html, body, #app {
  background: transparent !important;
  color: white;
  margin: 0;
  padding: 0;
  overflow: hidden;
}

/* 调整 Naive UI message 位置，避免被 TitleBar 遮挡 */
.n-message-container {
  top: 48px !important;
}
</style>
