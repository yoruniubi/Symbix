<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="themeOverrides">
    <n-message-provider :container-style="{ top: '48px' }">
      <n-dialog-provider>
        <ProviderBridge />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { onMounted, defineComponent, h } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { RouterView } from 'vue-router'
import { useTheme } from '@/composables/useTheme'
import type { MessageApi } from 'naive-ui'

const { naiveTheme, themeOverrides, initTheme } = useTheme()

// 把 Naive message/dialog 暴露到全局,供各 panel(ToolsRisk / JobPanel / Checkpoint)用
// window.$message / window.$dialog。这样与 useMessage()/useDialog() 同源、可被组件树外层
// (纯 JS handler)调用,消除之前 window.$message/$dialog 未定义导致的「弹窗/提示失效」。
const ProviderBridge = defineComponent({
  setup() {
    const message = useMessage()
    const dialog = useDialog()
    ;(window as any).$message = message
    ;(window as any).$dialog = dialog
    return () => h(RouterView)
  },
})

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

/* 调整 Naive UI message 位置,避免被 TitleBar 遮挡 */
.n-message-container {
  top: 48px !important;
}

/* ── Dialog 主题兜底:确保 discrete API(window.$dialog)生成的弹窗也走主题色 ──
   theme.ts 已配 Dialog override,但某些实例可能拿不到 n-config-provider 的
   theme ,这里用 CSS 变量兜底强制对齐。 */
.n-dialog {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-lg) !important;
  box-shadow: var(--shadow-md) !important;
}
.n-dialog__header {
  padding-bottom: 8px;
}
.n-dialog__title {
  color: var(--text-primary) !important;
  font-weight: 600;
}
.n-dialog__content {
  color: var(--text-secondary) !important;
}
/* 主/确认按钮 → 主题珊瑚色 */
.n-dialog__action .n-button--primary-type:not(.n-button--error-type) {
  color: #fff;
}
</style>