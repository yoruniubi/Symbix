# Symbix 🐾

<p align="center">
  <img src="Symbix_frontend/public/logo/logo.png" alt="Symbix Logo" width="200"/>
</p>

> 一个全能的「情绪陪伴型」AI 桌宠 Agent —— 它陪你聊天,也替你干活。

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

Symbix 把 **AI Agent** 装进一只 **桌面宠物** 里:它不止是你桌面上会跳会跑的小可爱,更是一个**能自己干活**的智能体——读文件、改代码、查资料、跑命令、下论文、排定时任务、生成新皮肤…… 全部通过自然对话驱动,并且把每一步行为都记录成可回溯的「行为 Checkpoint」。

**技术形态**:Tauri 2 桌面壳(Vue 3 + TypeScript + PixiJS 渲染桌宠,透明窗口 / 鼠标穿透 / 多窗口)+ FastAPI 后端 + 自研 Python Agent SDK(工具调用 / 记忆 / 技能 / MCP / 定时任务)。**所有对话与记忆都留在本地。**

---

## ✨ 核心亮点

| | |
|---|---|
| 🧠 **真 Agent 循环** | 不是「套壳聊天」:多轮工具调用 + 并行只读工具 + 子 Agent 分工 + 中断/重试/续跑 |
| 🙋 **先问再做** | 多步任务会先抛计划卡(`propose_plan`)让你确认,信息不足时抛选项式提问卡(`ask_clarifying_question`) |
| 🔒 **风险分级 + 审批** | 工具按 safe / medium / high 分级,动手前弹审批卡;也有 auto-pilot 信任指令 |
| 🗂️ **行为可回溯** | 每一步工具调用落 Checkpoint(按 `session_id + round_id`),改错文件可一键还原,新建文件可撤销 |
| 💾 **长期记忆 + 手账** | SQLite 记忆库 + RAG 检索 + 自动压缩上下文 + 每日手账,关掉再开也记得你 |
| ⏰ **定时任务** | 说人话就能建(「每天早上八点提醒我吃药」),支持周期 / 一次性、失败补偿重试、跑完自动归档 |
| 🎨 **AI 生成桌宠皮肤** | 内置 `pet-forge` 技能:给一张参考图 → 提取配色 → 生成 rig / 关键帧 / 烘焙 → 打包成可导入皮肤包 |
| 🔊 **能听会说** | 本地 SenseVoice 流式语音输入 + Edge-TTS / OpenAI 兼容 / 自建 GPT-SoVITS 朗读 |
| 🧩 **可扩展** | 31 个内置工具 + Skill 技能包 + MCP 外部工具(Playwright / 论文检索 …)一站式接入 |

---

## 🖥️ 一只活的桌宠

- 一只**常驻桌面**的透明小宠物,会动、会跳、会冒气泡跟你说话(PixiJS 逐帧/骨骼动画,rig + 关键帧 + 烘焙快照)
- **工作 / 休闲双模式**,干活时认真,摸鱼时卖萌;状态动画由 Agent 通过 `emit_pet_action` / `play_status_animation` 主动驱动
- **AI 也能帮你换皮肤**:直接描述想要的形象,它帮你生成一套新桌宠皮肤;**也支持导入 Codex 桌宠**
- **陪伴弹幕窗**:透明全屏 + 鼠标穿透,摸鱼时飘字陪伴
- **手账窗口**:每天的记忆 + AI 小巧思,像一本自动写的日记

## 🧠 一个会干活的 AI 大脑

- 内置 **9 家主流厂商预设**(OpenAI / Anthropic / Google / DeepSeek / Kimi / Grok / Qwen / GLM / Mistral),可自定义 `base_url` 接入任意 OpenAI 兼容网关
- **一边聊天一边干活**:你说需求,它自己规划并调用工具把事办完(文件 / 命令 / 网络 / 文档 / 技能 …)
- **会分工的子 Agent**:复杂任务先派子 Agent 分头查代码 / 分析 / 设计 / 审查(只读探索,多路并行),再自己汇总落地;子 Agent 可单独配置模型
- **两种行动模式**:`reactive`(直接干活)与 `plan_solve`(先列待办清单并征求确认)
- **长对话不失忆**:上下文自动压缩 + 记忆持久化 + RAG 检索,聊再久也记得你
- **上游抖动兜得住**:429 / 5xx / 断线自动重试(指数退避 + `Retry-After`),整轮重来而不是把半截答案丢给你
- **模型视觉三态探测**:支持视觉 → 直接看图;确认不支持 → 取色降级 + 明确告知模型「图没进来」;探测失败(限流/网络)→ 不再误判并缓存

### 🧰 内置工具(31)

<details>
<summary>点开看全部工具</summary>

**文件与代码**:`read_file` `create_file` `edit_file` `search_and_replace` `list_files` `search_files` `search_file_with_name` `parse_file` `open_terminal`

**文档转换**:`doc_to_markdown` `doc_to_markdown_file` `md_to_docx` `md_to_pdf` `md_to_pptx` `md_to_xlsx`

**网络**:`search_online` `fetch_webpage` `download_file`

**记忆**:`save_memory` `search_memories`

**定时任务**:`create_schedule_job` `list_schedule_jobs` `cancel_schedule_job`

**Agent 协作与交互**:`delegate_task` `delegate_tasks` `check_agent_status` `propose_plan` `ask_clarifying_question`

**桌宠与技能**:`emit_pet_action` `play_status_animation` `create_skill`

外加 Skill 技能包(如 `pet-forge` 生成桌宠)与 MCP 外部工具,统一注册进同一张表,按风险通道分流。

</details>

## 🛡️ 安全与可控

- **风险分级**:每个工具标注 `risk_channel`(read / write / execute …)与风险等级,medium / high 操作弹审批卡,`safe` 只读工具允许并行执行(最多 6 路)
- **auto-pilot 信任指令**:确认一次后可对某类操作免打扰,可随时收回
- **本地边界硬拦**:`browser_*` 等外部工具收到本地路径或 `file://` 时直接返回指引,不会真的去开浏览器
- **失败必留痕**:后台任务(定时任务 / 子 Agent)异常绝不静默——落历史 + 发通知
- **会话级文件隔离**:上传文件随会话删除而清理,不同会话互不干扰

## 🗂️ 干过的活都能找回

- **行为回溯**:每一步工具调用与整轮总结落库(Checkpoint),可查看、可还原到任意一步
- **文件级撤销**:还原会算出新增/修改/删除的文件集,新建文件也能撤掉
- **聊天记忆**:对话、记忆、手账都存在本地 SQLite,关掉再开不丢
- **定时任务**:每天定点提醒 / 干活;一次性任务跑完自动标记「已完成」,失败自动补偿重试一次

## 🔊 能听会说

- **语音输入**:张嘴说就行,本地 **SenseVoice.cpp** 流式识别(也支持 OpenAI 兼容云端 STT)
- **语音朗读**:**Edge-TTS** / OpenAI 兼容 TTS / **自建 GPT-SoVITS**(自定义 GET 接口,可配多个地址轮询),支持句子级流式朗读;设置页一个总开关,跨窗口同步(聊天窗口与桌宠窗口同时生效)

## 🌍 处处贴心

- 桌面窗口(Windows / macOS / Linux)+ 完整**中英双语**(i18n,双语键位一致)
- **多窗口各司其职**:桌宠主页 / 聊天 / 换肤 / 设置 / 弹幕 / 手账
- **设置齐全**:语言与界面、系统提示词预设、TTS / STT、模型与供应商、工具风险与信任规则

---

## 🏗️ 技术架构

```
┌──────────────────────────── Tauri 2 桌面壳 ────────────────────────────┐
│  Vue 3 + TS + naive-ui          │            PixiJS                  │
│  聊天 / 设置 / 换肤 / 手账        │   桌宠形象 · 状态动画 · 弹幕窗        │
└───────────────────────────────┬────────────────────────────────────────┘
                                │ HTTP / SSE(流式事件:token / 工具 / 审批 / 重试)
┌───────────────────────────────▼────────────────────────────────────────┐
│                        FastAPI 后端(application/)                     │
│  routers: chat(stream / approve / helpers)· sessions · files · pet     │
│           skills · mcp · jobs · journal · voice · checkpoint · risk    │
│  services: memory_ops · danmaku · pet_action                           │
└───────────────────────────────┬────────────────────────────────────────┘
                                │
┌───────────────────────────────▼────────────────────────────────────────┐
│                     Symbix Agent SDK(Symbix_sdk/)                      │
│  client(Agent 循环 / 流式 / 系统提示)   tools(注册表 · 风险分级 · 并行)   │
│  act_mode(reactive / plan_solve)       checkpoint(行为回溯 · 文件还原)   │
│  memory(SQLite · RAG · 压缩)           job_schedule(APScheduler · 人话时间)│
│  skill(技能加载 / 安装 / 生成)          mcp(stdio + remote / OAuth)      │
│  stt(SenseVoice · OpenAI 兼容)          tts(Edge / OpenAI / 自建)       │
│  retry_policy · model_capabilities · color_extract                     │
└───────────────────────────────┬────────────────────────────────────────┘
                                │ OpenAI 兼容协议
                     ┌──────────▼──────────┐
                     │  LLM 网关 / 中转站   │
                     └─────────────────────┘
```

## 📁 项目结构

```
Symbix/
├── backend/
│   ├── main.py                 # FastAPI 入口(默认 127.0.0.1:8000)
│   ├── application/            # 后端服务层:routers + services + schemas
│   └── Symbix_sdk/             # Agent SDK:client / tools / memory / skill / mcp / job_schedule …
└── Symbix_frontend/
    ├── src/pages/              # Home(桌宠)· chat_window · Setting · SkinWindow · DanmakuWindow · JournalWindow
    ├── src/components/         # ChatInput / ChatMessage / SessionList / panels(工具·风险·Checkpoint·技能·MCP·定时任务)
    ├── src/composables/        # 对话、设置、朗读、桌宠联动、i18n
    ├── public/                 # 皮肤与图标资源
    └── src-tauri/              # Tauri 配置与权限
```

---

## 🚀 快速开始

### 后端

```bash
cd backend
# 需要 Python 3.10+;推荐 conda 虚拟环境
pip install fastapi uvicorn httpx pydantic apscheduler pillow markitdown \
  python-docx openpyxl python-pptx pypdf fpdf2 edge-tts jieba rank-bm25 \
  jsonschema markdown-it-py mcp ddgs cairosvg pyyaml
python main.py           # 默认 http://127.0.0.1:8000
```

> 仓库暂未附带 `requirements.txt`,按上面的列表安装即可(缺什么补什么)。

### 前端

```bash
cd Symbix_frontend
npm install
npm run dev          # 浏览器开发模式
npm run tauri dev    # Tauri 桌面应用
```

### 配置模型

在聊天界面左侧 Model Setting 面板选择 Provider(OpenAI / Anthropic / DeepSeek …),
填入 API Key 即可开始对话;支持自定义中转 `base_url`,可走任意 OpenAI 兼容网关。

关于 STT 模型,本项目支持 OpenAI 兼容的 STT 云端 API 调用,
如果想要免费的 STT 渠道:https://groq.com/

关于 TTS 模型,本项目支持 Edge TTS 直接调用,同时也支持 OpenAI 兼容的 TTS 云端 API 调用,以及自建 TTS 的 API 调用
(自建方式二选一:OpenAI 兼容的 `/audio/speech`,或「自定义 TTS」——GET `?text=&speaker=&speed=` 直接返回音频字节,
适配 GPT-SoVITS 等本地一键包,设置页可填多个地址轮询使用)

---

## 📸 界面截图

<!-- 截图待补 -->

### 主界面

### 桌宠皮肤界面

### 设置界面

### 聊天界面

### 模型设置界面

---

## 📚 文档

- [`当前已实现的功能.md`](./当前已实现的功能.md) —— 按版本积累的功能变更与踩坑记录(含根因分析与验证方式),也是本项目的开发日志
- 在应用内「工具风险」面板可查看全部工具的风险分级与信任规则;「Checkpoint」面板可回溯历史行为

---

## 🙏 致谢

- [PixiJS](https://pixijs.com/) — 桌宠渲染引擎
- [Tauri](https://tauri.app/) — 跨平台桌面壳
- [naive-ui](https://www.naiveui.com/) — Vue 组件库
- [FastAPI](https://fastapi.tiangolo.com/) — 后端框架
- [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) — 本地语音识别

---

## 🔗 友情链接

- [linux do 社区](https://linux.do) — 新的理想社区

**Symbix — 让 AI 陪你生活,也替你干活。** 🐾
