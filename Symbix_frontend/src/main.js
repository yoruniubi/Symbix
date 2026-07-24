import { createApp } from "vue";
import App from "./App.vue";
import router from "./router/index.js";
import { injectCssVariables, injectPanelIconBtnStyle, DEFAULT_THEME_MODE } from "./theme";
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

createApp(App).use(router).mount("#app");
