[中文](README.md) | English

<div align="center">

**Symbix — an AI companion that lives with you, and works for you.** 🐾

</div>

---

Symbix puts an **AI Agent** inside a **desktop pet**: state what you need, and it finds the tools, does the work, and hands you a finished, formatted Word / PPT / Excel / PDF file. Everything is conversation-driven, every step is logged and reversible — and all chats and memories stay on your machine.

**Stack**: Tauri 2 desktop shell (Vue 3 + PixiJS) + FastAPI backend + a custom Python Agent SDK (31 tools / memory / skills / MCP / scheduled jobs).

## ✨ Highlights

- 📦 **Delivers finished files, not just answers** — formatted Word / PPT / Excel / PDF, ready to send
- 🧬 **Reads and writes any format** — papers, reports, spreadsheets, handouts; scanned PDFs fall back to OCR
- 🤖 **One sentence, whole pipeline** — search → download → deep-read → summarize → deliver, fully unattended
- 🎭 **Multi-agent teamwork** — complex tasks spawn parallel sub-agents, each with its own model
- 🙋 **Asks before it acts** — multi-step plans need your approval; file edits and commands pop a confirmation card; or flip on auto-pilot and let it run
- 🗂️ **Everything is traceable** — every step logged with a readable diff; undo any step, even newly created files
- 💾 **Remembers you** — long-term memory + daily journal; no re-introductions after restart
- ⏰ **Scheduled jobs in plain words** — "remind me to take my meds at 8 every morning" just works; failures auto-retry
- 📊 **Token usage at a glance** — per-round usage, daily / weekly / monthly charts
- 🎨 **Makes its own skins** — describe a look; it draws, animates, and packages an importable pet skin
- 🔊 **Listens and speaks** — local speech recognition (nothing leaves your machine); streaming sentence-by-sentence TTS
- 💬 **It comes to you** — it strikes up conversation on its own; half the time it digs up an old memory ("that pet you wanted to make — how did it go?"); click the bubble and it opens the chat, having spoken first, waiting for you 💛
- 🧩 **Extensible** — skill packs + MCP tools plug in with the same permissions and approvals as built-ins

## 🎯 What sets it apart

| | Typical agent / chatbot | Symbix |
| --- | --- | --- |
| Output | A paragraph, a terminal dump — formatting is on you | Finished, formatted Word / PPT / Excel / PDF |
| Acting | Too timid to act, or acts without asking | Read-only runs freely; edits & commands pop an approval card |
| Mistakes | Start over | Every step logged, readable diffs, undo to any point |
| Memory | Forgotten when the tab closes | Long-term memory + daily journal; grows familiar — and finds its own topics from what it remembers |
| Data | Chats live in the cloud | Chats, memory, attachments all local; deleting a session wipes its attachments |
| Form | A browser tab | A pet living on your desktop: transparent, clickable, skinnable |

## 🧪 What it can do — a few examples

- 📚 Say "catch me up on recent work in XX field" → it searches, downloads, deep-reads papers (parallel sub-agents), and hands you a formatted Chinese review with comparison tables
- 📁 Say "summarize the reports in this folder into one PPT slide deck" → it reads everything and delivers
- ⏰ Casually mention "remind me to take my meds at 8 every morning" → remembered and executed on time, with auto-retry on failure
- 🎨 "I want a blue pixel-art cat pet" → it draws the sprite, animates it, and packages an importable skin
- 🌐 "Watch this page and tell me when it changes" → with Playwright plugged in, it drives a real browser

## 📸 Screenshots

| Main UI | Skin Studio |
| --- | --- |
| <img src="docs/screenshots/demo.gif" width="440"> | <img src="docs/screenshots/skin-studio.png" width="440"> |

| Chat | Danmaku |
| --- | --- |
| <img src="docs/screenshots/chat.png" width="440"> | <img src="docs/screenshots/danmaku.png" width="440"> |

<details>
<summary><b>More screenshots (settings / side panels)</b></summary>

**Settings**

| | | |
| --- | --- | --- |
| <img src="docs/screenshots/settings-general.png" width="440"> | <img src="docs/screenshots/settings-voice.png" width="440"> | <img src="docs/screenshots/settings-prompt.png" width="440"> |
| <img src="docs/screenshots/settings-model.png" width="440"> | <img src="docs/screenshots/settings-misc.png" width="440"> | |

**Model settings**

| | |
| --- | --- |
| <img src="docs/screenshots/model-setting-1.png" width="440"> | <img src="docs/screenshots/model-setting-2.png" width="440"> |

**Chat sidebar** (top to bottom)

| | | | |
| --- | --- | --- | --- |
| <img src="docs/screenshots/panel-files.png" width="290"><br><sub>File browser</sub> | <img src="docs/screenshots/panel-skill.png" width="290"><br><sub>Skills</sub> | <img src="docs/screenshots/panel-mcp.png" width="290"><br><sub>MCP</sub> | <img src="docs/screenshots/panel-native-tools.png" width="290"><br><sub>Native tools</sub> |
| <img src="docs/screenshots/panel-timeline.png" width="290"><br><sub>Timeline</sub> | <img src="docs/screenshots/panel-risk.png" width="290"><br><sub>Tool risk</sub> | <img src="docs/screenshots/panel-jobs.png" width="290"><br><sub>Jobs</sub> | |

</details>

## 🚀 Getting Started

### Download (recommended)

Grab an installer from [Releases](../../releases) — speech models and runtimes are bundled:

| Platform | Installer | Local STT |
| --- | --- | --- |
| Windows x64 | `.exe` | ✅ |
| macOS Apple Silicon | `.dmg` | ✅ |
| Linux x64 | `.deb` | ✅ |
| macOS Intel | Not available (build from source with cloud STT) | — |

### Run from source

```bash
# Backend (Python 3.10+, tested on 3.13)
cd backend
pip install -r requirements.txt
python main.py           # http://127.0.0.1:8000, auto-falls back to a nearby port

# Frontend
cd Symbix_frontend
npm install
npm run dev          # browser dev
npm run tauri dev    # desktop app
```

> For local speech recognition (SenseVoice): download the native stack for your platform from the `assets-v1` release and place it under `backend/Symbix_sdk/stt/multi-platform/<platform>/`. Without it, cloud STT is used (Groq offers a free tier).

### Configure a model

Pick a provider in the Model Setting panel and paste your API key. 9 vendor presets built in; any OpenAI-compatible gateway works via a custom `base_url`. TTS supports Edge TTS, OpenAI-compatible APIs, and self-hosted servers (GPT-SoVITS one-click packages connect directly).

## 📚 Docs

- [`当前已实现的功能.md`](./当前已实现的功能.md) — feature changelog & engineering notes (development log, in Chinese)
- Landing page: [`docs/index.html`](./docs/index.html) (GitHub Pages)

**Symbix — an AI companion that lives with you, and works for you.** 🐾
