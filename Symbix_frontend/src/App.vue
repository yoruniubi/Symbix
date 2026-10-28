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
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'
import { useTheme } from '@/composables/useTheme'
import { fetchBackendStatus, onBackendStatus, applyBackendStatus, type BackendStatus } from '@/utils/backend'
import type { MessageApi } from 'naive-ui'

const { naiveTheme, themeOverrides, initTheme } = useTheme()
const { t } = useI18n()

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
// 后端进程由 Tauri 侧托管(src-tauri/src/backend.rs:资源目录里找不到就自己拉起,
// 已在跑则不插手,应用退出时收尸);前端只负责把「起不来」告诉用户。
// 后端不可用时几乎所有请求都会失败,所以这类提示不自动消失(duration: 0)。
function handleBackendStatus(status: BackendStatus) {
  console.log('[backend]', status.state, status.managed, status.detail ?? '')
  // 端口是 Rust 侧动态选的,状态里的地址才是权威值(main.ts 已问过一次,
  // 这里覆盖「状态晚于挂载才定下来」的情况)
  applyBackendStatus(status)
  const broken = status.state === 'failed' || status.state === 'missing' || status.state === 'exited'
  if (!broken) return
  const message = (window as any).$message
  if (!message) return
  const text = status.detail ? `${t('backend.failed')}:${status.detail}` : t('backend.failed')
  message.error(text, { duration: 0 })
}

onMounted(() => {
  // Re-apply persisted mode so CSS vars + Naive stay in sync
  initTheme()
  // 先主动拉一次再订阅:启动阶段的状态事件早于本组件挂载,只订阅会漏掉
  void (async () => {
    const initial = await fetchBackendStatus()
    if (initial) handleBackendStatus(initial)
    await onBackendStatus(handleBackendStatus)
  })()
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
   theme,这里用 CSS 变量兜底强制对齐。 */
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
/* preset dialog(warning/error/info/success)的图标统一用主题强调色,
   避免 warning 预设的黄色图标与主题色不一致。 */
.n-dialog__icon {
  color: var(--accent-500, #ff7a59) !important;
}
.n-dialog--error-type .n-dialog__icon {
  color: var(--error, #ef4444) !important;
}
/* 确认/取消按钮（naive preset 的 positive button 会继承 dialog type，
   warning→warning-type 黄色）。这里用直接属性 + :hover 伪类强制覆盖，
   与 theme.ts Button override 对齐（primary 珊瑚色 / default hover 珊瑚边框）。 */
.n-dialog__action .n-button--primary-type,
.n-dialog__action .n-button--warning-type,
.n-dialog__action .n-button--info-type,
.n-dialog__action .n-button--success-type {
  background-color: var(--accent-500, #ff7a59) !important;
  border-color: var(--accent-500, #ff7a59) !important;
  color: #fff !important;
}
/* 珊瑚色主按钮(安装):hover 时背景加深 + 文字变黑 */
.n-dialog__action .n-button--primary-type:not(:disabled):hover,
.n-dialog__action .n-button--warning-type:not(:disabled):hover,
.n-dialog__action .n-button--info-type:not(:disabled):hover,
.n-dialog__action .n-button--success-type:not(:disabled):hover {
  background-color: var(--accent-600, #ff6347) !important;
  border-color: var(--accent-600, #ff6347) !important;
  color: #000 !important;
}
.n-dialog__action .n-button--primary-type:not(:disabled):active,
.n-dialog__action .n-button--warning-type:not(:disabled):active,
.n-dialog__action .n-button--info-type:not(:disabled):active,
.n-dialog__action .n-button--success-type:not(:disabled):active {
  background-color: var(--accent-700, #e85a3d) !important;
  border-color: var(--accent-700, #e85a3d) !important;
  color: #000 !important;  /* 如果需要按下时也是黑字,加这行 */
}
/* 取消/默认按钮：hover 时边框变珊瑚色（与 theme.ts borderHover 一致） */
.n-dialog__action .n-button--default-type {
  border-color: var(--border, #2a2a2e) !important;
  color: var(--text-primary, #e8e8ec) !important;
}
.n-dialog__action .n-button--default-type:not(:disabled):hover {
  border-color: var(--accent-500, #ff7a59) !important;
  color: var(--accent-500, #ff7a59) !important;
}
.n-dialog__action .n-button--default-type:not(:disabled):active {
  border-color: var(--accent-600, #ff6347) !important;
}
.n-dialog__action .n-button--error-type {
  color: #fff !important;
}
</style>