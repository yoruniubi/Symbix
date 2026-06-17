<template>
  <div class="titlebar" data-tauri-drag-region>
    <div class="titlebar-title">Symbix</div>
    <div class="titlebar-buttons">
      <button class="titlebar-button minimize" @click="minimizeWindow" title="最小化">
        <svg width="12" height="12" viewBox="0 0 12 12">
          <rect x="0" y="5" width="12" height="1" fill="currentColor"/>
        </svg>
      </button>
      <button class="titlebar-button maximize" @click="toggleMaximize" title="最大化/还原">
        <svg width="12" height="12" viewBox="0 0 12 12">
          <rect x="1" y="1" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1"/>
        </svg>
      </button>
      <button class="titlebar-button close" @click="closeWindow" title="关闭">
        <svg width="12" height="12" viewBox="0 0 12 12">
          <path d="M1,1 L11,11 M11,1 L1,11" stroke="currentColor" stroke-width="1"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { getCurrentWindow } from '@tauri-apps/api/window'

const appWindow = getCurrentWindow()

async function minimizeWindow() {
  await appWindow.minimize()
}

async function toggleMaximize() {
  await appWindow.toggleMaximize()
}

async function closeWindow() {
  await appWindow.close()
}
</script>

<style scoped>
.titlebar {
  height: 32px;
  background: rgba(12, 12, 16, 0.95);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 12px;
  user-select: none;
  border-bottom: 1px solid rgba(42, 42, 47, 0.8);
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 9999;
}

.titlebar-title {
  color: #d4d4d8;
  font-size: 13px;
  font-weight: 500;
}

.titlebar-buttons {
  display: flex;
  gap: 8px;
}

.titlebar-button {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: #85859b;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
  border-radius: 4px;
}

.titlebar-button:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #d4d4d8;
}

.titlebar-button.close:hover {
  background: #e81123;
  color: white;
}
</style>