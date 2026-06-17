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

    <SessionList
      :sessions="sessions"
      :active-session="activeSession"
      @new-chat="newChat"
      @load-session="loadSession"
    />

    <div class="chat-area">
      <div class="greeting" v-if="messages.length === 0">
        <n-gradient-text type="primary" style="font-size: 28px; font-weight: 700;">
          {{ greeting }}
        </n-gradient-text>
        <n-text depth="3" style="margin-top: 8px; display: block;">Symbix Agent 随时为你服务</n-text>
      </div>

      <div class="message-list" ref="messageListRef">
        <ChatMessage v-for="(msg, idx) in messages" :key="idx" :msg="msg" />
        <div v-if="loading" class="loading-row">
          <div class="loading-bubble">
            <n-spin size="small" />
          </div>
        </div>
      </div>

      <n-alert v-if="!hasApiKey" type="warning" style="margin-bottom: 12px;" closable>
        未设置 API Key，请先配置 API 密钥
      </n-alert>
      <ChatInput :loading="loading" @send="sendMessage" />
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
const message = useMessage()
const { settings, loadSettings } = useSettings()
const { chatCompletion } = useApiClient()

const hello_list = ['今天想做些什么', '欢迎回来！', '需要帮忙吗？', '有什么想聊的吗', '又见面了！']
const greeting = hello_list[Math.floor(Math.random() * hello_list.length)]

interface Message { role: 'user' | 'assistant'; content: string }
interface Session { title: string; messages: Message[] }

const sessions = ref<Session[]>([])
const activeSession = ref(-1)
const messages = ref<Message[]>([])
const loading = ref(false)
const messageListRef = ref<HTMLElement | null>(null)

const hasApiKey = computed(() => !!settings.value.apiKey)
const activePanel = ref<'skill' | 'mcp' | null>(null)

onMounted(() => { loadSettings() })

function togglePanel(panel: 'skill' | 'mcp') {
  activePanel.value = activePanel.value === panel ? null : panel
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
}

async function sendMessage(text: string) {
  if (!settings.value.apiKey) {
    message.warning('请先在设置页面配置 API Key')
    return
  }
  messages.value.push({ role: 'user', content: text })
  loading.value = true
  await nextTick()
  scrollToBottom()
  try {
    const model = settings.value.model || 'gpt-4o-mini'
    const reply = await chatCompletion(
      settings.value.apiKey,
      settings.value.baseUrl,
      model,
      messages.value.map(m => ({ role: m.role, content: m.content }))
    )
    messages.value.push({ role: 'assistant', content: reply })
  } catch (e: any) {
    message.error(`请求失败：${e.message}`)
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
  background-color: rgba(16, 16, 20, 0.95);
  color: white;
  padding-top: 32px; /* 为标题栏留出空间 */
}
/* ---- Activity Bar (VSCode-style) ---- */
.activity-bar {
  width: 48px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  background: #0c0c10;
  border-right: 1px solid #2a2a2f;
  flex-shrink: 0;
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
  border-radius: 8px;
  color: #85859b;
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;
}
.activity-btn:hover {
  color: #d4d4d8;
  background: #1e1e28;
}
.activity-btn.active {
  color: #e0e0ff;
  background: #1e1e28;
}
.activity-btn.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: #6366f1;
  border-radius: 0 2px 2px 0;
}
/* ---- Chat Area ---- */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 32px 48px 24px;
  overflow: hidden;
}
.greeting {
  text-align: center;
  margin: auto;
  padding-bottom: 40px;
}
.message-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  padding-right: 4px;
  scroll-behavior: smooth;
}
.message-list::-webkit-scrollbar {
  width: 6px;
}
.message-list::-webkit-scrollbar-thumb {
  background: #3a3a42;
  border-radius: 3px;
}
.loading-row {
  display: flex;
  justify-content: flex-start;
  margin: 12px 0;
}
.loading-bubble {
  max-width: min(75%, 800px);
  padding: 12px 16px;
  border-radius: 16px;
  border-bottom-left-radius: 4px;
  background: #2a2d35;
  display: flex;
  align-items: center;
}
</style>
