/* Symbix landing page — English copy.
 *
 * Mirrors the key structure of zh-CN.js one-to-one. Array indices go straight
 * into data-i18n, e.g. data-i18n="features.items.3.t".
 *
 * Entries containing <em> / <br> are applied via data-i18n-html; everything
 * else via data-i18n (textContent only).
 */
(function () {
    window.SYMBIX_I18N = window.SYMBIX_I18N || {};
    window.SYMBIX_I18N['en'] = {
        meta: {
            title: "Symbix — the AI desktop pet that chats with you and does the work",
            description: "Symbix is an AI desktop pet that actually ships work: hand it papers and reports and it searches, reads closely, digests, and returns a finished, formatted document. Everything runs locally — your chats and memories never leave your machine."
        },
        nav: {
            pipeline: 'How it works',
            features: 'Highlights',
            preview: 'Screenshots',
            download: 'Download',
            downloadBtn: 'Download',
            themeToDark: 'Switch to dark mode',
            themeToLight: 'Switch to light mode',
            langToggle: 'Switch language'
        },
        hero: {
            titleHtml: 'A <em>desktop pet</em> that chats with you<br>An <em>agent</em> that does the work',
            sub: "Drop in a pile of papers, reports and spreadsheets — it searches, reads them closely, digests them, and hands back a finished document with proper formatting. Driven entirely by natural conversation, with every step logged, reviewable and undoable.",
            ctaDownload: 'Download free',
            ctaGithub: 'GitHub repo'
        },
        badges: [
            'Windows x64',
            'macOS Apple Silicon',
            'Linux x64',
            'Chinese & English',
            '100% local data'
        ],
        pipeline: {
            title: 'One sentence. The whole pipeline runs unattended.',
            sub: '“Summarize recent work on X” — you just state the goal and pick a format',
            steps: [
                { name: 'Find', desc: 'Searches academic databases; parallel agents skim in tandem and filter out the irrelevant' },
                { name: 'Fetch', desc: 'Pulls down the original PDFs — login walls included' },
                { name: 'Read', desc: 'Reads body text and tables section by section; OCR as the fallback for scans' },
                { name: 'Write', desc: 'Produces a structured review with every comparison table present' },
                { name: 'Deliver', desc: 'Hands over finished Word / PPT / Excel / PDF files' }
            ]
        },
        features: {
            title: 'More than a cute little thing hopping around your desktop',
            sub: 'Companion and worker, rolled into one',
            items: [
                { t: 'Deliverables, not just answers', d: 'You get properly formatted Word / PPT / Excel / PDF that are ready to send the moment you receive them.' },
                { t: 'Any format in, any format out', d: 'Papers, reports, spreadsheets and lecture notes are all readable, with OCR as a fallback for scanned PDFs. Converting to another format is one sentence away.' },
                { t: 'An agent that delegates', d: 'For complex jobs it dispatches several sub-agents in parallel, then merges the results — not a single-threaded chatbot.' },
                { t: 'Asks first, acts later', d: 'Multi-step tasks arrive as a plan you approve first; anything that writes pops an approval card, while pure reads run on their own. Find confirmations annoying? Turn on auto-pilot and it is green lights all the way.' },
                { t: 'Everything it did is recoverable', d: 'Every step is logged, and the diff shows exactly what changed at a glance; one click restores a bad edit, and even newly created files can be rolled back.' },
                { t: 'Every tool call in plain sight', d: 'Which tool was called, what went in, what came back, how long it took and why it failed — all laid out in the chat stream. No black box: when something breaks you debug from what you see.' },
                { t: 'It remembers you', d: 'Long-term memory plus a daily journal. Close it and reopen it and it is still the same one — no briefing it from scratch every time.' },
                { t: 'Scheduled jobs in plain language', d: '“Remind me to take my pills at 8 every morning” simply works; failed runs retry automatically and notify you.' },
                { t: 'It can reskin itself', d: 'Describe the look you want and it draws the character, builds the animations and packs them into an importable desktop-pet skin.' },
                { t: 'Costs at a glance', d: 'Token usage for every turn shown in real time, with daily / weekly / monthly totals in a single chart.' },
                { t: 'It listens and speaks', d: 'Speech recognition runs on your own machine — no network, no uploads. Read-aloud streams sentence by sentence.' },
                { t: 'No ceiling on capability', d: '31 built-in tools plus skill packs and MCP integrations — whatever you plug in is what it becomes.' },
                { t: 'It comes to you first', d: 'It will start a conversation unprompted and half the time digs through your memories to bring up the past. Click the bubble to jump straight into chat — it speaks first, you take it from there.' },
                { t: 'A desktop pet, not a web page', d: 'Always on your desktop, transparent and click-through, hopping, running and popping up bubbles to keep you company.' }
            ]
        },
        preview: {
            title: 'See what it looks like',
            sub: 'Pet, chat, danmaku overlay, journal — real windows that live on your desktop',
            shots: [
                {
                    alt: 'Symbix main view animation: the pet moving around the desktop while the chat window handles a task',
                    cap: 'Main view: the pet stays on your desktop — give it a task in one sentence and the finished file comes straight back'
                },
                {
                    alt: 'Tool calls in plain sight: tool names, arguments, results, durations and failure reasons all shown in the chat stream',
                    cap: 'Tool calls in plain sight: which tool, what went in, what came back, why it failed — debug straight from the chat'
                },
                {
                    alt: 'Chat window: streaming conversation, tool execution steps and approval cards',
                    cap: 'Chat window: streaming replies with every tool call visible'
                },
                {
                    alt: 'Companion danmaku overlay: transparent full-screen drifting text and proactive chat bubbles',
                    cap: 'Companion overlay: transparent and click-through — it comes looking for you when idle'
                },
                {
                    alt: 'Skin studio: manage the pet’s appearance and animations',
                    cap: 'Skin studio: describe the look you want and it draws it for you'
                },
                {
                    alt: 'Journal tab: what it remembered today, plus AI’s little touches',
                    alt2: 'Memory store tab: every memory grouped as constraints / personal info / project memory, and searchable',
                    cap: 'Journal + memory store: it remembers what happened between you two — browsable and searchable'
                },
                {
                    alt: 'Activity timeline panel: every step logged and reviewable',
                    cap: 'Activity timeline: every step of the work logged, one-click rollback'
                },
                {
                    alt: 'Tool risk panel: tune the approval policy to your liking',
                    cap: 'Tool risk panel: you decide what runs automatically and what asks first'
                }
            ]
        },
        download: {
            title: 'Download',
            sub: 'Install and go — speech models and the runtime are bundled in',
            th1: 'Platform',
            th2: 'Installer',
            th3: 'Local speech recognition',
            unsupported: 'Not supported'
        },
        arch: {
            title: 'Runs on your own machine',
            sub: 'All conversations and memories stay local — Tauri 2 shell + FastAPI backend + in-house Agent SDK',
            layers: [
                { name: 'Tauri 2 shell', desc: 'Vue 3 + TypeScript + naive-ui · PixiJS-rendered pet · transparent windows / click-through / multi-window' },
                { name: 'FastAPI backend', desc: 'streaming chat · approval cards · sessions · checkpoints · scheduled jobs · voice' },
                { name: 'Symbix Agent SDK', desc: 'agent loop · 31 tools · risk tiers · memory RAG · skills · MCP · OCR fallback' },
                { name: 'Local data', desc: 'SQLite memories and journal · activity timeline · one-click rollback' }
            ]
        },
        final: {
            title: 'Let AI keep you company — and do the work.',
            sub: 'Free and open source, MIT licensed.',
            ctaDownload: 'Download now',
            ctaSource: 'View source'
        }
    };
})();
