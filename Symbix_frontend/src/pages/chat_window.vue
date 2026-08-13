<template>
  <div class="layout">
    <TitleBar />

    <ChatActivityBar
      :active-panel="activePanel"
      @toggle="togglePanel"
    />
    <div class="sidebar-container">
      <!-- Skill Panel -->
      <SkillPanel
        :active-panel="activePanel"
        :skill-list="skillList"
        :skill-tool-list="skillToolList"
        @update:active-panel="activePanel = $event"
        @open-add-chooser="openAddChooser"
        @remove-skill="removeSkill"
        @refresh-skill-list="refreshSkillList"
      />

      <NativeToolsPanel
        :active-panel="activePanel"
        :native-tool-list="nativeToolList"
        @update:active-panel="activePanel = $event"
      />

      <McpPanel
        :active-panel="activePanel"
        :mcp-server-groups="mcpServerGroups"
        :mcp-tool-list="mcpToolList"
        :expanded-mcp-servers="expandedMcpServers"
        :mcp-status-map="mcpStatusMap"
        :refreshing="refreshingMcp"
        @update:active-panel="activePanel = $event"
        @open-add-chooser="openAddChooser"
        @toggle-mcp-server="toggleMcpServer"
        @remove-mcp="removeMcp"
        @refresh="handleMcpRefresh"
      />

      <!-- 文件浏览器:浏览本地文件 -->
      <FilePanel
        :active-panel="activePanel"
        @update:active-panel="activePanel = $event"
      />

      <!-- Session List (underneath, always present) -->
      <SessionList
        :sessions="sessions"
        :active-session-id="activeSessionId"
        @new-chat="newChat"
        @load-session="loadSession"
        @delete-session="deleteSession"
        @rename-session="renameSession"
      />
    </div>

    <!-- Main Chat Area -->
    <div class="chat-area">
      <!-- Welcome Screen -->
      <ChatWelcome
        v-if="messages.length === 0"
        :greeting="greeting"
        @quick-send="sendQuick"
      />

      <!-- Message List -->
      <div class="message-list" ref="messageListRef" v-else>
        <ChatMessage
          v-for="(msg, idx) in messages"
          :key="idx"
          :msg="msg"
          :final="!(loading && msg.role === 'assistant' && idx === messages.length - 1)"
          v-show="!(msg.role === 'assistant' && msg.content === '' && loading)"
          @edit="handleEditMessage(idx, $event)"
          @approve="approveTool(idx, $event)"
          @retry="handleRetryMessage(idx)"
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
        {{ $t('chat.noApiKey') }}
      </n-alert>

      <!-- Chat Input -->
      <ChatInput
        :loading="loading"
        :model-options="modelOptions"
        :current-model="currentModel"
        :session-id="activeSessionId"
        @send="sendMessage"
        @update:model="setModel"
        @stop="handleStopGeneration"
      />
    </div>

    <!-- 添加 Skill 弹窗:GitHub 安装 / 自定义创建 -->
    <AddSkillModal
      :show="showAddSkillModal"
      :creating="creatingSkill"
      :mode="skillAddMode"
      :form="skillForm"
      @update:show="showAddSkillModal = $event"
      @update:mode="skillAddMode = $event"
      @submit="submitCreateSkill"
    />

    <!-- 添加 MCP 弹窗:远程 URL / 本地 npm -->
    <AddMcpModal
      :show="showAddMcpModal"
      :installing="installingMcp"
      :mode="mcpAddMode"
      :form="mcpForm"
      @update:show="showAddMcpModal = $event"
      @update:mode="mcpAddMode = $event"
      @submit="submitInstallMcp"
      />

  </div>
</template>


<script setup lang="ts">
import SkillPanel from '@/components/panels/SkillPanel.vue'
import McpPanel from '@/components/panels/McpPanel.vue'
import FilePanel from '@/components/panels/FilePanel.vue'
import NativeToolsPanel from '@/components/panels/NativeToolsPanel.vue'
import ChatActivityBar from '@/components/ChatActivityBar.vue'
import { ref, computed, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { useMessage } from 'naive-ui'
import TitleBar from '@/components/TitleBar.vue'
import SessionList from '@/components/SessionList.vue'
import ChatMessage from '@/components/ChatMessage.vue'
import ChatInput from '@/components/ChatInput.vue'
import ChatWelcome from '@/components/ChatWelcome.vue'
import AddSkillModal from '@/components/AddSkillModal.vue'
import AddMcpModal from '@/components/AddMcpModal.vue'
import { useSettings } from '@/composables/useSettings'
import { useApiClient } from '@/composables/useApiClient'
import { fetch } from '@tauri-apps/plugin-http'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const messageUi = useMessage()
const { settings, loadSettings, saveSettings } = useSettings()
const { fetchModels, chatCompletion } = useApiClient()
const hello_list = [t('home.petGreeting'), t('home.petGreetingWelcome'), t('home.petGreetingHelp'), t('home.petGreetingChat'), t('home.petGreetingList')]
const greeting = hello_list[Math.floor(Math.random() * hello_list.length)]
import { useChatStore, mapBackendSteps } from '@/composables/useChatStore'
import { notifyTaskComplete } from '@/composables/useNotify'
import { safeLog } from '@/utils/logMask'
import { emit as emitTauri } from '@tauri-apps/api/event'

const { messages, sessions, activeSessionId, persistSessions, getActiveSession } = useChatStore()
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
const skillToolList = ref<any[]>([])
const activePanel = ref<'files' | 'skill' | 'mcp' | 'native_tools' | null>(null)
const modelOptions = ref<{ label: string; value: string }[]>([])
const currentModel = ref('gpt-4o-mini')
const mcpConfigData = ref<any>(null)
const mcpToolList = ref<{ type: string; function: { name: string; description: string; parameters: any } }[]>([])
const mcpServerGroups = ref<{ server_id: string; tool_count: number; tools: any[]; error?: string }[]>([])
const expandedMcpServers = ref<Set<string>>(new Set())
const nativeToolList = ref<{ type: string; function: { name: string; description: string; parameters: any } }[]>([])
const hasApiKey = computed(() => !!settings.value.apiKey)

// 添加 Skill / MCP 弹窗
const showAddSkillModal = ref(false)
const showAddMcpModal = ref(false)
const creatingSkill = ref(false)
const installingMcp = ref(false)
const skillAddMode = ref<'github' | 'custom'>('github')
const mcpAddMode = ref<'remote' | 'npm'>('remote')
const mcpStatusMap = ref<Record<string, { status: string; tools_count?: number; error?: string; transport?: string }>>({})
const refreshingMcp = ref(false)
// MCP 连接状态 5 分钟周期检测定时器（静默刷新；仅在"由 OK 变 OFFLINE"时 toast 一次）
const MCP_CHECK_INTERVAL = 5 * 60 * 1000
let mcpCheckTimer: ReturnType<typeof setInterval> | null = null
const skillForm = ref({
  skill_name: '',
  display_name: '',
  description: '',
  purpose: '',
  instructions: '',
  repo_url: '',
  branch: '',
  overwrite: false,
})
const mcpForm = ref({
  server_id: '',
  package_name: '',
  argsText: '',
  url: '',
  transport: 'sse',
  headersText: '',
})

function openAddChooser(kind: 'skill' | 'mcp') {
  if (kind === 'skill') {
    skillAddMode.value = 'github'
    showAddSkillModal.value = true
  } else {
    mcpAddMode.value = 'remote'
    showAddMcpModal.value = true
  }
}

/**
 * 静默拉取 MCP 连接状态。
 * - silent=true（定时/手动刷新默认）：不弹 toast，只在"从 connected 变成非 connected"
 *   时才 toast 一次，避免周期打扰。
 * - silent=false：复用原 toast 语义，用于首次加载出错时提示开发调试。
 */
async function refreshMcpStatus(silent = true) {
  const prevStatus: Record<string, string> = {}
  for (const [id, info] of Object.entries(mcpStatusMap.value)) {
    prevStatus[id] = info?.status || ''
  }
  try {
    const res = await fetch(`${BACKEND_URL}/mcp/test`)
    if (!res.ok) return
    const data = await res.json()
    mcpStatusMap.value = data.servers || {}
    if (silent) {
      // 仅在"由 OK 变 OFFLINE/error"时提示一次
      for (const [id, info] of Object.entries(mcpStatusMap.value)) {
        const was = prevStatus[id]
        const now: string = (info as any)?.status || ''
        if (was === 'connected' && now && now !== 'connected') {
          messageUi.warning(t('mcpPanel.silentOffline', { id }))
        }
      }
    }
  } catch {}
}

/** MCP 面板刷新按钮处理：转图标，同步刷新 server/tool 列表与状态。 */
async function handleMcpRefresh() {
  if (refreshingMcp.value) return
  refreshingMcp.value = true
  try {
    await refreshMcpPanel(false) // 手动刷新，显示 toast
  } finally {
    refreshingMcp.value = false
  }
}

async function removeMcp(serverId: string) {
  try {
    const res = await fetch(`${BACKEND_URL}/mcp/servers/${encodeURIComponent(serverId)}`, { method: 'DELETE' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
    messageUi.success(data.message || t('mcpPanel.removeSuccess', { serverId }))
    await refreshMcpPanel()
  } catch (e: any) {
    messageUi.error(t('mcpPanel.removeFail', { msg: e.message || e }))
  }
}

async function removeSkill(skillName: string) {
  try {
    const res = await fetch(`${BACKEND_URL}/skills/${encodeURIComponent(skillName)}`, { method: 'DELETE' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
    messageUi.success(data.message || t('skillPanel.deleteSuccess', { name: skillName }))
    await refreshSkillList()
  } catch (e: any) {
    messageUi.error(t('skillPanel.deleteFail', { msg: e.message || e }))
  }
}



// 监听 settings 变化,同步 currentModel
watch(() => settings.value.model, (newModel) => {
  if (newModel) currentModel.value = newModel
}, { immediate: true })

// 自动持久化 sessions 到 localStorage
watch(sessions, () => {
  persistSessions()
}, { deep: true })

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

  // 检测是否有从 SkinWindow 传来的预设皮肤生成消息
  try {
    const raw = localStorage.getItem('pendingSkinGen')
    if (raw) {
      const pending = JSON.parse(raw)
      // 5 分钟内有效,防止过期消息被重复发送
      if (pending.message && pending.ts && (Date.now() - pending.ts < 5 * 60 * 1000)) {
        localStorage.removeItem('pendingSkinGen')
        // 延迟一帧确保 ChatInput 等子组件已挂载
        setTimeout(() => {
          sendMessage(pending.message, [])
        }, 300)
      } else {
        // 过期,清理
        localStorage.removeItem('pendingSkinGen')
      }

    }
  } catch (e) {
    console.warn('[chat] 读取 pendingSkinGen 失败:', e)
  }

  // 启动 MCP 连接状态周期检测（5 分钟一次，静默刷新）
  refreshMcpStatus(true)
  mcpCheckTimer = setInterval(() => refreshMcpStatus(true), MCP_CHECK_INTERVAL)
})

onBeforeUnmount(() => {
  if (mcpCheckTimer) {
    clearInterval(mcpCheckTimer)
    mcpCheckTimer = null
  }
})
async function refreshSkillList() {
  try {
    const res = await fetch('http://127.0.0.1:8000/skills', {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    })
    if (res.ok) {
      const data = await res.json()
      skillList.value = data.skills || []
      messageUi.success(t('skillPanel.refreshSuccess'))
    } else {
      messageUi.error(t('skillPanel.fetchFail', { status: res.status }))
    }
  } catch (err: any) {
    console.error('获取Skill列表失败:', err)
    messageUi.error(t('skillPanel.fetchFailDetail', { msg: err.message || err }))
  }
  // 同时刷新 skill 工具列表
  try {
    const res = await fetch('http://127.0.0.1:8000/skills/tools')
    if (res.ok) {
      const data = await res.json()
      skillToolList.value = data.tools || []
    }
  } catch {}
}
async function togglePanel(panel: 'files' | 'skill' | 'mcp' | 'native_tools') {
  console.log('🟡 togglePanel called', panel)
  // 如果当前已经是激活状态,点击则是关闭,不需要请求
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
      console.log("具体错误为:",err)
      messageUi.error(t('skillPanel.fetchFailShort'))
    }
  } else if (panel === 'native_tools') {
    try {
      const res = await fetch('http://127.0.0.1:8000/native/tools')
      const data = await res.json()
      nativeToolList.value = data.tools || []
    } catch (err) {
      console.log("获取 Native Tools 列表失败:", err)
      messageUi.error(t('nativeToolsPanel.fetchFail'))
    }
  } else if (panel === 'mcp') {
    try {
      const res = await fetch('http://127.0.0.1:8000/mcp/config')
      mcpConfigData.value = await res.json()
    } catch (err) {
      console.log("具体错误为:",err)
      messageUi.error(t('mcpPanel.fetchConfigFail'))
    }
    try {
      const res = await fetch('http://127.0.0.1:8000/mcp/tools')
      const data = await res.json()
      mcpToolList.value = data.tools || []
    } catch (err) {
      console.log("获取MCP工具列表失败:", err)
    }
    // 按 server 分组获取 + 状态
    await refreshMcpPanel()
  }
}


function toggleMcpServer(serverId: string) {
  const s = new Set(expandedMcpServers.value)
  if (s.has(serverId)) {
    s.delete(serverId)
  } else {
    s.add(serverId)
  }
  expandedMcpServers.value = s
}
function handleStopGeneration() {
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
  loading.value = false
  publishAgentStatus('idle', t('chat.stopGenerate'))
}

function handleEditMessage(idx: number, newText: string) {
  // 截断到该消息位置,替换为新文本并重新发送
  messages.value.splice(idx)
  loading.value = false
  sendMessage(newText, [])
}

/** 重试 assistant 回复:找到对应 user 消息,截断后重新发送 */
function handleRetryMessage(idx: number) {
  if (loading.value) return
  if (idx <= 0 || messages.value[idx]?.role !== 'assistant') return

  // 向前找到触发该回复的 user 消息
  let userIdx = idx - 1
  while (userIdx >= 0 && messages.value[userIdx].role !== 'user') {
    userIdx--
  }
  if (userIdx < 0) return

  const userText = messages.value[userIdx].content
  // 从 user 消息起截断(含 assistant 及之后),由 sendMessage 重新推入
  messages.value.splice(userIdx)
  loading.value = false
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
  sendMessage(userText, [])
}

function setModel(model: string) {
  currentModel.value = model
  saveSettings({ model })
}

function newChat() {
  // 清空当前对话区;真正创建会话在首次 sendMessage 时
  messages.value = []
  activeSessionId.value = null
}

function loadSession(id: string) {
  const session = sessions.value.find(s => s.id === id)
  if (!session) return
  activeSessionId.value = id
  messages.value = [...session.messages]
  nextTick(() => scrollToBottom())
}

async function deleteSession(id: string) {
  const idx = sessions.value.findIndex(s => s.id === id)
  if (idx < 0) return
  const session = sessions.value[idx]

  sessions.value.splice(idx, 1)
  if (activeSessionId.value === id) {
    messages.value = []
    activeSessionId.value = null
  }

  // 按 session id 删除后端 Markdown
  try {
    await fetch(`${BACKEND_URL}/api/delete_markdown`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: id, title: session.title }),
    })
  } catch (err) {
    console.error('删除 MD 文件失败:', err)
  }
}

async function renameSession(id: string, newTitle: string) {
  const session = sessions.value.find(s => s.id === id)
  if (!session || !newTitle.trim()) return
  const oldTitle = session.title
  session.title = newTitle.trim()
  session.titleGenerated = true // 用户手动改过,不再自动生成
  try {
    await fetch(`${BACKEND_URL}/api/rename_session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: id, title: session.title, old_title: oldTitle }),
    })
  } catch (err) {
    console.error('重命名失败:', err)
  }
}

function sendQuick(text: string) {
  sendMessage(text, [])
}

const BACKEND_URL = 'http://127.0.0.1:8000'

type AgentStatus = 'thinking' | 'complete' | 'error' | 'idle'

function publishAgentStatus(status: AgentStatus, bubble?: string) {
  void emitTauri('agent-status', { status, bubble }).catch((error) => {
    // 浏览器开发模式没有 Tauri event 总线时,聊天本身仍应正常工作。
    console.debug('[agent-status] event unavailable:', error)
  })
}

async function sendMessage(text: string, files: any[]) {
  console.log('=== sendMessage 开始(SSE 流式)===')
  safeLog('settings:', settings.value)

  let displayContent = text
  const ready = (files || []).filter((f: any) => f && (f.path || f.name))
  if (ready.length > 0) {
    const fileNames = ready.map((f: any) => `[文件: ${f.name || f.filename || 'file'}]`).join(' ')
    displayContent = text ? `${fileNames}\n${text}` : fileNames
  }

  messages.value.push({ role: 'user', content: displayContent })

  // 新对话首轮:创建带 UUID 的 session,并激活
  if (!activeSessionId.value) {
    const newId = crypto.randomUUID()
    const title = displayContent.slice(0, 20).replace(/[\\/:*?"<>|]/g, '') || t('chat.newChatTitle')
    sessions.value.unshift({
      id: newId,
      title,
      messages: [...messages.value],
      titleGenerated: false,
    })
    activeSessionId.value = newId
  } else {
    const session = sessions.value.find(s => s.id === activeSessionId.value)
    if (session) session.messages = [...messages.value]
  }

  const currentSessionId = activeSessionId.value!

  loading.value = true
  publishAgentStatus('thinking', t('chat.thinking'))
  await nextTick()
  scrollToBottom()
  let assistantMsgIndex = -1
  try {
    assistantMsgIndex = messages.value.push({ role: 'assistant', content: '' }) - 1
    const assistantMsg = messages.value[assistantMsgIndex] as any

    const attachments = ready.map((f: any) => ({
      path: f.path || '',
      filename: f.name || f.filename || '',
      name: f.name || f.filename || '',
      mime: f.mime || f.type || '',
      type: f.mime || f.type || '',
      size: f.size || 0,
    }))
    const requestBody = {
      message: text || '',
      session_id: currentSessionId,
      system_prompt: settings.value.systemPrompt || '',
      api_key: settings.value.apiKey || '',
      api_base: settings.value.baseUrl || '',
      model: settings.value.model || currentModel.value,
      use_mcp: true,
      attachments,
    }

    abortController.value = new AbortController()
    const response = await fetch(`${BACKEND_URL}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
      signal: abortController.value.signal,
    })

    if (!response.ok) {
      const errText = await response.text()
      throw new Error(`HTTP ${response.status}: ${errText}`)
    }

    // ─── 读取 SSE 流 ────────────────────────────────────────
    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let done = false
    const steps: any[] = []
    const toolCallAcc: Record<string, string> = {} // tool-call id → args 累积

    while (!done) {
      const { value, done: readerDone } = await reader.read()
      if (readerDone) break
      buffer += decoder.decode(value, { stream: true })

      // 按行解析 SSE
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // 保留不完整的最后一行

      let currentEventType = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEventType = line.slice(7).trim()
          continue
        }
        if (line.startsWith('data: ')) {
          const dataStr = line.slice(6)
          if (dataStr === '[DONE]') {
            done = true
            break
          }
          try {
            const evt = JSON.parse(dataStr)
            handleSSEEvent(evt, currentEventType, assistantMsg, steps, toolCallAcc)
          } catch {
            // 跳过无法解析的数据
          }
          currentEventType = ''
        }
      }

      // 如果是 await_approval 之后就 break
      if (assistantMsg.approval_id) {
        done = true
        break
      }
    }

    loading.value = false
    abortController.value = null
    // 同步当前会话消息,避免侧边栏停留在旧内容
    const active = sessions.value.find(s => s.id === currentSessionId)
    if (active) active.messages = [...messages.value]
    await saveSessionToLocalMarkdown()
    // 流式结束且不在等待审批时,触发任务完成提醒
    if (!assistantMsg.approval_id) {
      publishAgentStatus('complete')
      const preview = (assistantMsg.content || '').slice(0, 80).replace(/\s+/g, ' ')
      void notifyTaskComplete({
        title: 'Symbix · 任务完成',
        body: preview || '我在这里,任务已经完成啦~',
      })

    }

  } catch (e: any) {
    loading.value = false
    abortController.value = null
    // 检查是否是用户主动中断（AbortError）
    // 兼容不同浏览器：name === 'AbortError' 或 code === 20（DOMException.ABORT_ERR）
    if (e.name === 'AbortError' || e.code === 20 || e.message?.includes('abort')) {
      console.log('=== 流被用户中断 ===')
      publishAgentStatus('idle', t('chat.stopGenerate'))
      if (assistantMsgIndex !== -1 && !messages.value[assistantMsgIndex]?.content) {
        messages.value.splice(assistantMsgIndex, 1)
      }
      return
    }
    console.error('=== 流式异常 ===', e)
    publishAgentStatus('error', t('chat.errorOccurred'))
    if (assistantMsgIndex !== -1 && !messages.value[assistantMsgIndex]?.content) {
      messages.value.splice(assistantMsgIndex, 1)
    } else if (assistantMsgIndex !== -1) {
      messages.value[assistantMsgIndex].content += `\n\n[错误] ${e.message}`
    }
    messageUi.error(t('chat.requestFail', { msg: e.message }))
  }
}


/**
 * 处理单条 SSE 事件,更新 assistant 消息。
 */
function handleSSEEvent(
  evt: any,
  eventType: string,
  msg: any,
  steps: any[],
  toolCallAcc: Record<string, string>,
) {
  const type = evt.type || eventType

  switch (type) {
    case 'delta':
      msg.content += evt.content || ''
      nextTick(() => scrollToBottom())
      break

    case 'reasoning':
      msg.reasoning = (msg.reasoning || '') + (evt.content || '')
      break

    case 'tool_call': {
      const id = evt.id || ''
      const name = evt.name || ''
      const argsChunk = evt.arguments || ''
      // 同一工具调用的参数可能跨多个 SSE 事件,按 id 聚合。
      const key = id || `name:${name}`
      if (toolCallAcc[key] === undefined) toolCallAcc[key] = ''
      toolCallAcc[key] += argsChunk

      const found = steps.find((s: any) =>
        (id && s.id === id) || (!id && s._toolKey === key),
      )
      if (found) {
        found.arguments = toolCallAcc[key]
      } else {
        steps.push({ id, _toolKey: key, name, arguments: toolCallAcc[key], status: 'pending' })
      }
      msg.steps = steps.map((s: any) => ({
        ...s,
        arguments: typeof s.arguments === 'string' ? s.arguments : JSON.stringify(s.arguments ?? {}),
      }))
      nextTick(() => scrollToBottom())
      break
    }

    case 'tool_result': {
      const target = steps.find((s: any) => s.id === evt.id)
      if (target) {
        target.result = evt.content || ''
        target.status = 'done'
      } else {
        steps.push({
          id: evt.id || '',
          name: evt.name || '(result)',
          arguments: '',
          result: evt.content || '',
          status: 'done',
        })
      }
      msg.steps = steps.map((s: any) => ({
        ...s,
        arguments: typeof s.arguments === 'string' ? s.arguments : JSON.stringify(s.arguments ?? {}),
      }))
      nextTick(() => scrollToBottom())
      break
    }

    case 'steps':
      msg.steps = mapBackendSteps(evt.steps || [], undefined)
      nextTick(() => scrollToBottom())
      break

    case 'await_approval':
      msg.approval_id = evt.approval_id
      msg.risk_level = evt.risk_level  // 新增：保存风险等级
      msg.risk_reason = evt.risk_reason  // 新增：保存风险原因
      if (msg.steps && msg.steps.length > 0) {
        const pendingStep = msg.steps.find((s: any) => s.name === evt.tool?.name)
        if (pendingStep) pendingStep.status = 'awaiting_approval'
      }
      // 发送通知提醒用户审批
      notifyTaskComplete({
        title: t('chat.approvalNotifyTitle'),
        body: t('chat.approvalNotifyBody', { tool: evt.tool?.name || t('chat.unknownTool') }),
        forceDesktop: true,
      })
      break

    case 'done':
      if (evt.content && evt.content !== msg.content) msg.content = evt.content
      if (evt.reasoning) msg.reasoning = evt.reasoning
      break

    case 'error':
      msg.content += `\n\n[错误] ${evt.content || ''}`
      break
  }
}
// 将当前 Session 保存为本地 MD 文件
async function saveSessionToLocalMarkdown() {
  if (messages.value.length === 0 || !activeSessionId.value) return

  try {
    await fetch(`${BACKEND_URL}/api/save_markdown`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: activeSessionId.value,
        title: messages.value[0].content.slice(0, 20).replace(/[\\/:*?"<>|]/g, '') || 'untitled',
        history: messages.value.map(m => ({ role: m.role, content: m.content })),
      }),
    })
    console.log('历史记录已保存为 Markdown')

    // 新会话首次保存后,异步生成 AI 标题
    const session = sessions.value.find(s => s.id === activeSessionId.value)
    if (session && !session.titleGenerated) {
      tryGenerateTitle(session.id)
    }
  } catch (err) {
    console.error('保存 MD 文件失败:', err)
  }
}

/** 异步调用后端 AI 生成标题 */
async function tryGenerateTitle(sessionId: string) {
  const session = sessions.value.find(s => s.id === sessionId)
  if (!session || session.titleGenerated) return

  // 取对话前 3 轮作为上下文
  const recent = session.messages.slice(0, 6).map(m => `${m.role}: ${m.content.slice(0, 200)}`).join('\n')
  try {
    const res = await fetch(`${BACKEND_URL}/api/generate_title`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        context: recent,
      }),
    })
    if (res.ok) {
      const data = await res.json()
      if (data.title) {
        session.title = data.title
        session.titleGenerated = true
      }
    }
  } catch (err) {
    console.error('生成标题失败:', err)
  }
}
async function installMcpServer(packageName: string, serverId: string, args: string[] = []) {
  const res = await fetch('http://127.0.0.1:8000/mcp/install/npm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ package_name: packageName, server_id: serverId, args })
  })
  if (!res.ok) {
    const errText = await res.text()
    throw new Error(errText || `HTTP ${res.status}`)
  }
  const data = await res.json()
  if (data.status && data.status !== 'ok') {
    throw new Error(data.message || data.detail || '安装失败')
  }
  return data
}

async function refreshMcpPanel(silent = true) {
  try {
    const res = await fetch('http://127.0.0.1:8000/mcp/config')
    if (res.ok) mcpConfigData.value = await res.json()
  } catch {}
  try {
    const res = await fetch('http://127.0.0.1:8000/mcp/tools')
    if (res.ok) {
      const data = await res.json()
      mcpToolList.value = data.tools || []
    }
  } catch {}
  try {
    const res = await fetch('http://127.0.0.1:8000/mcp/tools/by_server')
    if (res.ok) {
      const data = await res.json()
      mcpServerGroups.value = data.servers || []
      // 合并配置中尚未连接的 server
      const cfgServers = mcpConfigData.value?.mcpServers || {}
      for (const id of Object.keys(cfgServers)) {
        if (!mcpServerGroups.value.find(g => g.server_id === id)) {
          mcpServerGroups.value.push({ server_id: id, tool_count: 0, tools: [], error: t('mcpPanel.statusOffline') })
        }
      }
      expandedMcpServers.value.clear()
      if (mcpServerGroups.value.length > 0) {
        expandedMcpServers.value.add(mcpServerGroups.value[0].server_id)
      }
    }
  } catch {}
  await refreshMcpStatus(silent)
  // 手动刷新时显示成功提示
  if (!silent) {
    messageUi.success(t('mcpPanel.refreshSuccess'))
  }
}

async function submitCreateSkill() {
  creatingSkill.value = true
  try {
    if (skillAddMode.value === 'github') {
      const repo = skillForm.value.repo_url.trim()
      if (!repo) {
        messageUi.warning('请填写 GitHub 仓库地址')
        return
      }
      const res = await fetch(`${BACKEND_URL}/skills/install/github`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_url: repo,
          skill_name: skillForm.value.skill_name.trim(),
          branch: skillForm.value.branch.trim(),
          overwrite: !!skillForm.value.overwrite,
        }),
      })
      if (!res.ok) {
        let detail = `HTTP ${res.status}`
        try {
          const err = await res.json()
          detail = err.detail || err.message || detail
        } catch {
          detail = await res.text() || detail
        }
        throw new Error(detail)
      }
      const data = await res.json()
      messageUi.success(data.message || 'Skill 安装成功')
    } else {
      const name = skillForm.value.skill_name.trim()
      if (!name) {
        messageUi.warning('请填写 Skill 名称')
        return
      }
      const res = await fetch(`${BACKEND_URL}/skills/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          skill_name: name,
          display_name: skillForm.value.display_name.trim(),
          description: skillForm.value.description.trim(),
          purpose: skillForm.value.purpose.trim(),
          instructions: skillForm.value.instructions.trim(),
          overwrite: !!skillForm.value.overwrite,
        }),
      })
      if (!res.ok) {
        let detail = `HTTP ${res.status}`
        try {
          const err = await res.json()
          detail = err.detail || err.message || detail
        } catch {
          detail = await res.text() || detail
        }
        throw new Error(detail)
      }
      const data = await res.json()
      messageUi.success(data.message || `Skill '${name}' 已创建`)
    }
    showAddSkillModal.value = false
    skillForm.value = {
      skill_name: '', display_name: '', description: '', purpose: '', instructions: '',
      repo_url: '', branch: '', overwrite: false,
    }
    await refreshSkillList()
  } catch (e: any) {
    messageUi.error(`安装/创建失败:${e.message || e}`)
  } finally {
    creatingSkill.value = false
  }
}

async function submitInstallMcp() {
  const serverId = mcpForm.value.server_id.trim()
  if (!serverId) {
    messageUi.warning(t('addMcpModal.needServerId'))
    return
  }
  installingMcp.value = true
  try {
    if (mcpAddMode.value === 'remote') {
      const url = mcpForm.value.url.trim()
      if (!url) {
        messageUi.warning(t('addMcpModal.needUrl'))
        return
      }
      let headers: Record<string, string> = {}
      const ht = mcpForm.value.headersText.trim()
      if (ht) {
        try {
          headers = JSON.parse(ht)
        } catch {
          messageUi.warning(t('addMcpModal.needHeadersJson'))
          return
        }
      }
      const res = await fetch(`${BACKEND_URL}/mcp/servers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          server_id: serverId,
          url,
          transport: mcpForm.value.transport || 'sse',
          headers,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
      if (data.connected) messageUi.success(data.message || t('mcpPanel.addSuccess'))
      else messageUi.warning(data.message || t('mcpPanel.addSaved'))
    } else {
      const packageName = mcpForm.value.package_name.trim()
      if (!packageName) {
        messageUi.warning(t('addMcpModal.needPackage'))
        return
      }
      const args = mcpForm.value.argsText.trim().split(/\s+/).filter(Boolean)
      const res = await fetch(`${BACKEND_URL}/mcp/servers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          server_id: serverId,
          package_name: packageName,
          args,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
      if (data.connected) messageUi.success(data.message || t('mcpPanel.addNpmSuccess', { serverId }))
      else messageUi.warning(data.message || t('mcpPanel.addNpmWarning'))
    }
    showAddMcpModal.value = false
    mcpForm.value = { server_id: '', package_name: '', argsText: '', url: '', transport: 'sse', headersText: '' }
    await refreshMcpPanel()
  } catch (e: any) {
    messageUi.error(t('mcpPanel.addFail', { msg: e.message || e }))
  } finally {
    installingMcp.value = false
  }
}


// 工具审批:用户在 ChatMessage 卡片点击 同意/拒绝 后回调
async function approveTool(msgIdx: number, approved: boolean) {
  const msg: any = messages.value[msgIdx]
  if (!msg || !msg.approval_id) return
  // 后端会在第一次请求开始时移除 pending 记录;双击会导致第二次请求得到
  // 404,虽然第一次工具实际上已经执行成功。先在前端锁住当前审批卡片。
  if (msg.approval_pending === true) return
  const approvalId = msg.approval_id
  // 乐观更新：立即清除审批状态（工具会瞬间执行完），显示"生成中"状态
  msg.approval_pending = false
  msg.approval_id = undefined
  msg.generating = true
  loading.value = true
  publishAgentStatus('thinking', approved ? t('chat.continueProcessing') : t('chat.processingResult'))
  try {
    const res = await fetch(`${BACKEND_URL}/chat/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        approval_id: approvalId, // 使用保存的 approvalId，而不是已清除的 msg.approval_id
        approve: approved, // 后端 ApproveRequest 字段名为 approve
        session_id: activeSessionId.value || 'default',
        system_prompt: settings.value.systemPrompt || '',
        api_key: settings.value.apiKey || '',
        api_base: settings.value.baseUrl || '',
        model: settings.value.model || currentModel.value,
      }),
      signal: abortController.value?.signal, // 支持用户中断
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    const steps = mapBackendSteps(data.steps || [], data.pending_tool)

    if (data.status === 'pending_approval') {
      msg.reasoning = data.reasoning
      msg.steps = steps
      msg.approval_id = data.approval_id
      msg.approval_pending = false
      msg.generating = false
      msg.content = ''
      loading.value = false
      // 仍有下一项审批,保持桌宠思考循环,不要提前庆祝。
      return
    }

    msg.content = data.content || data.response || data.message || data.text || ''
    msg.reasoning = data.reasoning
    msg.steps = steps
    msg.approval_id = undefined
    msg.approval_pending = false
    msg.generating = false
    loading.value = false
    publishAgentStatus('complete', approved ? t('chat.complete') : t('chat.processedDone'))
    await saveSessionToLocalMarkdown()
    const preview = (msg.content || '').slice(0, 80).replace(/\s+/g, ' ')
    void notifyTaskComplete({
      title: 'Symbix · 任务完成',
      body: preview || '审批已通过,任务完成啦~',
    })

  } catch (e: any) {
    loading.value = false
    msg.generating = false
    // 如果是重复请求,第一次通常已经完成了工具执行;不要让旧审批按钮继续
    // 可点击并再次提交同一个已经消费的 approval_id。
    if (msg.approval_id === approvalId) msg.approval_id = undefined
    msg.approval_pending = false
    
    // 检查是否是用户主动中断（AbortError）
    // 兼容不同浏览器：name === 'AbortError' 或 code === 20（DOMException.ABORT_ERR）
    if (e.name === 'AbortError' || e.code === 20 || e.message?.includes('abort')) {
      console.log('=== 审批请求被用户中断 ===')
      publishAgentStatus('idle', t('chat.stopGenerate'))
      return
    }
    
    publishAgentStatus('error', t('chat.approvalFailed'))
    console.error(t('chat.approvalFailed'), e)
    messageUi.error(t('chat.approvalFailedDetail', { msg: e.message }))
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
  box-sizing: border-box; /* include titlebar padding so bottom isn't clipped */
  background: var(--bg-app);
  color: var(--text-primary);
  padding-top: 32px;
  overflow: hidden;
  min-height: 0;
}
.layout > .activity-bar,
.layout > .sidebar-container,
.layout > .chat-area {
  min-height: 0;
  height: 100%;
  align-self: stretch;
}


/* ---- Sidebar Container ---- */
.sidebar-container {
  position: relative;
  flex-shrink: 0;
  height: 100%;
  min-height: 0;
  align-self: stretch;
}


/* ---- Chat Area ---- */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 18px 24px 16px;
  overflow: hidden;
  min-width: 0;
  min-height: 0;
  height: 100%;
  box-sizing: border-box;
}
/* Keep ChatInput fully visible at the bottom */
.chat-area > :deep(.input-container) {
  flex: 0 0 auto;
  position: relative;
  z-index: 2;
}


/* ---- Message List ---- */
.message-list {
  flex: 1 1 auto;
  min-height: 0; /* critical: shrink so input is not pushed off-screen */
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
  background: var(--scrollbar);
  border-radius: 3px;
}
.message-list::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-hover);
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
  border-radius: var(--radius-md, 8px);
  border-bottom-left-radius: 4px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
}
.loading-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-500, #EF6B6E);
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
