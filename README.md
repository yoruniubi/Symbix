# Symbix 🐾

<p align="center">
  <img src="Symbix_frontend/public/logo/logo.png" alt="Symbix Logo" width="200"/>
</p>

<p align="center">
  <a href="README_EN.md">English</a> | <a href="#中文">中文</a>
</p>

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

<!-- 技术栈 -->
[![Python](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python&logoColor=white)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.137-009688?logo=fastapi&logoColor=white)]()
[![Vue](https://img.shields.io/badge/Vue-3-42b883?logo=vue.js&logoColor=white)]()
[![TypeScript](https://img.shields.io/badge/TypeScript-7-3178C6?logo=typescript&logoColor=white)]()
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white)]()
[![Tauri](https://img.shields.io/badge/Tauri-2-24C8D8?logo=tauri&logoColor=white)]()
[![PixiJS](https://img.shields.io/badge/PixiJS-8-e11d74?logo=pixi.js&logoColor=white)]()
[![naive-ui](https://img.shields.io/badge/naive--ui-2-0080ff)]()

---

<div id="中文">

Symbix 把 **AI Agent** 装进一只**桌面宠物**里:你说需求,它自己找工具、干完活,交给你排版好的 Word / PPT / Excel / PDF 成品文件。全程对话驱动,每步留痕、可回溯;所有对话与记忆都留在本地。

**技术形态**:Tauri 2 桌面壳(Vue 3 + PixiJS 渲染桌宠)+ FastAPI 后端 + 自研 Python Agent SDK(31 工具 / 记忆 / 技能 / MCP / 定时任务)。

欢迎各位提出建议和贡献
## ✨ 核心亮点

- 📦 **交付成品,不只是答案** —— 直接给你排好版的 Word / PPT / Excel / PDF,拿到手就能发出去
- 🧬 **任何格式进出自如** —— 论文、报告、表格、讲义都读得懂,扫描件 PDF 走 OCR 兜底;输出要什么格式一句话的事
- 🤖 **一句话全流程自己跑** —— 检索 → 下载 → 精读 → 归纳 → 出稿,无人值守
- 🔍 **每一步都摊开给你看** —— 调了哪个工具、入参是什么、返回了什么、耗时多久、为什么失败,全在聊天流里留痕,不是黑盒
- 🎭 **会分身的智能体** —— 复杂任务派多个分身并行推进再汇总,分身可各配不同模型
- 🙋 **先问再做** —— 多步任务先递计划等你点头;改文件、跑命令弹审批卡,纯读取的自己跑;嫌麻烦?开 auto-pilot 一路绿灯
- 🗂️ **干过的活都能找回** —— 每步留痕,diff 一眼看清;改错一键还原,新建的文件也能撤
- 💾 **记得住你** —— 长期记忆 + 每日手账,关掉再开不用从头交代
- ⏰ **定时任务说人话就行** —— 「每天早上八点提醒我吃药」它就懂,失败自动重试
- 📊 **花销一目了然** —— token 用量实时显示,日 / 周 / 月汇总图表
- 🎨 **能给自己换皮肤** —— 描述想要的样子,它自己画形象、做动作、打包导入
- 🔊 **能听会说** —— 语音识别跑在本地开销小不上传;朗读一句一句流着念
- 🧩 **能力没有上限** —— 技能包 + MCP 外部工具随时接，与内置工具同权同审批
- 📕 **生态齐全** —— 支持多种形式的MCP，包括stdio MCP以及远程MCP oauth等配置
- 💬 **会主动来找你** —— 没事搭句话,一半概率翻你的记忆聊旧事(「你之前想画的桌宠,后来呢?」);点一下气泡直接进聊天,它先开口、你来接 💛
- ☕ **温柔感做在细节里** —— 完成提示音是十几种柔和预设(轻风、晨露、余烬…),不是刺耳的"叮";界面是暖调奶油色主题,暗色模式也走暖炭色,不用冷冰冰的科技灰
- 🛡️ **审批机制随你调** —— 从严格审批到火力全开，安全边界由你决定
## 🎯 和别的 Agent 差在哪

| | 普通 Agent / 聊天机器人 | Symbix |
| --- | --- | --- |
| 结果形态 | 一段话、一屏终端输出，排版你自己来 | 排版好的 Word / PPT / Excel / PDF 成品 |
| 过程可见性 | 只知道它「想了很久」：调了哪个工具、传什么参数、为什么失败，全在黑盒里 | 工具调用全程可视：工具名 + 入参 + 出参 + 耗时 + 错误原因，出事直接对着看 |
| 动手方式 | 要么不敢动，要么不打招呼就动 | 纯读取自己跑；改文件、跑命令先弹审批卡 |
| 干错了 | 只能重来 | 每步留痕，diff 看得懂，任意一步一键还原 |
| 记性 | 关窗就忘 | 长期记忆 + 每日手账，越用越熟，还会自己翻记忆找话题 |
| 数据 | 聊天记录在云端 | 对话、记忆、附件全在本地，删会话连附件一起清 |
| 形态 | 一个网页标签页 | 常驻桌面的宠物：透明穿透、会跳会跑、能换皮 |
| 感觉 | 效率工具，用完就走 | 陪伴：完成音是轻风晨露般的柔和音，界面是暖色主题，它没事会来找你说话 |

## 🧪 能做的事，举几个例子

- 📚 丢一句「帮我整理 XX 方向的近期工作」→ 它自己检索、下载、逐篇精读（分身并行），交给你一份排版好的中文综述，对比表格一个不少
- 📁 说「把这个文件夹里的报告汇总成一页 PPT」→ 读懂全部文件，直接产出成品
- ⏰ 随口一句「每天早上八点提醒我吃药」→ 记住并准时执行，失败自动重试
- 🎨 「我想要一只蓝色像素风的小猫桌宠」→ 它自己画形象、做动作、打包成能导入的皮肤
- 🌐 「帮我盯一下这个页面，变了告诉我」→ 接上 Playwright 就是真浏览器操作

## 📸 界面速览

| 主界面 | 皮肤工作台 |
| --- | --- |
| <img src="docs/screenshots/demo.gif" width="440"> | <img src="docs/screenshots/skin-studio.png" width="440"> |

| 聊天界面 | 弹幕窗口 |
| --- | --- |
| <img src="docs/screenshots/chat.png" width="440"> | <img src="docs/screenshots/danmaku.png" width="440"> |

### 🔍 工具调用全程可视

很多 Agent 框架里你只看得见「它想了一会儿」—— 到底调了哪个工具、传了什么参数、拿回什么、为什么失败,全是黑盒,出了问题只能靠猜。Symbix 把每一步都摊在聊天流里:**工具名、入参、返回内容、耗时、成败与错误原因都留痕**,再配合行为时间线,可以逐步回溯「它当时到底干了啥」。

<img src="docs/screenshots/tool_use.png" width="620">


<details>
<summary><b>更多截图（设置 / 侧栏面板）</b></summary>

**设置界面**

| | | |
| --- | --- | --- |
| <img src="docs/screenshots/settings-general.png" width="440"> | <img src="docs/screenshots/settings-voice.png" width="440"> | <img src="docs/screenshots/settings-prompt.png" width="440"> |
| <img src="docs/screenshots/settings-model.png" width="440"> | <img src="docs/screenshots/settings-misc.png" width="440"> | |

**模型设置**

| | |
| --- | --- |
| <img src="docs/screenshots/model-setting-1.png" width="440"> | <img src="docs/screenshots/model-setting-2.png" width="440"> |

**聊天侧栏**（从上到下）

| | | | |
| --- | --- | --- | --- |
| <img src="docs/screenshots/panel-files.png" width="290"><br><sub>文件浏览器</sub> | <img src="docs/screenshots/panel-skill.png" width="290"><br><sub>Skill 管理</sub> | <img src="docs/screenshots/panel-mcp.png" width="290"><br><sub>MCP 管理</sub> | <img src="docs/screenshots/panel-native-tools.png" width="290"><br><sub>本地工具</sub> |
| <img src="docs/screenshots/panel-timeline.png" width="290"><br><sub>行为时间线</sub> | <img src="docs/screenshots/panel-risk.png" width="290"><br><sub>工具风险</sub> | <img src="docs/screenshots/panel-jobs.png" width="290"><br><sub>定时任务</sub> | |

</details>

## 🚀 快速开始

### 下载安装(推荐)

到 [Releases](../../releases) 下载安装包(安装即用,语音识别模型与运行时已打包在内):

| 平台 | 安装包 | 本地语音识别 |
| --- | --- | --- |
| Windows x64 | `.exe` | ✅ |
| macOS Apple Silicon | `.dmg` | ✅ |
| Linux x64 | `.deb` | ✅ |
| macOS Intel | 暂不支持(可从源码构建,走云端 STT) | — |

### 从源码运行

```bash
# 后端(Python 3.10+,实测 3.13)
cd backend
pip install -r requirements.txt
python main.py           # 默认 http://127.0.0.1:8000,占用时自动换邻近端口

# 前端
cd Symbix_frontend
npm install
npm run dev          # 浏览器开发
npm run tauri dev    # 桌面应用
```

> 想用本地语音识别(SenseVoice):从 Releases 资产(`assets-v1`)下载对应平台原生栈,放进 `backend/Symbix_sdk/stt/multi-platform/<平台>/`;不配置自动走云端 STT(Groq 有免费额度)。

### 配置模型

聊天界面左侧 Model Setting 面板选 Provider,填 API Key 即可。内置 9 家厂商预设,支持自定义 `base_url` 接任意 OpenAI 兼容网关。TTS 支持 Edge TTS / OpenAI 兼容 / 自建(GPT-SoVITS 等本地一键包可直连)。

## 📚 文档

- [`当前已实现的功能.md`](./当前已实现的功能.md) —— 功能变更与踩坑记录,也是开发日志
- landing page:[`docs/index.html`](./docs/index.html)(GitHub Pages)

## 🙏 致谢

- [PixiJS](https://pixijs.com/) · [Tauri](https://tauri.app/) · [naive-ui](https://www.naiveui.com/) · [FastAPI](https://fastapi.tiangolo.com/) · [SenseVoice](https://github.com/FunAudioLLM/SenseVoice)
- 友链: [linux do 社区](https://linux.do)

**Symbix — 让 AI 陪你生活,也替你干活。** 🐾

</div>

