import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import i18n from "./i18n";
import { injectCssVariables, injectPanelIconBtnStyle, DEFAULT_THEME_MODE } from "./theme";
import { listen } from "@tauri-apps/api/event";
import { setLocale as applyI18nLocale, type AppLocale } from "./i18n";
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

createApp(App).use(router).use(i18n).mount("#app");