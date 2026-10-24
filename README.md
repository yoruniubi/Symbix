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

Symbix 把 **AI Agent** 装进一只 **桌面宠物** 里。

它不止是桌面上会跳会跑的小可爱 —— 你丢给它一堆论文、报告或表格,它能自己检索、自己精读、自己归纳,最后**交给你一份排版好的成品文件**;你也能随口说「每天早上八点提醒我吃药」,剩下的它记住。全程自然对话驱动,每一步都留痕、可回溯、可撤销。

**而且它全程在你自己的电脑上跑 —— 所有对话与记忆都留在本地。**

**技术形态**:Tauri 2 桌面壳(Vue 3 + TypeScript + PixiJS 渲染桌宠,透明窗口 / 鼠标穿透 / 多窗口)+ FastAPI 后端 + 自研 Python Agent SDK(工具调用 / 记忆 / 技能 / MCP / 定时任务)。**所有对话与记忆都留在本地。**

---

## ✨ 核心亮点

| | |
|---|---|
| 📦 **交付成品,不只是答案** | 不只是回你一段话——直接给你排好版的 **Word / PPT / Excel / PDF** 成品文件,拿到手就能发出去 |
| 🧬 **任何格式,进出自如** | 论文、报告、表格、讲义丢进来它都读得懂;想变成什么格式,一句话的事 |
| 🤖 **一句话,全流程自己跑** | 找资料 → 下载 → 精读 → 归纳 → 出稿,全程无人值守,你只管提需求和挑格式 |
| 🎭 **会分工的智能体** | 复杂任务先派多个「分身」并行推进,再汇总落地;不是单线程聊天机器人 |
| 🙋 **先问再做,不擅自动手** | 多步任务先递计划让你点头,信息不足就抛选项问你;要动手改东西时弹审批卡 |
| 🗂️ **干过的活都能找回** | 每一步都留痕,改错文件一键还原,**新建的文件也能撤销** |
| 💾 **记得住你** | 长期记忆 + 每日手账,关掉再开还是它,不用每次从头交代 |
| ⏰ **定时任务说人话就行** | 「每天早上八点提醒我吃药」它就懂,跑失败会自动重试 |
| 🎨 **能给自己换皮肤** | 描述一下想要的样子,它自己画形象、做动作、打包成能导入的桌宠皮肤 |
| 🔊 **能听会说** | 本地语音识别 + 多种朗读音色,还能接你自己的声音 |
| 🐾 **它是桌宠,不是网页** | 常驻桌面、透明穿透、会跳会跑会陪你摸鱼;陪伴与干活,同一只 |
| 🧩 **能力没有上限** | 技能包 + 外部工具随时接,接上什么它就是什么 |

---

## 📄 别的 Agent 给你答案,它给你能直接交出去的成品

> 大多数 Agent 聊完就完了:一段文字、一段代码、一屏终端输出,剩下的排版、粘贴、对齐全是你自己的事。
> Symbix 会把结果**做成一封可以直接发出去的文件**。

一句「帮我整理 XX 方向的近期工作」,它会自己去检索论文、下载原文、逐篇精读,再**交给你一份排版好的 Word 综述 / PPT 汇报 / Excel 对比表 / PDF 终稿** —— 拿到手就能用。

### 一句话,全流程无人值守

| 环节 | 它自己做完 |
| --- | --- |
| 🔍 **找** | 上学术库检索主题论文,派多个「分身」并行速读摘要,先把不相关的筛掉 |
| ⬇️ **下** | 取回 PDF 原文;遇到登录墙、动态加载页也能翻过去 |
| 📖 **读** | 解析正文与表格,分章节精读,不会因为篇幅太长而漏掉后半篇 |
| ✍️ **写** | 汇总成结构化中文综述,该有的对比表格一个不少 |
| 📦 **交** | 直接产出 Word / PPT / Excel / PDF 成品文件 |

你要做的只是说清要什么,以及最后挑一个格式。

### 不是「格式转换器」,而是「通用桥梁」

普通工具只能单向转一下。Symbix 选择的是:**进来的任何格式先统一成一种语言,出去的任何格式都从这种语言渲染**。
于是「读懂一篇 PDF」和「写出一份 PPT」不再是两件事,而是同一条流水线上的两个动作 —— **任何格式 → 理解 → 任何格式**,而且表格结构不会被打散成一坨文字。

```
PDF 论文 ─┐                                       ┌─→ Word 速读报告
Word 报告 ─┤                                       ├─→ PPT 组会汇报
PPT 演示  ─┼─→ 统一理解 ─→ 分析·归纳·重写 ─────────┼─→ Excel 对比表
Excel 表格 ─┘                                       └─→ PDF 终稿
```

### 同一套流程,换个领域照样能用

把「论文检索」换成任意信息源,这条流水线就能复用到:**法律条文、财报研读、竞品调研、课程讲义、访谈记录、病历文献……**
凡是「资料散落在各种文档里、最后还得交一份像样的东西」的活,都是它的主场。

> **工具是它的手,而你想动嘴就够。**

## 🖥️ 一只真正住在你桌面上的宠物

- 🐾 **不是网页,是桌宠** —— 透明无边框的窗口贴在桌面上,会动、会跳、会冒气泡跟你说话,点得到也摸得着
- 🌗 **工作 / 休闲两种状态** —— 干活时一脸认真,摸鱼时专心卖萌;它会根据自己在做什么自己切换
- 🎨 **能自己换皮肤** —— 描述一下想要的样子就行;也支持导入 Codex 桌宠,把你以前的形象搬过来
- 💬 **陪伴弹幕窗** —— 全屏透明、鼠标直接穿透,不挡你干活,只在旁边飘字陪你
- 📔 **手账窗口** —— 每天的记忆 + 它自己写的小心思,像一本不用你动笔的日记

## 🧠 一个会干活、也会先问你的 AI 大脑

- 🗣️ **一边聊天一边干活**:你说需求,它自己规划、自己找工具,直到把事办成
- 🎭 **会分身**:复杂任务先派多个分身分头查代码 / 分析 / 设计 / 审查,再自己汇总落地;分身还能各自配不同模型
- 🧭 **两种做事风格**:直接开干,或者先列一份待办清单等你点头
- 🧠 **长对话不失忆**:聊再久也记得前面说过什么、做过什么,不会反复问同一个问题
- 🔄 **不半途而废**:网络抖动、服务限流都会自己重试并把整件事做完,而不是把半截答案丢给你
- 👀 **看得懂图,也敢说自己看不懂**:能看图就直接看;看不了就明说「图没进来」,绝不假装看过了
- 🔌 **用你手边现成的 API 就行**:内置 **9 家主流大模型厂商预设**,也可以接任意兼容网关

### 🧰 内置工具(31)

<details>
<summary>👀 想看它到底有多少本事(31 个工具)</summary>

**文件与代码**:`read_file` `create_file` `edit_file` `search_and_replace` `list_files` `search_files` `search_file_with_name` `parse_file` `open_terminal`

**文档转换**:`doc_to_markdown` `doc_to_markdown_file` `md_to_docx` `md_to_pdf` `md_to_pptx` `md_to_xlsx`

**网络**:`search_online` `fetch_webpage` `download_file`

**记忆**:`save_memory` `search_memories`

**定时任务**:`create_schedule_job` `list_schedule_jobs` `cancel_schedule_job`

**Agent 协作与交互**:`delegate_task` `delegate_tasks` `check_agent_status` `propose_plan` `ask_clarifying_question`

**桌宠与技能**:`emit_pet_action` `play_status_animation` `create_skill`

`pet-forge` 只是其中一个。技能包与外部工具都会统一注册进同一张能力表,**同样受审批与风险管控约束**。

</details>

## 🧩 想要的能力,没有上限

内置 **31 个工具**已经覆盖文件、命令、网络、文档、记忆、定时任务;不够的部分,两种方式随便补 —— 而且补进来的能力**与内置工具同权同审批**,不用适应第二套规则:

- 🎓 **技能包(Skill)** —— 一个文件夹就是一份「专业手册」。
  比如 `pet-forge` 你只需说一句想要什么形象,它自己走完「提取配色 → 画形象 → 生成动作 → 烘焙 → 打包」,最后递给你一套**能直接导入的桌宠皮肤**。
- 🔌 **MCP 外部能力** —— 改一行配置就能挂上。已跑通的有 **Playwright 真浏览器操作**与 **arXiv 学术论文检索**;接上之后,上面那条流水线立刻变成全自动。

> 装上什么,它就是什么:今天当论文助手,明天当浏览器操作员,后天当你的桌宠画师。

## 🛡️ 敢把电脑交给它,因为它每一步都问你

能干活的前提是**敢让它干活**。Symbix 的安全感不是一句承诺,而是一层一层拦在你前面:

- ✋ **动手前先弹审批卡** —— 改文件、跑命令这类有后果的操作,它会停下来等你点「同意」;纯读取的它自己跑
- 🕊️ **信任你的重复操作** —— 某类活你确认过几次、不想再被打断,可以给它免打扰;随时收回
- 🚧 **不越界** —— 不会偷偷去碰你没允许的目录,也拦得住「拿本地文件路径去开浏览器」这类越界行为
- 📢 **失败绝不装死** —— 后台任务(定时任务 / 分身)出错一定报出来:留下记录 + 给你发通知
- 🗑️ **上传的东西不留底** —— 会话删掉,里面的附件一起清干净,不同会话互不干扰

## 🗂️ 干过的活在哪都能找回

Agent 干活最怕的是「它到底改了什么」。所以每一步都留痕:

- 🕐 **行为时间线** —— 每一次操作、每一轮的结论都记下来,随时回看「它刚才都干了啥」
- 🔍 **改动看得懂** —— 点开就是一份 commit 风格的 diff:新增绿、删除红,带行号与增删统计,一眼看清它到底动了哪几行
- ↩️ **改错了一键还原** —— 能回到历史上任意一步,不只是回到开头
- 🧹 **连新建的文件也能撤** —— 不只是恢复旧内容,它新造出来的文件也能一并清掉
- 📚 **聊天、记忆、手账都在本地** —— 关掉再开不丢,数据不出你的机器

## 🔊 它会说话,也能听你说话

- 🎤 **张嘴就能聊** —— 语音输入默认**跑在你自己电脑上**,不联网、不上传
- 🗣️ **音色随你挑** —— 现成的多种音色,或者接你自己的声音模型;朗读是**一句一句流着念**的,不用等它整段想完
- 🔁 **所有窗口同步** —— 设置里一个总开关,聊天窗和桌宠窗同时生效

## 🌍 处处贴心

- 🪟 **三平台都能跑**(Windows / macOS / Linux),界面**中英双语**
- 🧩 **多窗口各司其职**:桌宠主页 / 聊天 / 换肤 / 设置 / 弹幕 / 手账,想开哪个开哪个
- ⚙️ **设置项齐全**:语言与界面、系统提示词、语音输入输出、模型与供应商、工具风险与信任规则

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
│  act_mode(reactive / plan_solve)       checkpoint(回溯 · diff · 还原)  │
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
# 需要 Python 3.10+(实测 3.13);推荐 conda / venv 虚拟环境
pip install -r requirements.txt
python main.py           # 默认 http://127.0.0.1:8000
```

> `requirements.txt` 是按「从 `main.py` 顺 import 图做可达性分析」实测出来的,只列真正用到的包。
> 第一部分是运行必需(12 个,含传递共 45 个),第二部分是功能插件(不装也能启动,只影响对应工具)。
> 每个包的注释里写了它为什么需要;`markitdown` 这类单价最贵的可选包也标明了取舍。

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
