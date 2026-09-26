# Symbix 🐾

<p align="center">
  <img src="Symbix_frontend/public/logo/logo.png" alt="Symbix Logo" width="200"/>
</p>

> 一个全能的「情绪陪伴型」AI 桌宠 Agent。

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

<!-- 技术栈 -->
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.137-009688?logo=fastapi&logoColor=white)]()
[![Vue](https://img.shields.io/badge/Vue-3-42b883?logo=vue.js&logoColor=white)]()
[![TypeScript](https://img.shields.io/badge/TypeScript-7-3178C6?logo=typescript&logoColor=white)]()
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white)]()
[![Tauri](https://img.shields.io/badge/Tauri-2-24C8D8?logo=tauri&logoColor=white)]()
[![PixiJS](https://img.shields.io/badge/PixiJS-8-e11d74?logo=pixi.js&logoColor=white)]()
[![naive-ui](https://img.shields.io/badge/naive--ui-2-0080ff)]()

Symbix 把 **AI Agent** 装进一只 **桌面宠物** 里:它不止是你桌面上会跳会跑的小可爱,更是一个**能自己干活**的智能体——读文件、改代码、查资料、跑命令、下载论文、写轮子、生成新皮肤......全部通过自然对话驱动,并且把每一步行为都记录成可回溯的「行为 Checkpoint」。

---

## ✨ 它都能做什么?

### 🖥️ 一只活的桌宠
- 一只**常驻桌面**的透明小宠物,会动、会跳、会冒气泡跟你说话
- **工作 / 休闲双模式**,干活时认真,摸鱼时卖萌
- **AI 也能帮你换皮肤**:直接描述想要的形象,它帮你生成一套新桌宠皮肤;也支持导入现有桌宠

### 🧠 一个会干活的 AI 大脑
- 支持 **OpenAI / Claude / Gemini / DeepSeek 等 13+ 家模型**,随便切换
- **一边聊天一边干活**:你说需求,它自己学会调用工具把事办完,不用你手动操作
- 长对话**不失忆**:自动压缩上下文,聊再久也记得你

### 🛠️ 十八般武艺
- **文件与代码**:读文件、改代码、搜内容、跑命令,你口头说就行
- **查资料**:搜索网页、下载并解析论文,一步到位
- **技能插件(Skill)**:装一个技能它就多一门手艺,支持一键安装
- **安全防呆**:它要改你的文件前会先问你,高风险的动手会拦住让你确认,不怕乱来
- **连接更多工具(MCP)**:把外部服务接进来,扩展无限可能

### 🗂️ 干过的活都能找回
- **行为回溯**:它每一步干了什么都记着,改错文件了?一键还原
- **聊天记忆**:对话和记忆存在本地,关掉再开也不丢
- **定时任务**:让它每天定点提醒你、帮你做事

### 🔊 能听会说
- **语音输入**:张嘴说就行,本地识别飞快
- **语音朗读**:它把回答念给你听,像真人一样交流

### 🌍 处处贴心
- 桌面窗口(Windows / macOS / Linux)+ 完整**中英双语**
- **四个页面**清晰分工:桌宠主页 / 聊天 / 换肤 / 设置

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

## 🔗 友情链接
- [linux do社区](https://linux.do) — 新的理想社区


**Symbix — 让 AI 陪你生活,也替你干活。** 🐾