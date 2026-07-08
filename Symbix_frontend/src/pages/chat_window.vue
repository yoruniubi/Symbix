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
        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <div class="activity-btn" :class="{ active: activePanel === 'native_tools' }" @click="togglePanel('native_tools')">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
              </svg>
            </div>
          </template>
          Native Tools
        </n-tooltip>
      </div>
      <div class="activity-bar-bottom">
        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <div class="activity-btn" @click="$router.push('/model_setting')">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
              </svg>
            </div>
          </template>
          模型设置
        </n-tooltip>
      </div>
    </div>

    <!-- Sidebar Area: panels overlay the session list -->
    <div class="sidebar-container">
      <!-- Skill Panel -->
      <transition name="panel-slide">
        <div class="side-panel" v-if="activePanel === 'skill'">
          <div class="side-panel-header">
            <span class="side-panel-title">Skill 面板</span>
            <n-button text size="tiny" @click="activePanel = null" class="close-btn">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
            </n-button>
          </div>
          <div class="side-panel-body">
            <n-text depth="3" style="font-size:13px;">已安装 {{ skillList.length }} 个 Skill</n-text>
            <div v-for="skill in skillList" :key="skill.name" style="margin-top:8px; padding:8px; border-radius:8px; background:rgba(255,255,255,0.04)">
              <div style="font-size:13px; color:#c7d2fe">{{ skill.display_name }}</div>
              <div style="font-size:11px; color:#6b6b80; margin-top:2px">{{ skill.description }}</div>
            </div>
            <n-empty v-if="skillList.length === 0" description="暂无 Skill" size="small" style="margin-top:20px;" />
          </div>
          <div class="side-panel-footer">
            <n-button size="small" secondary block @click="refreshSkillList">刷新列表</n-button>
          </div>
        </div>
      </transition>

      <!-- Native Tools Panel -->
      <transition name="panel-slide">
        <div class="side-panel" v-if="activePanel === 'native_tools'">
          <div class="side-panel-header">
            <span class="side-panel-title">Native Tools 面板</span>
            <n-button text size="tiny" @click="activePanel = null" class="close-btn">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
            </n-button>
          </div>
          <div class="side-panel-body">
            <n-text depth="3" style="font-size:13px;">已注册 {{ nativeToolList.length }} 个内置工具</n-text>
            <div v-for="tool in nativeToolList" :key="tool.function.name" class="mcp-tool-item">
              <div class="mcp-tool-name">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0; margin-right:6px;">
                  <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                </svg>
                {{ tool.function.name }}
              </div>
              <div style="font-size:11px; color:#6b6b80; margin-top:2px; padding-left:20px;">{{ tool.function.description }}</div>
            </div>
            <n-empty v-if="nativeToolList.length === 0" description="暂无内置工具" size="small" style="margin-top:20px;" />
          </div>
        </div>
      </transition>

      <!-- MCP Panel -->
      <transition name="panel-slide">
        <div class="side-panel" v-if="activePanel === 'mcp'">
          <div class="side-panel-header">
            <span class="side-panel-title">MCP 面板</span>
            <n-button text size="tiny" @click="activePanel = null" class="close-btn">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
            </n-button>
          </div>
          <div class="side-panel-body">
            <div v-if="mcpConfigData" style="font-size:12px; color:#6b6b80; margin-bottom:10px;">
              已配置 {{ Object.keys(mcpConfigData.mcpServers || {}).length }} 个 MCP Server
            </div>
            <n-text depth="3" style="font-size:13px;">已注册 {{ mcpToolList.length }} 个工具</n-text>
            <div v-for="tool in mcpToolList" :key="tool.function.name" class="mcp-tool-item">
              <div class="mcp-tool-name">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0; margin-right:6px;">
                  <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                </svg>
                {{ tool.function.name }}
              </div>
              <div style="font-size:11px; color:#6b6b80; margin-top:2px; padding-left:20px;">{{ tool.function.description }}</div>
            </div>
            <n-empty v-if="mcpToolList.length === 0" description="暂无工具" size="small" style="margin-top:20px;" />
          </div>
          <div class="side-panel-footer">
            <n-button size="small" secondary block @click="testMcpConnection">测试连接</n-button>
          </div>
        </div>
      </transition>

      <!-- Session List (underneath, always present) -->
      <SessionList
        :sessions="sessions"
        :active-session="activeSession"
        @new-chat="newChat"
        @load-session="loadSession"
        @delete-session="deleteSession"
      />
    </div>

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
        <ChatMessage
          v-for="(msg, idx) in messages"
          :key="idx"
          :msg="msg"
          v-show="!(msg.role === 'assistant' && msg.content === '' && loading)"
          @edit="handleEditMessage(idx, $event)"
          @approve="approveTool(idx, $event)"
        />
        <div v-if="loading && messages[messages.length - 1]?.role === 'assistant'
            && messages[messages.length - 1]?.content === ''"
            class="loading-row">
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
        @stop="handleStopGeneration"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import TitleBar from '@/components/TitleBar.vue'
import SessionList from '@/components/SessionList.vue'
import ChatMessage from '@/components/ChatMessage.vue'
import ChatInput from '@/components/ChatInput.vue'
import { useSettings } from '@/composables/useSettings'
import { useApiClient } from '@/composables/useApiClient'
import { fetch } from '@tauri-apps/plugin-http'
const router = useRouter()
const messageUi = useMessage()
const { settings, loadSettings, saveSettings } = useSettings()
const { fetchModels, chatCompletion } = useApiClient()

const hello_list = ['今天想做些什么？', '欢迎回来！', '需要帮忙吗？', '有什么想聊的吗？', '又见面了！']
const greeting = hello_list[Math.floor(Math.random() * hello_list.length)]

interface Message { role: 'user' | 'assistant'; content: string }
interface Session { title: string; messages: Message[] }

import { useChatStore, mapBackendSteps } from '@/composables/useChatStore'
import { safeLog } from '@/utils/logMask'
const { messages, sessions, activeSession } = useChatStore()
const loading = ref(false)
const messageListRef = ref<HTMLElement | null>(null)
const abortController = ref<AbortController | null>(null)
interface Skill {
  name: string
  display_name: string
  description: string
  trigger_keywords: string[]
}

const skillList = ref<Skill[]>([])
const activePanel = ref<'skill' | 'mcp' | 'native_tools' | null>(null)
const modelOptions = ref<{ label: string; value: string }[]>([])
const currentModel = ref('gpt-4o-mini')
const mcpConfigData = ref<any>(null)
const mcpToolList = ref<{ type: string; function: { name: string; description: string; parameters: any } }[]>([])
const nativeToolList = ref<{ type: string; function: { name: string; description: string; parameters: any } }[]>([])
const hasApiKey = computed(() => !!settings.value.apiKey)

// 监听 settings 变化，同步 currentModel
watch(() => settings.value.model, (newModel) => {
  if (newModel) currentModel.value = newModel
}, { immediate: true })

onMounted(async () => {
  loadSettings()
  currentModel.value = settings.value.model || 'gpt-4o-mini'
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
async function testMcpConnection() {
  try {
    const res = await fetch('http://127.0.0.1:8000/mcp/test', {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    })
    if (res.ok) {
      const data = await res.json()
      if (data.status === 'connected') {
        messageUi.success('MCP 服务连接成功！')
      } else {
        messageUi.warning('MCP 服务返回异常状态')
      }
    } else {
      messageUi.error('无法连接到 MCP 服务 (HTTP ' + res.status + ')')
    }
  } catch (err: any) {
    console.error('MCP测试连接失败:', err)
    messageUi.error('无法连接到 MCP 服务: ' + (err.message || err))
  }
}

async function refreshSkillList() {
  try {
    const res = await fetch('http://127.0.0.1:8000/skills', {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    })
    if (res.ok) {
      const data = await res.json()
      skillList.value = data.skills || []
      messageUi.success('Skill 列表已刷新')
    } else {
      messageUi.error('获取 Skill 列表失败 (HTTP ' + res.status + ')')
    }
  } catch (err: any) {
    console.error('获取Skill列表失败:', err)
    messageUi.error('获取 Skill 列表失败: ' + (err.message || err))
  }
}
async function togglePanel(panel: 'skill' | 'mcp' | 'native_tools') {
  console.log('🟡 togglePanel called', panel)
  // 如果当前已经是激活状态，点击则是关闭，不需要请求
  if (activePanel.value === panel) {
    activePanel.value = null
    return
  }

  activePanel.value = panel

  // 根据打开的面板动态请求后端 FastAPI
  if (panel === 'skill') {
    try {
      // 对应你的 FastAPI: @app.get("/skills")
      const res = await fetch('http://127.0.0.1:8000/skills')
      const data = await res.json()
      skillList.value = data.skills
    } catch (err) {
      console.log("具体错误为：",err)
      messageUi.error('获取 Skill 列表失败')
    }
  } else if (panel === 'native_tools') {
    try {
      const res = await fetch('http://127.0.0.1:8000/native/tools')
      const data = await res.json()
      nativeToolList.value = data.tools || []
    } catch (err) {
      console.log("获取 Native Tools 列表失败:", err)
      messageUi.error('获取 Native Tools 列表失败')
    }
  } else if (panel === 'mcp') {
    try {
      const res = await fetch('http://127.0.0.1:8000/mcp/config')
      mcpConfigData.value = await res.json()
    } catch (err) {
      console.log("具体错误为：",err)
      messageUi.error('获取 MCP 配置失败')
    }
    try {
      const res = await fetch('http://127.0.0.1:8000/mcp/tools')
      const data = await res.json()
      mcpToolList.value = data.tools || []
    } catch (err) {
      console.log("获取MCP工具列表失败:", err)
    }
  }
}

function handleStopGeneration() {
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
  loading.value = false
}

function handleEditMessage(idx: number, newText: string) {
  // 截断到该消息位置，替换为新文本并重新发送
  messages.value.splice(idx)
  loading.value = false
  sendMessage(newText, [])
}

function setModel(model: string) {
  currentModel.value = model
  saveSettings({ model })
}

function newChat() {
  // 直接清空当前对话区，开始新对话；历史已由 sendMessage 首轮归档
  messages.value = []
  activeSession.value = -1
}

function loadSession(idx: number) {
  activeSession.value = idx
  messages.value = [...sessions.value[idx].messages]
  nextTick(() => scrollToBottom())
}

function deleteSession(idx: number) {
  sessions.value.splice(idx, 1)
  // 如果删除的是当前激活的会话，清空聊天区
  if (activeSession.value === idx) {
    messages.value = []
    activeSession.value = -1
  } else if (activeSession.value > idx) {
    // 索引前移
    activeSession.value -= 1
  }
}

function sendQuick(text: string) {
  sendMessage(text, [])
}

const BACKEND_URL = 'http://127.0.0.1:8000'

async function sendMessage(text: string, files: File[]) {
  console.log('=== sendMessage 开始 ===')
  safeLog('settings:', settings.value)

  let displayContent = text
  if (files.length > 0) {
    const fileNames = files.map(f => `[文件: ${f.name}]`).join(' ')
    displayContent = text ? `${fileNames}\n${text}` : fileNames
  }

  messages.value.push({ role: 'user', content: displayContent })

  // 新对话首轮：当前未激活历史 session 时，归档为新 session
  if (activeSession.value === -1) {
    const title = displayContent.slice(0, 20).replace(/[\\/:*?"<>|]/g, '') || '新对话'
    sessions.value.unshift({
      title,
      messages: [...messages.value],
    })
  }

  loading.value = true
  await nextTick()
  scrollToBottom()
  let assistantMsgIndex = -1
  try {
    assistantMsgIndex = messages.value.push({ role: 'assistant', content: '' }) - 1

    const requestBody = {
      message: displayContent,
      session_id: 'default',
      system_prompt: '',
      api_key: settings.value.apiKey || '',
      api_base: settings.value.baseUrl || '',
      model: settings.value.model || currentModel.value,
      // use_mcp: true,
    }
    safeLog('=== 请求体 ===', requestBody)

    abortController.value = new AbortController()
    const response = await fetch(`${BACKEND_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
      signal: abortController.value.signal
    })

    console.log('=== 收到响应 ===', response.status, response.ok)

    if (!response.ok) {
      throw new Error(`HTTP 错误! 状态码: ${response.status}`)
    }

    const data = await response.json()
    console.log('=== 响应数据 ===', JSON.stringify(data))

    // 兼容多种响应格式：{ content } 或 { response } 或 { message }
    const steps = mapBackendSteps(data.steps || [], data.pending_tool)

    if (data.status === 'pending_approval') {
      messages.value[assistantMsgIndex].reasoning = data.reasoning
      messages.value[assistantMsgIndex].steps = steps
      messages.value[assistantMsgIndex].approval_id = data.approval_id
      loading.value = false
      abortController.value = null
      await saveSessionToLocalMarkdown()
      return
    }

    const reply = data.content || data.response || data.message || data.text || ''
    messages.value[assistantMsgIndex].content = reply
    messages.value[assistantMsgIndex].reasoning = data.reasoning
    messages.value[assistantMsgIndex].steps = steps
    loading.value = false
    abortController.value = null
    await saveSessionToLocalMarkdown()

  } catch (e: any) {
    loading.value = false
    abortController.value = null
    if (e.name === 'AbortError') {
      console.log('=== 请求被用户中断 ===')
      // 如果中断时 assistant 消息为空，则移除
      if (assistantMsgIndex !== -1 && messages.value[assistantMsgIndex]?.content === '') {
        messages.value.splice(assistantMsgIndex, 1)
      }
      return
    }
    console.error('=== 捕获到异常 ===', e)
    if (assistantMsgIndex !== -1) {
      messages.value.splice(assistantMsgIndex, 1)
    }
    messageUi.error(`请求失败：${e.message}`)
  }
}
// 将当前 Session 保存为本地 MD 文件
async function saveSessionToLocalMarkdown() {
  if (messages.value.length === 0) return

  // 获取会话标题（首条用户消息前20个字）
  const sessionTitle = messages.value[0].content.slice(0, 20).replace(/[\\/:*?"<>|]/g, '') || 'untitled'

  try {
    await fetch(`${BACKEND_URL}/api/save_markdown`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: sessionTitle,
        // 把整个对话数组传过去
        history: messages.value.map(m => ({ role: m.role, content: m.content }))
      })
    })
    console.log('历史记录已同步保存为本地 Markdown 文件')
  } catch (err) {
    console.error('保存 MD 文件失败:', err)
  }
}
async function installMcpServer(packageName: string, serverId: string) {
  const res = await fetch('http://127.0.0.1:8000/mcp/install/npm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ package_name: packageName, server_id: serverId })
  })
  if (res.ok) {
    messageUi.success('MCP Server 安装成功')
  }
}
// 工具审批：用户在 ChatMessage 卡片点击 同意/拒绝 后回调
async function approveTool(msgIdx: number, approved: boolean) {
  const msg: any = messages.value[msgIdx]
  if (!msg || !msg.approval_id) return
  loading.value = true
  try {
    const res = await fetch(`${BACKEND_URL}/chat/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        approval_id: msg.approval_id,
        approved,
        session_id: 'default',
        api_key: settings.value.apiKey || '',
        api_base: settings.value.baseUrl || '',
        model: settings.value.model || currentModel.value,
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    const steps = mapBackendSteps(data.steps || [], data.pending_tool)

    if (data.status === 'pending_approval') {
      msg.reasoning = data.reasoning
      msg.steps = steps
      msg.approval_id = data.approval_id
      msg.content = ''
      loading.value = false
      return
    }

    msg.content = data.content || data.response || data.message || data.text || ''
    msg.reasoning = data.reasoning
    msg.steps = steps
    msg.approval_id = undefined
    loading.value = false
    await saveSessionToLocalMarkdown()
  } catch (e: any) {
    loading.value = false
    console.error('审批失败:', e)
    messageUi.error(`审批失败：${e.message}`)
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
.activity-bar-bottom {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  margin-top: auto;
  padding-bottom: 8px;
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
  transform: translateY(-15px)
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

/* ---- Sidebar Container ---- */
.sidebar-container {
  position: relative;
  flex-shrink: 0;
}

/* ---- Side Panel (Skill / MCP) ---- */
.side-panel {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 260px;
  background: rgba(20, 20, 28, 0.95);
  backdrop-filter: blur(16px);
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  z-index: 20;
  box-shadow: 4px 0 24px rgba(0, 0, 0, 0.4);
}

/* Panel slide transition */
.panel-slide-enter-active {
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.panel-slide-leave-active {
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.panel-slide-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}
.panel-slide-leave-to {
  opacity: 0;
  transform: translateX(-12px);
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
.mcp-tool-item {
  margin-top: 8px;
  padding: 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
}
.mcp-tool-name {
  font-size: 13px;
  color: #c7d2fe;
  display: flex;
  align-items: center;
}

/* ---- Side Panel Footer (固定底部按钮区) ---- */
.side-panel-footer {
  flex-shrink: 0;
  padding: 12px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
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