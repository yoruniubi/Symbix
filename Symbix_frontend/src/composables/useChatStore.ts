import { ref, watch } from 'vue'

/**
 * 工具返回原文在内存里保留的上限（字符）。
 *
 * 为什么必须在**写入时**截、而不是只靠显示层 `truncateResult()`：
 * 显示层只截了给用户看的那 800 字，完整原文照样整份存在 `step.result` 里。
 * 一个 `browser_snapshot` / `read_file` 的返回常常几万到几百万字符，
 * 累计几十轮后光这一项就能把 renderer 顶到几百 MB —— 而用户其实永远只能看到前 800 字。
 * 所以真正占用内存的这份要当场封顶，尾巴上标明被截了多少，便于日后回溯。
 */
export const TOOL_RESULT_KEEP = 4000

/** 截断标记尾缀。带上它是为了幂等 —— 再次 clamp 时能认出「这条已经截过了」。 */
const RESULT_CUT_MARK = '... [已截断'
const ARGS_CUT_MARK = '... [参数过长已截断'

/** 把工具返回原文压到保留上限内（幂等，短文本原样返回）。 */
export function clampToolResult(raw: string): string {
  if (typeof raw !== 'string' || raw.length <= TOOL_RESULT_KEEP) return raw
  // 已截过就直接还回去：否则第二轮会把尾部的截断说明自己再截一次，
  // 叠成「已截断 N 字... [已截断 M 字]」，而每次 map 都会调一次。
  if (raw.indexOf(RESULT_CUT_MARK) !== -1) return raw
  const cut = raw.length - TOOL_RESULT_KEEP
  return `${raw.slice(0, TOOL_RESULT_KEEP)}\n\n${RESULT_CUT_MARK} ${cut} 字，仅保留前 ${TOOL_RESULT_KEEP} 字]`
}

/**
 * 工具参数的上限（字符）。
 *
 * 参数比返回值更容易被无视：`write_file` / `create_file` 会把**整个文件内容**
 * 当参数流上来，一个几百 KB 的源码文件就是几百 KB 字符串常驻。
 * 而参数区在界面上默认是折起来的，用户几乎不会看全文 ——
 * 所以保留开头足以判断「它要干什么」，后面直接丢掉。
 */
export const TOOL_ARGS_KEEP = 2000

/** 把工具参数压到保留上限内（幂等）。 */
export function clampToolArguments(raw: string): string {
  if (typeof raw !== 'string' || raw.length <= TOOL_ARGS_KEEP) return raw
  if (raw.indexOf(ARGS_CUT_MARK) !== -1) return raw
  const cut = raw.length - TOOL_ARGS_KEEP
  return `${raw.slice(0, TOOL_ARGS_KEEP)}\n${ARGS_CUT_MARK} ${cut} 字]`
}

export interface ToolCallStep {
  id: string
  name: string
  arguments: string
  result?: string
  status: 'pending' | 'awaiting_approval' | 'approved' | 'rejected' | 'done' | 'skipped'
  need_approval?: boolean
  progress?: string
}

/** 一轮里某个文件的磁盘变更（后端 artifact_tracker 的 diff 结果）。 */
export interface FileChange {
  /** 绝对路径（Windows 反斜杠，已被 normcase） */
  path: string
  op: 'create' | 'edit' | 'delete'
  /** 变更后的字节数；delete 时是删除前的字节数 */
  size?: number
}

export interface Message {
  /**
   * 稳定唯一 id，仅前端用，不传给后端。
   *
   * 消息列表不能拿数组下标当 :key：handleEditMessage / handleRetryMessage 会
   * splice 截断中间的若干条，下标整体前移 → Vue 会错位复用同位置的旧组件，
   * 旧组件的 onUnmounted 不触发，它持有的 Blob URL / Audio 就永远不释放。
   *
   * 懒生成：历史会话从磁盘读回来的消息没有这个字段（后端不存它），
   * 渲染时用 `msg.uid ?? idx` 兜底；新建的消息一律挂上。
   */
  uid?: string
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  steps?: ToolCallStep[]
  /**
   * 本轮真正落盘 / 改掉 / 删掉的文件（后端轮末磁盘快照 diff 得出）。
   *
   * 替代「靠工具名 + 正则扫参数」的产物推断：Agent 用终端命令写盘时那个办法
   * 会漏，命令里提到的输入文件又会被误当产物。这里只认磁盘上真变了的东西。
   */
  fileChanges?: FileChange[]
  approval_id?: string
  /** 审批/提问已失效(后端重启或挂起态被清理):卡片只展示原因,不再可点 */
  approval_expired?: boolean
  /** 上游中断重试中:非空时前端显示「正在重新生成」提示(内容已清空重来) */
  retryHint?: string
  /** 本轮后端自动判决的执行模式(reactive / plan_solve):聊天页据此显示角标 */
  act_mode?: string
  /** 主动搭话开场气泡(宠物先说的话,点击弹幕气泡后进入会话的那条) */
  proactive?: boolean
  /** 运行中插话:任务进行中补充的话,按顺序原样上屏(带「插话」徽标) */
  injected?: string[]
}

export interface Session {
  id: string
  title: string
  messages: Message[]
  /** 是否已用 AI 生成过标题（避免重复请求） */
  titleGenerated?: boolean
}

const CHAT_STORE_KEY = 'symbix_chat_sessions'
/** 当前会话 id 也要落盘:否则 webview 一重载就回到 null,聊天区空白而侧栏还在 */
const CHAT_ACTIVE_KEY = 'symbix_active_session'

function loadPersistedSessions(): Session[] {
  try {
    const raw = localStorage.getItem(CHAT_STORE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as any[]
    // 兼容旧数据：没有 id 的 session 补上 UUID
    return parsed.map((s) => ({
      id: s.id || crypto.randomUUID(),
      title: s.title || '新对话',
      messages: s.messages || [],
      titleGenerated: !!s.titleGenerated,
    }))
  } catch {
    return []
  }
}

/**
 * 持久化失败的原因(空串 = 正常)。
 *
 * localStorage 只有 5MB,长会话带 steps/result 很容易撞线。以前这里是无条件
 * `catch {}`,写失败完全无声 —— 用户看到的是「历史突然没了」,却没有任何提示。
 * 现在把失败原因暴露出去,由聊天页弹一次警告。
 */
const persistError = ref<string>('')

function saveSessionsToLocal(sessions: Session[]) {
  try {
    localStorage.setItem(CHAT_STORE_KEY, JSON.stringify(sessions))
    persistError.value = ''
  } catch (e) {
    persistError.value = e instanceof Error ? e.message : String(e)
    console.error('[chat] 会话持久化失败(localStorage 可能已满):', e)
  }
}

const messages = ref<Message[]>([])
const sessions = ref<Session[]>(loadPersistedSessions())

function loadPersistedActiveId(): string | null {
  try {
    return localStorage.getItem(CHAT_ACTIVE_KEY) || null
  } catch {
    return null
  }
}

/** 当前激活会话 id，null 表示尚未绑定会话（欢迎页 / 新对话未发消息） */
const activeSessionId = ref<string | null>(loadPersistedActiveId())

// 模块级单例,整个应用生命周期只需一个 watcher
watch(activeSessionId, (id) => {
  try {
    if (id) localStorage.setItem(CHAT_ACTIVE_KEY, id)
    else localStorage.removeItem(CHAT_ACTIVE_KEY)
  } catch {}
})

/**
 * 把后端 /chat 返回的 steps 数组映射成前端 ToolCallStep[]。
 */
export function mapBackendSteps(
  rawSteps: any[],
  pendingTool?: any,
): ToolCallStep[] {
  const steps: ToolCallStep[] = []
  for (const s of rawSteps || []) {
    if (s.type === 'tool_call') {
      steps.push({
        id: s.id,
        name: s.name,
        arguments: clampToolArguments(typeof s.arguments === 'string' ? s.arguments : JSON.stringify(s.arguments ?? {})),
        need_approval: !!s.need_approval,
        status: pendingTool && pendingTool.id === s.id ? 'awaiting_approval' : 'pending',
      })
    } else if (s.type === 'tool_calls') {
      for (const tc of s.tool_calls || []) {
        steps.push({
          id: tc.id,
          name: tc.name,
          arguments: clampToolArguments(typeof tc.arguments === 'string' ? tc.arguments : JSON.stringify(tc.arguments ?? {})),
          need_approval: false,
          status: 'pending',
        })
      }
    } else if (s.type === 'tool_result') {
      const target = steps.find(st => st.id === s.tool_call_id || st.id === s.id)
      if (target) {
        target.result = clampToolResult(typeof s.content === 'string'
          ? s.content
          : (typeof s.output === 'string' ? s.output : JSON.stringify(s.content ?? s.output ?? '')))
        target.status = s.approved === false ? 'rejected' : 'done'
      } else {
        steps.push({
          id: s.tool_call_id || s.id || '',
          name: s.name || '(结果)',
          arguments: '',
          result: clampToolResult(typeof s.content === 'string' ? s.content : JSON.stringify(s.content ?? '')),
          status: s.approved === false ? 'rejected' : 'done',
        })
      }
    }
  }
  return steps
}

export function useChatStore() {
  function persistSessions() {
    saveSessionsToLocal(sessions.value)
  }

  function findSessionIndex(id: string): number {
    return sessions.value.findIndex(s => s.id === id)
  }

  function getActiveSession(): Session | null {
    if (!activeSessionId.value) return null
    return sessions.value.find(s => s.id === activeSessionId.value) || null
  }

  function clearAllSessions() {
    sessions.value = []
    messages.value = []
    activeSessionId.value = null
    localStorage.removeItem(CHAT_STORE_KEY)
    localStorage.removeItem(CHAT_ACTIVE_KEY)
  }

  return {
    messages,
    sessions,
    persistError,
    activeSessionId,
    persistSessions,
    findSessionIndex,
    getActiveSession,
    clearAllSessions,
  }
}