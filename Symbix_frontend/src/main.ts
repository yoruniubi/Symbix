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

void (async () => {
  await resolveBackendUrl();
  createApp(App).use(router).use(i18n).mount("#app");
})();