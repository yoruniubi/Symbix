# Symbix 🐾

> 一个全能的「情绪陪伴型」AI 桌宠 Agent。

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

Symbix 把 **AI Agent** 装进一只 **桌面宠物** 里:它不止是你桌面上会跳会跑的小可爱,更是一个**能自己干活**的智能体——读文件、改代码、查资料、跑命令、下载论文、写轮子、生成新皮肤……全部通过自然对话驱动,并且把每一步行为都记录成可回溯的「行为 Checkpoint」。

---

## ✨ 特性总览

### 🖥️ 桌宠
- **PixiJS 8 渲染** 的 spritesheet 桌宠,透明置顶,280×260 小窗常驻桌面
- 工作 / 休闲双模式,动作事件总线(`emit_pet_action`)驱动动画与气泡
- **pet-forge 皮肤流水线**:rig → states → mirrors → validate → pack,AI 直接生成整套桌宠皮肤
- 支持 Codex 桌宠导入,一键换肤

### 🧠 Agent 大脑
- **多 Provider 支持**:OpenAI / Anthropic / Gemini / DeepSeek / Groq / Mistral / Kimi / Qwen / 智谱 / Moonshot / xAI / OpenRouter 等 13+ 家,统一原生 httpx 驱动,**零 litellm 依赖**
- 原生 SSE 流式对话,自动适配各家协议(OpenAI / Anthropic / Gemini)
- 多轮 tool calls 循环 + 跨审批上下文累积,模型不「失忆」

### 🛠️ 工具与技能
- **内置工具**:文件读写 / 搜索替换 / 终端 / 网页抓取 / 论文搜索下载解析 / 桌宠动作……
- **三级风险审批**:SAFE 自动放行 / MEDIUM 审批 / HIGH 强制审批,可配置会话信任通道,防 AI 乱写文件
- **Skill 系统**:关键词触发 + prompt 注入 + 工具注册,支持 GitHub 一键安装 / 自定义创建
- **MCP 协议**:stdio + 远程 HTTP 双通道,支持 **OAuth 自动登录** / API Key / 面板化管理

### 🗂️ 记忆与回溯
- SQLite 持久化对话 / 摘要 / 用户画像 / 定时任务
- **行为 Checkpoint**:每一步工具调用与文件改动都留 blob 快照,AI 改错文件可一键回溯恢复
- 上下文压缩(阈值触发 AI 摘要),长对话不降智
- **Job Schedule**:cron / interval 定时任务,跑完桌宠开心跳一下

### 🔊 语音
- **STT**:SenseVoice 本地流式识别(逐句直达聊天),或云端 OpenAI 兼容 STT
- **TTS**:Edge TTS / OpenAI 兼容 TTS,句子级流式朗读

### 🌍 界面
- Vue 3 + TypeScript + Vite,naive-ui 组件库,完整的**中英双语 i18n**
- Tauri 2 桌面壳,四页面:桌宠主页 / 聊天 / 换肤 / 设置

---

## 🏗️ 架构

```
Symbix/
├── backend/                  Python FastAPI 后端
│   ├── main.py               FastAPI 入口
│   ├── application/          业务层 (routers / state / memory_ops)
│   └── Symbix_sdk/           自研 SDK
│       ├── client.py         AI 客户端(多 Provider SSE)
│       ├── memory/           记忆与上下文
│       ├── mcp/              MCP 协议支持
│       ├── tools/            工具系统
│       ├── skill/            Skill 系统 + pet-forge 皮肤生成
│       ├── checkpoint/       行为回溯
│       ├── stt/ tts/         语音
│       └── ...
├── Symbix_frontend/          Vue 3 + Vite + Tauri 桌面应用
│   └── src/
│       ├── pages/            主页 / 聊天 / 换肤 / 设置
│       └── src-tauri/        Rust 桌面壳
└── AGENTS.md                 项目开发指南
```

---

## 🚀 快速开始

### 后端

```bash
cd backend
# 需要 Python 3.10+;推荐 conda
pip install -r requirements.txt
python main.py
```

### 前端

```bash
cd Symbix_frontend
npm install
npm run dev          # 浏览器开发模式
npm run tauri dev    # Tauri 桌面应用
```

### 配置模型

在聊天界面左侧 Model Setting 面板选择 Provider(OpenAI / Anthropic / DeepSeek …),
填入 API Key 即可开始对话;支持自定义中转 base_url,可走任意 OpenAI 兼容网关。

---

## 📚 文档

- [`当前已实现的功能.md`](当前已实现的功能.md) — 追踪项目完成度的功能清单(持续更新)
- [`AGENTS.md`](AGENTS.md) — 项目结构 / 代码规范 / Agent 开发指南

---

## 🧩 规划中

- 更多桌宠交互(全局手势拖拽、桌面碰撞弹跳)
- 多语言模型切换与上下文缓存
- Team 记忆共享 / 多 Agent 协作
- 插件市场(皮肤 + Skill 一键分发)

---

## 🙏 致谢

- [PixiJS](https://pixijs.com/) — 桌宠渲染引擎
- [Tauri](https://tauri.app/) — 跨平台桌面壳
- [naive-ui](https://www.naiveui.com/) — Vue 组件库
- [FastAPI](https://fastapi.tiangolo.com/) — 后端框架
- [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) — 本地语音识别

---

**Symbix — 让 AI 陪你生活,也替你干活。** 🐾