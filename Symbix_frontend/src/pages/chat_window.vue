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
        :refreshing="refreshingSkill"
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

      <!-- Checkpoint 时间线:Agents 行为回溯 -->
      <CheckpointPanel
        :active-panel="activePanel"
        :active-session-id="activeSessionId"
        @update:active-panel="activePanel = $event"
      />

      <ToolsRiskPanel
        :active-panel="activePanel"
        :active-session-id="activeSessionId"
        :native-tool-list="nativeToolList"
        :skill-tool-list="skillToolList"
        :mcp-tool-list="mcpToolList"
        :mcp-server-groups="mcpServerGroups"
        @update:active-panel="activePanel = $event"
      />

      <JobSchedulePanel
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
          v-show="!hideDuringLoading(msg)"
          @edit="handleEditMessage(idx, $event)"
          @approve="approveTool(idx, $event)"
          @retry="handleRetryMessage(idx)"
        />
        <div v-if="loading && messages[messages.length - 1]?.role === 'assistant'"
            v-show="hideDuringLoading(messages[messages.length - 1])"
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
        :voice-enabled="voiceEnabled"
        @send="sendMessage"
        @update:model="setModel"
        @stop="handleStopGeneration"
        @update:voice-enabled="voiceEnabled = $event"
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
      :oauth-waiting="oauthWaiting"
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
import CheckpointPanel from '@/components/panels/CheckpointPanel.vue'
import ToolsRiskPanel from '@/components/panels/ToolsRiskPanel.vue'
import JobSchedulePanel from '@/components/panels/JobSchedulePanel.vue'
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
import { feedSpeechSentence, flushSpeechSentence, speakStart, stopSpeak } from '@/utils/backend'
import { emit as emitTauri } from '@tauri-apps/api/event'
import { listen as listenTauri } from '@tauri-apps/api/event'

const { messages, sessions, activeSessionId, persistSessions, getActiveSession } = useChatStore()
const loading = ref(false)
const messageListRef = ref<HTMLElement | null>(null)
const abortController = ref<AbortController | null>(null)
/** 朗读开关：AI 回复后自动朗读 */
const voiceEnabled = ref(false)
/** 标记是否为用户主动中断（避免 abort 导致的错误被当成真实错误处理） */
let userAborted = false
/** 本轮流式是否已开启句子级朗读(用于结束时 flush 尾巴)。 */
let ttsStreaming = false
interface Skill {
  name: string
  display_name: string
  description: string
  trigger_keywords: string[]
}

const skillList = ref<Skill[]>([])
const skillToolList = ref<any[]>([])
const activePanel = ref<'files' | 'skill' | 'mcp' | 'native_tools' | 'checkpoint' | 'risk' | 'jobs' | null>(null)
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
/** OAuth 浏览器授权等待中(弹窗内显示提示) */
const oauthWaiting = ref(false)
const creatingSkill = ref(false)
const installingMcp = ref(false)
const skillAddMode = ref<'github' | 'custom'>('github')
const mcpAddMode = ref<'raw' | 'remote'>('raw')
const mcpStatusMap = ref<Record<string, { status: string; tools_count?: number; error?: string; transport?: string }>>({})
const refreshingMcp = ref(false)
const refreshingSkill = ref(false)
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
  transport: 'streamable_http',
  apiKey: '',
  headersText: '',
  rawJson: '',
})

function openAddChooser(kind: 'skill' | 'mcp') {
  if (kind === 'skill') {
    skillAddMode.value = 'github'
    showAddSkillModal.value = true
  } else {
    mcpAddMode.value = 'raw'
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
  // 新窗口：从 localStorage 反序列化读取；老已开窗口：Tauri 事件補发
  consumeSkinGenFromLS()

  // Tauri 事件监听：现有窗口收不到 onMounted，需事件補发
  // listen 一次：handler 立即生效，Promise 返回值 = UnlistenFn
  listenTauri<any>('skin-gen-request', (event: any) => {
    handleSkinGenPayload(event.payload)
  }).then((un) => {
    unlistenSkinGen = un
  }).catch(() => {})

  // 启动 MCP 连接状态周期检测（5 分钟一次，静默刷新）
  refreshMcpStatus(true)
  mcpCheckTimer = setInterval(() => refreshMcpStatus(true), MCP_CHECK_INTERVAL)
})

onBeforeUnmount(() => {
  if (mcpCheckTimer) {
    clearInterval(mcpCheckTimer)
    mcpCheckTimer = null
  }
  if (unlistenSkinGen) {
    unlistenSkinGen()
    unlistenSkinGen = null
  }
})
async function refreshSkillList() {
  if (refreshingSkill.value) return
  refreshingSkill.value = true
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
  refreshingSkill.value = false
}
async function togglePanel(panel: 'files' | 'skill' | 'mcp' | 'native_tools' | 'checkpoint' | 'risk' | 'jobs') {
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
  } else if (panel === 'risk') {
    // 风险面板需要全部真实工具全集(native + skill + mcp),先预取再交给面板
    try {
      const res = await fetch('http://127.0.0.1:8000/native/tools')
      if (res.ok) {
        const data = await res.json()
        nativeToolList.value = data.tools || []
      }
    } catch (err) {
      console.log('预取 Native 工具失败:', err)
    }
    try {
      const res = await fetch('http://127.0.0.1:8000/skills/tools')
      if (res.ok) {
        const data = await res.json()
        skillToolList.value = data.tools || []
      }
    } catch (err) {
      console.log('预取 Skill 工具失败:', err)
    }
    try {
      const res = await fetch('http://127.0.0.1:8000/mcp/tools')
      if (res.ok) {
        const data = await res.json()
        mcpToolList.value = data.tools || []
      }
    } catch (err) {
      console.log('预取 MCP 工具失败:', err)
    }
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
  userAborted = true
  // 打断当前播放的句子级朗读队列(清空未播句子 + 停当前音频)
  stopSpeak()
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
  const assistantMsg = messages.value[idx]
  const supersededRoundId = (assistantMsg as any).roundId || ''
  // 从 user 消息起截断(含 assistant 及之后),由 sendMessage 重新推入
  messages.value.splice(userIdx)
  loading.value = false
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
  sendMessage(userText, [], supersededRoundId)
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
  // markstream-vue 是异步批量渲染,内容高度可能渲染完成才稳定。
  // 用短暂延迟 + 多帧重试,确保切会话后能真正到底(而不是停在中间)。
  scrollToBottom()
  setTimeout(() => scrollToBottom(true), 120)
  setTimeout(() => scrollToBottom(true), 350)
  setTimeout(() => scrollToBottom(true), 800)
}

async function deleteSession(id: string) {
  const idx = sessions.value.findIndex(s => s.id === id)
  if (idx < 0) return
  const session = sessions.value[idx]
  const isActive = activeSessionId.value === id

  // 关键：如果正在删的是当前活动会话且后台仍在上一次请求中，必须先终止该请求。
  // 否则后端 SSE 还在跑，前端 message 删了但流式回调还在 push message，造成“看到鬼”现象。
  if (isActive && loading.value) {
    handleStopGeneration()
  }

  sessions.value.splice(idx, 1)
  if (isActive) {
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

// ── SkinWindow 跨窗口生成桌宠──────────────────────────────────
/** 将 base64 dataURL 转成 File，上传 /upload，返回 attachments 所需的 {path, name} 数组 */
async function uploadRefImage(ref: { dataUrl: string; name: string; mime: string }): Promise<any[]> {
  const res = await fetch(ref.dataUrl)
  const blob = await res.blob()
  const file = new File([blob], ref.name || 'ref.png', { type: ref.mime || blob.type })
  const form = new FormData()
  form.append('files', file, file.name)
  form.append('session_id', activeSessionId.value || 'pending')
  const resp = await fetch(`${BACKEND_URL}/upload`, { method: 'POST', body: form })
  if (!resp.ok) throw new Error(`upload HTTP ${resp.status}`)
  const data = await resp.json()
  const meta = data?.uploaded?.[0]
  if (!meta || meta.status !== 'ok') throw new Error(meta?.message || 'upload failed')
  return [{ path: meta.path, name: meta.filename || file.name, mime: meta.mime || file.type }]
}

// 用于跨窗口事件取消订阅
let unlistenSkinGen: (() => void) | null = null


/** 处理 SkinWindow 传过来的皮肤生成请求 payload（发一条预设消息给 AI） */
async function handleSkinGenPayload(payload: any) {
  if (!payload || !payload.message) return
  // 超过 5 分钟丢弃，防陈旧请求随事件重放
  if (payload.ts && Date.now() - payload.ts > 5 * 60 * 1000) return
  let files: any[] = []
  if (payload.refImage?.dataUrl) {
    try {
      files = await uploadRefImage(payload.refImage)
    } catch (e) {
      console.warn('[chat] 上传参考图失败，仅发送文本:', e)
    }
  }
  // 延迟一帧保证 ChatInput 等子组件已挂载
  setTimeout(() => sendMessage(payload.message, files), 300)
}

/** 新窗口路径：从 localStorage 读 pendingSkinGen 并清空。老窗口不走这条，走 Tauri事件。 */
function consumeSkinGenFromLS() {
  try {
    const raw = localStorage.getItem('pendingSkinGen')
    if (!raw) return
    localStorage.removeItem('pendingSkinGen')
    const payload = JSON.parse(raw)
    if (payload?.message) handleSkinGenPayload(payload)
  } catch (e) {
    console.warn('[chat] 读取 pendingSkinGen 失败:', e)
  }
}

const BACKEND_URL = 'http://127.0.0.1:8000'

type AgentStatus = 'thinking' | 'complete' | 'error' | 'idle'

function publishAgentStatus(status: AgentStatus, bubble?: string) {
  void emitTauri('agent-status', { status, bubble }).catch((error) => {
    // 浏览器开发模式没有 Tauri event 总线时,聊天本身仍应正常工作。
    console.debug('[agent-status] event unavailable:', error)
  })
}

/**
 * 加载期间是否隐藏某条 assistant 消息。
 * 仅当消息为真空内容(无文本、无工具步骤、无思维过程、无审批待处理)时隐藏,
 * 避免 Agent 场景下模型先调工具不输出文本时,step cards / reasoning 被一起藏掉。
 */
function hideDuringLoading(msg: any): boolean {
  if (!loading.value) return false
  if (msg.role !== 'assistant') return false
  if (msg.content && msg.content.trim() !== '') return false
  if (msg.approval_id) return false
  const steps = msg.steps
  if (Array.isArray(steps) && steps.length > 0) return false
  const r = msg.reasoning
  if (typeof r === 'string' ? r.trim().length > 0 : !!r) return false
  return true
}

async function sendMessage(text: string, files: any[], supersededRoundId?: string) {
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
      superseded_round_id: supersededRoundId || undefined,
    }

    abortController.value = new AbortController()
    userAborted = false // 开始新请求时重置中断标志
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
    // 流式结束且不在等待审批时，触发任务完成提醒
    if (!assistantMsg.approval_id) {
      publishAgentStatus('complete')
      const preview = (assistantMsg.content || '').slice(0, 80).replace(/\s+/g, ' ')
      void notifyTaskComplete({
        title: 'Symbix · 任务完成',
        body: preview || '我在这里，任务已经完成啦~',
      })
      // 朗读开关打开时:流式句子已在 delta 阶段逐句播放,这里只把剩余尾巴送出去
      if (ttsStreaming) {
        flushSpeechSentence()
      }
      ttsStreaming = false
    }

  } catch (e: any) {
    loading.value = false
    abortController.value = null
    // 流异常/中断时同步打断句子级朗读,避免残留队列继续播旧回复
    stopSpeak()
    ttsStreaming = false
    // 检查是否是用户主动中断(通过标志位或 AbortError 兼容不同浏览器)
    if (userAborted || e.name === 'AbortError' || e.code === 20 || e.message?.includes('abort') || e.message?.includes('fetch')) {
      console.log('=== 流被用户中断 ===')
      userAborted = false
      publishAgentStatus('idle', t('chat.stopGenerate'))
      if (assistantMsgIndex !== -1 && !messages.value[assistantMsgIndex]?.content) {
        messages.value.splice(assistantMsgIndex, 1)
      }
      return
    }
    console.error('=== 流式异常 ===', e)
    userAborted = false
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
      // 句子级朗读:首段 delta 时开启本轮回合,之后逐句喂入 TTS 队列
      if (voiceEnabled.value && evt.content) {
        if (!ttsStreaming) {
          ttsStreaming = true
          speakStart()
        }
        feedSpeechSentence(evt.content)
      }
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
      // 拒绝审批的 tool_result 带 approved:false → 标 rejected，否则会覆盖掉 steps 事件里的 rejected 状态
      const status = evt.approved === false ? 'rejected' : 'done'
      const target = steps.find((s: any) => s.id === evt.id)
      if (target) {
        target.result = evt.content || ''
        target.status = status
      } else {
        steps.push({
          id: evt.id || '',
          name: evt.name || '(result)',
          arguments: '',
          result: evt.content || '',
          status,
        })
      }
      msg.steps = steps.map((s: any) => ({
        ...s,
        arguments: typeof s.arguments === 'string' ? s.arguments : JSON.stringify(s.arguments ?? {}),
      }))
      nextTick(() => scrollToBottom())
      break
    }

    case 'steps': {
      // 用后端完整 steps 重建 msg.steps,同时同步局部聚合数组 —
      // 否则后续 tool_result 在旧局部数组里找不到 target,会 push 孤儿 step(参数为空)。
      const mapped = mapBackendSteps(evt.steps || [], undefined)
      msg.steps = mapped
      steps.length = 0
      steps.push(...mapped)
      nextTick(() => scrollToBottom())
      break
    }

    case 'await_approval':
      msg.approval_id = evt.approval_id
      msg.risk_level = evt.risk_level  // 新增:保存风险等级
      msg.risk_reason = evt.risk_reason  // 新增:保存风险原因
      if (msg.steps && msg.steps.length > 0) {
        // 优先按 id 精确匹配;找不到再回退到 name(且排除已拒绝/已完成的 step),
        // 避免同名工具多轮出现时误标旧 step 为待审批。
        let pendingStep = msg.steps.find((s: any) => evt.tool?.id && s.id === evt.tool.id)
        if (!pendingStep) pendingStep = msg.steps.find((s: any) =>
          s.name === evt.tool?.name && s.status !== 'rejected' && s.status !== 'done',
        )
        if (pendingStep) pendingStep.status = 'awaiting_approval'
      }
      // 发送通知提醒用户审批
      notifyTaskComplete({
        title: t('chat.approvalNotifyTitle'),
        body: t('chat.approvalNotifyBody', { tool: evt.tool?.name || t('chat.unknownTool') }),
        forceDesktop: true,
      })
      break

    case 'round_id':
      // 后端通知本轮 checkpoint round_id；重试时带上作为 superseded_round_id
      msg.roundId = evt.round_id || ''
      break

    case 'done':
      if (evt.content && evt.content !== msg.content) msg.content = evt.content
      if (evt.reasoning) msg.reasoning = evt.reasoning
      break

    case 'content_reset':
      // 上游连接中断重试:清空已渲染文本;同时打断本次朗读(重新生成时从头播)
      stopSpeak()
      ttsStreaming = false
      msg.content = ''
      msg.reasoning = ''
      nextTick(() => scrollToBottom())
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
        model: settings.value.model || currentModel.value,
        api_base: settings.value.baseUrl || '',
        api_key: settings.value.apiKey || '',
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

/**
 * 轮询 OAuth 连接状态(浏览器授权期间前端等待)。
 * 返回 'ok'(连接成功)或错误消息字符串。
 * 轮询中会保持弹窗打开并显示浏览器授权提示。
 */
async function waitOauthConnect(serverId: string): Promise<string> {
  // 每 2s 轮询一次,最多 150s(与后端任务超时一致)
  const maxAttempts = 75
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, 2000))
    try {
      const res = await fetch(`${BACKEND_URL}/mcp/oauth/status/${encodeURIComponent(serverId)}`)
      if (!res.ok) continue
      const st = await res.json().catch(() => ({}))
      if (st.status === 'ok') return 'ok'
      if (st.status === 'error') return st.message || 'OAuth authorization failed'
      // 仍在 authorizing/connecting,继续等
    } catch {
      // 网络抖动,继续
    }
  }
  return 'OAuth authorization timeout'
}

async function submitInstallMcp() {
  installingMcp.value = true
  try {
    if (mcpAddMode.value === 'raw') {
      // 粘贴 JSON 模式：配置 JSON 本身含 server_id，外层 server_id 输入框不必填
      const rawText = mcpForm.value.rawJson.trim()
      if (!rawText) {
        messageUi.warning(t('addMcpModal.needRawJson'))
        return
      }
      let parsed: any
      try {
        parsed = JSON.parse(rawText)
      } catch (e: any) {
        messageUi.warning(t('addMcpModal.invalidJson', { msg: e.message || e }))
        return
      }
      // 接受三种写法:
      // (1) 直接 {"server_xxx": {"command": ...}}
      // (2) {"mcpServers": {"server_xxx": {...}}}
      // (3) {"mcpServers": {...}, "mcp_api_key": {"server_xxx": "sk-..."}}
      const servers = parsed?.mcpServers && typeof parsed.mcpServers === 'object'
        ? parsed.mcpServers
        : (parsed?.mcpServers === undefined ? parsed : {})
      if (!servers || typeof servers !== 'object' || Array.isArray(servers) || Object.keys(servers).length === 0) {
        messageUi.warning(t('addMcpModal.needServers'))
        return
      }
      const mcpApiKeys = parsed?.mcp_api_key && typeof parsed.mcp_api_key === 'object'
        ? parsed.mcp_api_key
        : undefined
      const res = await fetch(`${BACKEND_URL}/mcp/servers/raw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ servers, mcp_api_key: mcpApiKeys }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
      // 后端返回 {results: [{server_id, status, connected, message}, ...]}
      const results = data?.results || []
      const okCount = results.filter((r: any) => r.status === 'ok').length
      const savedCount = results.filter((r: any) => r.status === 'saved').length
      const errCount = results.filter((r: any) => r.status === 'error').length
      if (errCount === results.length) {
        throw new Error(results.map((r: any) => `${r.server_id}: ${r.message}`).join('; '))
      }
      if (okCount && !errCount) messageUi.success(t('addMcpModal.addedN', { n: okCount }))
      else if (errCount) messageUi.warning(t('addMcpModal.partialWarn', { ok: okCount, saved: savedCount, err: errCount }))
      else messageUi.warning(t('addMcpModal.allSavedWarn') )
    } else {
      const serverId = mcpForm.value.server_id.trim()
      if (!serverId) {
        messageUi.warning(t('addMcpModal.needServerId'))
        return
      }
      // 远程 URL 模式:支持 streamable_http(默认)/ sse,可选 API Key(Bearer)或自定义 headers
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
          transport: mcpForm.value.transport || 'streamable_http',
          headers,
          api_key: mcpForm.value.apiKey.trim(),
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
      // OAuth 场景:后端返回 oauth_pending,浏览器窗口已弹出,需要轮询授权结果
      if (data.status === 'oauth_pending') {
        // 等待后台 OAuth 任务完成(浏览器登录 -> 自动连接)
        oauthWaiting.value = true
        const pollResult = await waitOauthConnect(serverId)
        oauthWaiting.value = false
        if (pollResult === 'ok') {
          messageUi.success(t('addMcpModal.oauthDone'))
        } else {
          messageUi.warning(t('addMcpModal.oauthError', { msg: pollResult || t('mcpPanel.statusOffline') }))
          showAddMcpModal.value = false
          mcpForm.value = { server_id: '', package_name: '', argsText: '', url: '', transport: 'streamable_http', apiKey: '', headersText: '', rawJson: '' }
          await refreshMcpPanel()
          return
        }
      } else if (data.connected) messageUi.success(data.message || t('mcpPanel.addSuccess'))
      else messageUi.warning(data.message || t('mcpPanel.addSaved'))
    }
    showAddMcpModal.value = false
    mcpForm.value = { server_id: '', package_name: '', argsText: '', url: '', transport: 'streamable_http', apiKey: '', headersText: '', rawJson: '' }
    await refreshMcpPanel()
  } catch (e: any) {
    oauthWaiting.value = false
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
  userAborted = false // 开始审批请求时重置中断标志
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
        approval_id: approvalId,
        approve: approved,
        session_id: activeSessionId.value || 'default',
        system_prompt: settings.value.systemPrompt || '',
        api_key: settings.value.apiKey || '',
        api_base: settings.value.baseUrl || '',
        model: settings.value.model || currentModel.value,
      }),
      signal: abortController.value?.signal,
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    // 后端现在返回 SSE 流，逐字渲染回复（避免审批后干等）
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let done = false
    const steps = msg.steps ? [...msg.steps] : []
    const toolCallAcc: Record<string, string> = {}

    while (!done) {
      const { value, done: readerDone } = await reader.read()
      if (readerDone) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      let currentEventType = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEventType = line.slice(7).trim()
          continue
        }
        if (line.startsWith('data: ')) {
          const dataStr = line.slice(6)
          if (dataStr === '[DONE]') { done = true; break }
          try {
            const evt = JSON.parse(dataStr)
            handleSSEEvent(evt, currentEventType, msg, steps, toolCallAcc)
          } catch { /* skip */ }
          currentEventType = ''
        }
      }
    }

    loading.value = false
    abortController.value = null
    msg.generating = false
    msg.approval_pending = false
    // 审批后续流也走句子级朗读:结尾把剩余尾巴送完
    if (ttsStreaming) flushSpeechSentence()
    ttsStreaming = false
    if (!msg.approval_id) {
      publishAgentStatus('complete', approved ? t('chat.complete') : t('chat.processedDone'))
      await saveSessionToLocalMarkdown()
      const preview = (msg.content || '').slice(0, 80).replace(/\s+/g, ' ')
      void notifyTaskComplete({
        title: 'Symbix · 任务完成',
        body: preview || '审批已通过,任务完成啦~',
      })
    } else {
      // 又出现新的审批请求，保持生成中状态
      msg.generating = false
    }

  } catch (e: any) {
    loading.value = false
    msg.generating = false
    // 审批流异常/中断:同步打断句子级朗读,避免残留队列
    stopSpeak()
    ttsStreaming = false
    // 如果是重复请求,第一次通常已经完成了工具执行;不要让旧审批按钮继续
    // 可点击并再次提交同一个已经消费的 approval_id。
    if (msg.approval_id === approvalId) msg.approval_id = undefined
    msg.approval_pending = false
    
    // 检查是否是用户主动中断（通过标志位或 AbortError 兼容不同浏览器）
    if (userAborted || e.name === 'AbortError' || e.code === 20 || e.message?.includes('abort') || e.message?.includes('fetch')) {
      console.log('=== 审批请求被用户中断 ===')
      userAborted = false
      publishAgentStatus('idle', t('chat.stopGenerate'))
      return
    }
    
    publishAgentStatus('error', t('chat.approvalFailed'))
    console.error(t('chat.approvalFailed'), e)
    messageUi.error(t('chat.approvalFailedDetail', { msg: e.message }))
  }
}


function scrollToBottom(instant: boolean = false) {
  if (messageListRef.value) {
    const el = messageListRef.value
    // 显式 behavior 覆盖 CSS 的 scroll-behavior:smooth,
    // 避免多次重试/新增消息时从旧位置平滑动画导致停在中间
    el.scrollTo({ top: el.scrollHeight, behavior: instant ? 'auto' : 'smooth' })
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
