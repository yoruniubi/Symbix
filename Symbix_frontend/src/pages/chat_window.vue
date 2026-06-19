<template>
  <div class="layout">
    <TitleBar />

    <!-- VSCode-style Activity Bar -->
    <div class="activity-bar">
      <div class="activity-bar-top">
        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <div class="activity-btn" :class="{ active: activePanel === 'skill' }" @click="togglePanel('skill')">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2"></polygon>
                <line x1="12" y1="22" x2="12" y2="15.5"></line>
                <polyline points="22 8.5 12 15.5 2 8.5"></polyline>
              </svg>
            </div>
          </template>
          Skill
        </n-tooltip>
        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <div class="activity-btn" :class="{ active: activePanel === 'mcp' }" @click="togglePanel('mcp')">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
                <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
                <line x1="6" y1="6" x2="6.01" y2="6"></line>
                <line x1="6" y1="18" x2="6.01" y2="18"></line>
              </svg>
            </div>
          </template>
          MCP
        </n-tooltip>
      </div>
    </div>

    <!-- Skill Panel -->
    <div class="side-panel" v-if="activePanel === 'skill'">
      <div class="side-panel-header">
        <span class="side-panel-title">Skill 面板</span>
        <n-button text size="tiny" @click="activePanel = null" class="close-btn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </n-button>
      </div>
      <div class="side-panel-body">
        <n-text depth="3" style="font-size:13px;">Skill 加载器 - 管理你的 AI 能力扩展</n-text>
        <n-button size="small" secondary style="margin-top:12px;" block>刷新 Skill 列表</n-button>
      </div>
    </div>

    <!-- MCP Panel -->
    <div class="side-panel" v-if="activePanel === 'mcp'">
      <div class="side-panel-header">
        <span class="side-panel-title">MCP 面板</span>
        <n-button text size="tiny" @click="activePanel = null" class="close-btn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </n-button>
      </div>
      <div class="side-panel-body">
        <n-text depth="3" style="font-size:13px;">MCP 连接器 - 管理工具和资源</n-text>
        <n-button size="small" secondary style="margin-top:12px;" block>测试连接</n-button>
      </div>
    </div>

    <!-- Session List -->
    <SessionList
      :sessions="sessions"
      :active-session="activeSession"
      @new-chat="newChat"
      @load-session="loadSession"
    />

    <!-- Main Chat Area -->
    <div class="chat-area">
      <!-- Welcome Screen -->
      <div class="greeting" v-if="messages.length === 0">
        <div class="greeting-icon">
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
            <line x1="9" y1="9" x2="9.01" y2="9"/>
            <line x1="15" y1="9" x2="15.01" y2="9"/>
          </svg>
        </div>
        <h2 class="greeting-title">{{ greeting }}</h2>
        <p class="greeting-sub">Symbix Agent 随时为你服务</p>
        <div class="quick-actions">
          <n-button text class="quick-action" @click="sendQuick('帮我写一段代码')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
            帮我写一段代码
          </n-button>
          <n-button text class="quick-action" @click="sendQuick('解释一个概念')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            解释一个概念
          </n-button>
          <n-button text class="quick-action" @click="sendQuick('给我一些灵感')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            给我一些灵感
          </n-button>
        </div>
      </div>

      <!-- Message List -->
      <div class="message-list" ref="messageListRef" v-else>
        <ChatMessage v-for="(msg, idx) in messages" :key="idx" :msg="msg" />
        <div v-if="loading" class="loading-row">
          <div class="loading-bubble">
            <span class="loading-dot"></span>
            <span class="loading-dot"></span>
            <span class="loading-dot"></span>
          </div>
        </div>
      </div>

      <!-- Alert -->
      <n-alert v-if="!hasApiKey" type="warning" style="margin-bottom: 12px;" closable>
        未设置 API Key，请先配置 API 密钥
      </n-alert>

      <!-- Chat Input -->
      <ChatInput
        :loading="loading"
        :model-options="modelOptions"
        :current-model="currentModel"
        @send="sendMessage"
        @update:model="setModel"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import TitleBar from '@/components/TitleBar.vue'
import SessionList from '@/components/SessionList.vue'
import ChatMessage from '@/components/ChatMessage.vue'
import ChatInput from '@/components/ChatInput.vue'
import { useSettings } from '@/composables/useSettings'
import { useApiClient } from '@/composables/useApiClient'

const router = useRouter()
const messageUi = useMessage()
const { settings, loadSettings, saveSettings } = useSettings()
const { fetchModels, chatCompletion } = useApiClient()

const hello_list = ['今天想做些什么？', '欢迎回来！', '需要帮忙吗？', '有什么想聊的吗？', '又见面了！']
const greeting = hello_list[Math.floor(Math.random() * hello_list.length)]

interface Message { role: 'user' | 'assistant'; content: string }
interface Session { title: string; messages: Message[] }

const sessions = ref<Session[]>([])
const activeSession = ref(-1)
const messages = ref<Message[]>([])
const loading = ref(false)
const messageListRef = ref<HTMLElement | null>(null)

const activePanel = ref<'skill' | 'mcp' | null>(null)
const modelOptions = ref<{ label: string; value: string }[]>([])
const currentModel = ref(settings.value.model || 'gpt-4o-mini')

const hasApiKey = computed(() => !!settings.value.apiKey)

onMounted(async () => {
  loadSettings()
  if (settings.value.model) {
    currentModel.value = settings.value.model
  }
  // 尝试获取模型列表
  if (settings.value.apiKey && settings.value.baseUrl) {
    try {
      const models = await fetchModels(settings.value.apiKey, settings.value.baseUrl)
      modelOptions.value = models.map(m => ({ label: m, value: m }))
    } catch { /* silent */ }
  }
  if (modelOptions.value.length === 0 && currentModel.value) {
    modelOptions.value = [{ label: currentModel.value, value: currentModel.value }]
  }
})

function togglePanel(panel: 'skill' | 'mcp') {
  activePanel.value = activePanel.value === panel ? null : panel
}

function setModel(model: string) {
  currentModel.value = model
  saveSettings({ model })
}

function newChat() {
  if (messages.value.length > 0) {
    sessions.value.unshift({
      title: messages.value[0].content.slice(0, 20) || '新对话',
      messages: [...messages.value],
    })
  }
  messages.value = []
  activeSession.value = -1
}

function loadSession(idx: number) {
  activeSession.value = idx
  messages.value = [...sessions.value[idx].messages]
  nextTick(() => scrollToBottom())
}

function sendQuick(text: string) {
  sendMessage(text, [])
}

async function sendMessage(text: string, files: File[]) {
  if (!settings.value.apiKey) {
    messageUi.warning('请先在设置页面配置 API Key')
    return
  }

  // Build display content
  let displayContent = text
  if (files.length > 0) {
    const fileNames = files.map(f => `[文件: ${f.name}]`).join(' ')
    displayContent = text ? `${fileNames}\n${text}` : fileNames
  }

  messages.value.push({ role: 'user', content: displayContent })
  loading.value = true
  await nextTick()
  scrollToBottom()

  try {
    const reply = await chatCompletion(
      settings.value.apiKey,
      settings.value.baseUrl,
      currentModel.value,
      messages.value.map(m => ({ role: m.role, content: m.content }))
    )
    messages.value.push({ role: 'assistant', content: reply })
  } catch (e: any) {
    messageUi.error(`请求失败：${e.message}`)
    messages.value.push({ role: 'assistant', content: `⚠️ 请求失败：${e.message}` })
  } finally {
    loading.value = false
    await nextTick()
    scrollToBottom()
  }
}

function scrollToBottom() {
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  background: linear-gradient(160deg, #0c0c14 0%, #111118 40%, #0f0f18 100%);
  color: white;
  padding-top: 32px;
  overflow: hidden;
}

/* ---- Activity Bar (VSCode-style) ---- */
.activity-bar {
  width: 48px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  background: rgba(12, 12, 16, 0.7);
  backdrop-filter: blur(12px);
  border-right: 1px solid rgba(255, 255, 255, 0.05);
  flex-shrink: 0;
  z-index: 10;
}
.activity-bar-top {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.activity-btn {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: #85859b;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}
.activity-btn:hover {
  color: #d4d4d8;
  background: rgba(255, 255, 255, 0.06);
}
.activity-btn.active {
  color: #c7d2fe;
  background: rgba(99, 102, 241, 0.12);
}
.activity-btn.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 2px;
  background: linear-gradient(180deg, #6366f1, #a78bfa);
  border-radius: 0 2px 2px 0;
}

/* ---- Side Panel (Skill / MCP) ---- */
.side-panel {
  width: 260px;
  background: rgba(14, 14, 20, 0.8);
  backdrop-filter: blur(12px);
  border-right: 1px solid rgba(255, 255, 255, 0.05);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  z-index: 5;
  animation: slideIn 0.2s ease;
}
@keyframes slideIn {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: translateX(0); }
}
.side-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.side-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #c0c0d0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.close-btn {
  color: #6b6b80 !important;
}
.close-btn:hover {
  color: #a0a0b8 !important;
}
.side-panel-body {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}

/* ---- Chat Area ---- */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 24px 40px 32px;
  overflow: hidden;
  min-width: 0;
}

/* ---- Welcome / Greeting ---- */
.greeting {
  text-align: center;
  margin: auto;
  padding-bottom: 60px;
  display: flex;
  flex-direction: column;
  align-items: center;
  animation: fadeUp 0.5s ease;
}
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
.greeting-icon {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(167, 139, 250, 0.08));
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
  color: #818cf8;
}
.greeting-title {
  font-size: 28px;
  font-weight: 700;
  background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 50%, #a78bfa 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin: 0 0 8px;
}
.greeting-sub {
  font-size: 14px;
  color: #6b6b80;
  margin: 0 0 32px;
}
.quick-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: center;
}
.quick-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px !important;
  border-radius: 20px !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  color: #a0a0b8 !important;
  font-size: 13px !important;
  transition: all 0.2s ease;
}
.quick-action:hover {
  border-color: rgba(99, 102, 241, 0.3) !important;
  color: #c7d2fe !important;
  background: rgba(99, 102, 241, 0.06) !important;
  transform: translateY(-1px);
}

/* ---- Message List ---- */
.message-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-right: 4px;
  padding-bottom: 16px;
  scroll-behavior: smooth;
}
.message-list::-webkit-scrollbar {
  width: 5px;
}
.message-list::-webkit-scrollbar-track {
  background: transparent;
}
.message-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
}
.message-list::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.14);
}

/* ---- Loading ---- */
.loading-row {
  display: flex;
  justify-content: flex-start;
  margin: 4px 0;
}
.loading-bubble {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 18px;
  border-radius: 16px;
  border-bottom-left-radius: 4px;
  background: rgba(42, 45, 53, 0.6);
}
.loading-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #6366f1;
  animation: bounce 1.4s ease-in-out infinite;
}
.loading-dot:nth-child(1) { animation-delay: 0s; }
.loading-dot:nth-child(2) { animation-delay: 0.2s; }
.loading-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>