import { defineConfig, type Plugin } from "vite";
import vue from "@vitejs/plugin-vue";
import AutoImport from "unplugin-auto-import/vite";
import Components from "unplugin-vue-components/vite";
import { NaiveUiResolver } from "unplugin-vue-components/resolvers";
import { fileURLToPath, URL } from "node:url";
import { createReadStream, readFileSync } from "node:fs";
import { stat } from "node:fs/promises";
import path from "node:path";

const host = process.env.TAURI_DEV_HOST;

/** 浏览器调试环境没有 Tauri getVersion()，用它兜底(直接读 package.json，不依赖 npm 注入的 env) */
const APP_VERSION = JSON.parse(
  readFileSync(fileURLToPath(new URL("./package.json", import.meta.url)), "utf-8")
).version as string;

// Vite 只为「启动时已登记进 publicFiles 白名单」的 public 文件提供服务,而白名单靠文件 watcher
// 增量维护。public/codex_pet 与 public/pixiv_pet 必须从 watcher 里排除(资源被运行中的 Tauri
// 应用锁住时 fs.watch 会抛 EBUSY 崩掉 dev server),于是新导入 / 新烘焙出来的桌宠皮肤永远进不了
// 白名单,请求会掉到 SPA 回退返回 index.html → 前端拿到的不是图片,桌宠加载失败。
// 这里给这两个目录补一层「直读磁盘」的静态服务:绕开白名单,也不用把目录交回 watcher。
const PET_ASSET_MIME: Record<string, string> = {
  ".webp": "image/webp",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".json": "application/json",
  ".txt": "text/plain",
};

function petAssetsPlugin(): Plugin {
  return {
    name: "symbix-pet-assets",
    configureServer(server) {
      const root = path.resolve(server.config.publicDir);
      server.middlewares.use((req, res, next) => {
        const url = (req.url || "").split("?")[0].split("#")[0];
        if (!/^\/(codex_pet|pixiv_pet)\//.test(url)) {
          return next();
        }
        let rel: string;
        try {
          rel = decodeURIComponent(url);
        } catch {
          return next();
        }
        const file = path.resolve(root, "." + rel);
        // 目录穿越保护:解析后必须仍在 public/ 内
        if (!file.startsWith(root + path.sep)) {
          return next();
        }
        stat(file)
          .then((st) => {
            if (!st.isFile()) {
              res.statusCode = 404;
              return res.end("pet asset not found");
            }
            res.setHeader("Content-Type", PET_ASSET_MIME[path.extname(file).toLowerCase()] || "application/octet-stream");
            res.setHeader("Content-Length", String(st.size));
            // 皮肤会被反复重新烘焙,禁掉缓存免得看到旧图
            res.setHeader("Cache-Control", "no-store");
            createReadStream(file).pipe(res);
          })
          .catch(() => {
            res.statusCode = 404;
            res.end("pet asset not found");
          });
      });
    },
  };
}

// https://vite.dev/config/
export default defineConfig(async () => ({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  // 浏览器调试环境没有 Tauri getVersion()，用它兜底(与 package.json 同源)
  define: {
    __APP_VERSION__: JSON.stringify(APP_VERSION),
  },
  plugins:[
    // 桌宠皮肤静态服务(必须在 Vite 内置中间件之前接入)
    petAssetsPlugin(),
    vue(),
    // 自动引入 Vue 的 API (如 ref, reactive) 和 Naive UI 的非组件 API
    AutoImport({
      imports:[
        "vue",
        {
          "naive-ui":[
            "useDialog",
            "useMessage",
            "useNotification",
            "useLoadingBar",
          ],
        },
      ],
    }),
    // 自动按需引入 Naive UI 组件 (如 <n-button>)
    Components({
      resolvers:[NaiveUiResolver()],
    }),
  ],

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      // 3. tell Vite to ignore watching `src-tauri`
      // 4. ignore `public/codex_pet` / `public/pixiv_pet` — 桌宠资源文件常被运行中的
      //    Tauri 应用锁定,fs.watch 会抛 EBUSY 导致 dev server 崩溃。静态资源无需 HMR。
      //     注意:由此产生的「新皮肤不在 publicFiles 白名单里」由 petAssetsPlugin 兜住。
      ignored: ["**/src-tauri/**", "**/public/codex_pet/**", "**/public/pixiv_pet/**"],
    },
  },
}));
