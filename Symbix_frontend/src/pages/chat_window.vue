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
        @update:active-panel="activePanel = $event"
        @open-add-chooser="openAddChooser"
        @toggle-mcp-server="toggleMcpServer"
        @reconnect-mcp="reconnectMcp"
        @remove-mcp="removeMcp"
        @test-mcp-connection="testMcpConnection"
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
        未设置 API Key，请先配置 API 密钥
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

    <!-- 添加 Skill 弹窗：GitHub 安装 / 自定义创建 -->
    <AddSkillModal
      :show="showAddSkillModal"
      :creating="creatingSkill"
      :mode="skillAddMode"
      :form="skillForm"
      @update:show="showAddSkillModal = $event"
      @update:mode="skillAddMode = $event"
      @submit="submitCreateSkill"
    />

    <!-- 添加 MCP 弹窗：远程 URL / 本地 npm -->
    <AddMcpModal
      :show="showAddMcpModal"
      :installing="installingMcp"
      :mode="mcpAddMode"
      :form="mcpForm"
      @update:show="showAddMcpModal = $event"
      @update:mode="mcpAddMode = $event"
      />

  </div>
</template>


<script setup lang="ts">
import SkillPanel from '@/components/panels/SkillPanel.vue'
import McpPanel from '@/components/panels/McpPanel.vue'
import FilePanel from '@/components/panels/FilePanel.vue'
import NativeToolsPanel from '@/components/panels/NativeToolsPanel.vue'
import ChatActivityBar from '@/components/ChatActivityBar.vue'
import { ref, computed, nextTick, onMounted, watch } from 'vue'
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
const messageUi = useMessage()
const { settings, loadSettings, saveSettings } = useSettings()
const { fetchModels, chatCompletion } = useApiClient()
const hello_list = ['今天想做些什么？', '欢迎回来！', '需要帮忙吗？', '有什么想聊的吗？', '又见面了！']
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


async function refreshMcpStatus() {
  try {
    const res = await fetch(`${BACKEND_URL}/mcp/test`)
    if (!res.ok) return
    const data = await res.json()
    mcpStatusMap.value = data.servers || {}
  } catch {}
}

async function reconnectMcp(serverId: string) {
  try {
    const res = await fetch(`${BACKEND_URL}/mcp/servers/${encodeURIComponent(serverId)}/reconnect`, { method: 'POST' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
    if (data.connected) messageUi.success(data.message || '重连成功')
    else messageUi.warning(data.message || '已尝试重连，当前仍未连通')
    await refreshMcpPanel()
  } catch (e: any) {
    messageUi.error(`重连失败：${e.message || e}`)
  }
}

async function removeMcp(serverId: string) {
  try {
    const res = await fetch(`${BACKEND_URL}/mcp/servers/${encodeURIComponent(serverId)}`, { method: 'DELETE' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
    messageUi.success(data.message || `已删除 ${serverId}`)
    await refreshMcpPanel()
  } catch (e: any) {
    messageUi.error(`删除失败：${e.message || e}`)
  }
}

async function removeSkill(skillName: string) {
  try {
    const res = await fetch(`${BACKEND_URL}/skills/${encodeURIComponent(skillName)}`, { method: 'DELETE' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
    messageUi.success(data.message || `已删除 ${skillName}`)
    await refreshSkillList()
  } catch (e: any) {
    messageUi.error(`删除 Skill 失败：${e.message || e}`)
  }
}



// 监听 settings 变化，同步 currentModel
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
      // 5 分钟内有效，防止过期消息被重复发送
      if (pending.message && pending.ts && (Date.now() - pending.ts < 5 * 60 * 1000)) {
        localStorage.removeItem('pendingSkinGen')
        // 延迟一帧确保 ChatInput 等子组件已挂载
        setTimeout(() => {
          sendMessage(pending.message, [])
        }, 300)
      } else {
        // 过期，清理
        localStorage.removeItem('pendingSkinGen')
      }

    }
  } catch (e) {
    console.warn('[chat] 读取 pendingSkinGen 失败:', e)
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
      mcpStatusMap.value = data.servers || {}
      const entries = Object.entries(mcpStatusMap.value)
      const connected = entries.filter(([, v]: any) => v?.status === 'connected').length
      if (connected > 0) {
        messageUi.success(`MCP 连接正常：${connected}/${entries.length} 个 Server 在线`)
      } else if (entries.length === 0) {
        messageUi.warning('尚未配置任何 MCP Server')
      } else {
        messageUi.warning('MCP 已配置但当前均未连通')
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
  publishAgentStatus('idle', '已暂停')
}

function handleEditMessage(idx: number, newText: string) {
  // 截断到该消息位置，替换为新文本并重新发送
  messages.value.splice(idx)
  loading.value = false
  sendMessage(newText, [])
}

/** 重试 assistant 回复：找到对应 user 消息，截断后重新发送 */
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
  // 从 user 消息起截断（含 assistant 及之后），由 sendMessage 重新推入
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
  // 清空当前对话区；真正创建会话在首次 sendMessage 时
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
  session.titleGenerated = true // 用户手动改过，不再自动生成
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
  console.log('=== sendMessage 开始（SSE 流式）===')
  safeLog('settings:', settings.value)

  let displayContent = text
  const ready = (files || []).filter((f: any) => f && (f.path || f.name))
  if (ready.length > 0) {
    const fileNames = ready.map((f: any) => `[文件: ${f.name || f.filename || 'file'}]`).join(' ')
    displayContent = text ? `${fileNames}\n${text}` : fileNames
  }

  messages.value.push({ role: 'user', content: displayContent })

  // 新对话首轮：创建带 UUID 的 session，并激活
  if (!activeSessionId.value) {
    const newId = crypto.randomUUID()
    const title = displayContent.slice(0, 20).replace(/[\\/:*?"<>|]/g, '') || '新对话'
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
  publishAgentStatus('thinking', '我来看看...')
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
    // 同步当前会话消息，避免侧边栏停留在旧内容
    const active = sessions.value.find(s => s.id === currentSessionId)
    if (active) active.messages = [...messages.value]
    await saveSessionToLocalMarkdown()
    // 流式结束且不在等待审批时，触发任务完成提醒
    if (!assistantMsg.approval_id) {
      publishAgentStatus('complete')
      const preview = (assistantMsg.content || '').slice(0, 80).replace(/\s+/g, ' ')
      void notifyTaskComplete({
        title: 'Symbix · 任务完成',
        body: preview || '我在这里，任务已经完成啦～',
      })

    }

  } catch (e: any) {
    loading.value = false
    abortController.value = null
    if (e.name === 'AbortError') {

      console.log('=== 流被用户中断 ===')
      publishAgentStatus('idle', '已暂停')
      if (assistantMsgIndex !== -1 && !messages.value[assistantMsgIndex]?.content) {
        messages.value.splice(assistantMsgIndex, 1)
      }
      return
    }
    console.error('=== 流式异常 ===', e)
    publishAgentStatus('error', '处理时遇到了一点问题')
    if (assistantMsgIndex !== -1 && !messages.value[assistantMsgIndex]?.content) {
      messages.value.splice(assistantMsgIndex, 1)
    } else if (assistantMsgIndex !== -1) {
      messages.value[assistantMsgIndex].content += `\n\n[错误] ${e.message}`
    }
    messageUi.error(`请求失败：${e.message}`)
  }
}


/**
 * 处理单条 SSE 事件，更新 assistant 消息。
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
      if (msg.steps && msg.steps.length > 0) {
        const pendingStep = msg.steps.find((s: any) => s.name === evt.tool?.name)
        if (pendingStep) pendingStep.status = 'awaiting_approval'
      }
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

    // 新会话首次保存后，异步生成 AI 标题
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

async function refreshMcpPanel() {
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
          mcpServerGroups.value.push({ server_id: id, tool_count: 0, tools: [], error: '未连接' })
        }
      }
      expandedMcpServers.value.clear()
      if (mcpServerGroups.value.length > 0) {
        expandedMcpServers.value.add(mcpServerGroups.value[0].server_id)
      }
    }
  } catch {}
  await refreshMcpStatus()
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
    messageUi.error(`安装/创建失败：${e.message || e}`)
  } finally {
    creatingSkill.value = false
  }
}

async function submitInstallMcp() {
  const serverId = mcpForm.value.server_id.trim()
  if (!serverId) {
    messageUi.warning('请填写 Server ID')
    return
  }
  installingMcp.value = true
  try {
    if (mcpAddMode.value === 'remote') {
      const url = mcpForm.value.url.trim()
      if (!url) {
        messageUi.warning('请填写远程 MCP URL')
        return
      }
      let headers: Record<string, string> = {}
      const ht = mcpForm.value.headersText.trim()
      if (ht) {
        try {
          headers = JSON.parse(ht)
        } catch {
          messageUi.warning('Headers 需为合法 JSON，例如 {"Authorization":"Bearer xxx"}')
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
      if (data.connected) messageUi.success(data.message || '远程 MCP 已连接')
      else messageUi.warning(data.message || '配置已保存，但当前未连通（可能需要鉴权后重连）')
    } else {
      const packageName = mcpForm.value.package_name.trim()
      if (!packageName) {
        messageUi.warning('请填写 npm 包名')
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
      if (data.connected) messageUi.success(data.message || `MCP '${serverId}' 已添加`)
      else messageUi.warning(data.message || '已添加但启动失败')
    }
    showAddMcpModal.value = false
    mcpForm.value = { server_id: '', package_name: '', argsText: '', url: '', transport: 'sse', headersText: '' }
    await refreshMcpPanel()
  } catch (e: any) {
    messageUi.error(`添加失败：${e.message || e}`)
  } finally {
    installingMcp.value = false
  }
}


// 工具审批：用户在 ChatMessage 卡片点击 同意/拒绝 后回调
async function approveTool(msgIdx: number, approved: boolean) {
  const msg: any = messages.value[msgIdx]
  if (!msg || !msg.approval_id) return
  // 后端会在第一次请求开始时移除 pending 记录;双击会导致第二次请求得到
  // 404,虽然第一次工具实际上已经执行成功。先在前端锁住当前审批卡片。
  if (msg.approval_pending === true) return
  const approvalId = msg.approval_id
  msg.approval_pending = true
  loading.value = true
  publishAgentStatus('thinking', approved ? '继续处理...' : '正在整理结果...')
  try {
    const res = await fetch(`${BACKEND_URL}/chat/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        approval_id: msg.approval_id,
        approve: approved, // 后端 ApproveRequest 字段名为 approve
        session_id: activeSessionId.value || 'default',
        system_prompt: settings.value.systemPrompt || '',
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
      msg.approval_pending = false
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
    loading.value = false
    publishAgentStatus('complete', approved ? '完成啦!' : '已处理完毕')
    await saveSessionToLocalMarkdown()
    const preview = (msg.content || '').slice(0, 80).replace(/\s+/g, ' ')
    void notifyTaskComplete({
      title: 'Symbix · 任务完成',
      body: preview || '审批已通过，任务完成啦～',
    })

  } catch (e: any) {
    loading.value = false
    // 如果是重复请求,第一次通常已经完成了工具执行;不要让旧审批按钮继续
    // 可点击并再次提交同一个已经消费的 approval_id。
    if (msg.approval_id === approvalId) msg.approval_id = undefined
    msg.approval_pending = false
    publishAgentStatus('error', '审批处理失败')
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
