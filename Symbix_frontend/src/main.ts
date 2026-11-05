import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import i18n from "./i18n";
import { injectCssVariables, injectPanelIconBtnStyle, DEFAULT_THEME_MODE } from "./theme";
import { listen } from "@tauri-apps/api/event";
import { setLocale as applyI18nLocale, type AppLocale } from "./i18n";
import { installLegacyUrlRewrite, resolveBackendUrl } from "./utils/backend";
import "markstream-vue/index.css";

// Restore persisted theme before first paint (avoid flash)
function getInitialThemeMode() {
  try {
    const saved = localStorage.getItem("symbix_theme_mode");
    if (saved === "light" || saved === "dark") return saved;
  } catch {}
  return DEFAULT_THEME_MODE;
}

injectCssVariables(getInitialThemeMode());
injectPanelIconBtnStyle();


listen<AppLocale>("locale-changed", (event) => {
  applyI18nLocale(event.payload);
});

// 后端端口现在是 Rust 侧动态选定的,先把请求改写装上,再问出地址、挂载。
// (纯浏览器里 resolveBackendUrl 直接返回默认 8000,不会多等)
installLegacyUrlRewrite();

/**
 * 把桌宠主窗口从「最小化」还原出来。
 *
 * 启动方式不同(安装器「立即运行」、快捷方式,或上个会话残留),窗口交给我们时可能
 * 已经是最小化状态,tao 不会自动还原。桌宠没有标题栏,用户看到的就是「启动了但
 * 宠物不出现,点一下任务栏图标才冒出来」。
 *
 * 只对 label === "main" 生效(聊天/皮肤/弹幕窗各有自己的显隐时机)。打两发:挂载后
 * 立刻一次,再延迟一次兜住「最小化在首次 show 之后才生效」的情况。
 */
async function ensureMainWindowVisible() {
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    const win = getCurrentWindow();
    if (win.label !== "main") return;
    const reveal = async () => {
      try {
        if (await win.isMinimized()) await win.unminimize();
        await win.show();
        await win.setFocus();
      } catch (e) {
        console.warn("[window] 还原桌宠窗口失败:", e);
      }
    };
    await reveal();
    setTimeout(() => void reveal(), 800);
  } catch {
    /* 非 Tauri 环境(纯浏览器 dev)没有窗口 API */
  }
}

void (async () => {
  await resolveBackendUrl();
  createApp(App).use(router).use(i18n).mount("#app");
  void ensureMainWindowVisible();
})();