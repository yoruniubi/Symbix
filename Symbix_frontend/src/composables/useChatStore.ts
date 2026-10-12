import { ref } from 'vue'

export interface ToolCallStep {
  id: string
  name: string
  arguments: string
  result?: string
  status: 'pending' | 'awaiting_approval' | 'approved' | 'rejected' | 'done' | 'skipped'
  need_approval?: boolean
  progress?: string
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  steps?: ToolCallStep[]
  approval_id?: string
  /** 审批/提问已失效(后端重启或挂起态被清理):卡片只展示原因,不再可点 */
  approval_expired?: boolean
  /** 上游中断重试中:非空时前端显示「正在重新生成」提示(内容已清空重来) */
  retryHint?: string
  /** 本轮后端自动判决的执行模式(reactive / plan_solve):聊天页据此显示角标 */
  act_mode?: string
}

export interface Session {
  id: string
  title: string
  messages: Message[]
  /** 是否已用 AI 生成过标题（避免重复请求） */
  titleGenerated?: boolean
}

const CHAT_STORE_KEY = 'symbix_chat_sessions'

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

function saveSessionsToLocal(sessions: Session[]) {
  try {
    localStorage.setItem(CHAT_STORE_KEY, JSON.stringify(sessions))
  } catch {}
}

const messages = ref<Message[]>([])
const sessions = ref<Session[]>(loadPersistedSessions())
/** 当前激活会话 id，null 表示尚未绑定会话（欢迎页 / 新对话未发消息） */
const activeSessionId = ref<string | null>(null)

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
        arguments: typeof s.arguments === 'string' ? s.arguments : JSON.stringify(s.arguments ?? {}),
        need_approval: !!s.need_approval,
        status: pendingTool && pendingTool.id === s.id ? 'awaiting_approval' : 'pending',
      })
    } else if (s.type === 'tool_calls') {
      for (const tc of s.tool_calls || []) {
        steps.push({
          id: tc.id,
          name: tc.name,
          arguments: typeof tc.arguments === 'string' ? tc.arguments : JSON.stringify(tc.arguments ?? {}),
          need_approval: false,
          status: 'pending',
        })
      }
    } else if (s.type === 'tool_result') {
      const target = steps.find(st => st.id === s.tool_call_id || st.id === s.id)
      if (target) {
        target.result = typeof s.content === 'string'
          ? s.content
          : (typeof s.output === 'string' ? s.output : JSON.stringify(s.content ?? s.output ?? ''))
        target.status = s.approved === false ? 'rejected' : 'done'
      } else {
        steps.push({
          id: s.tool_call_id || s.id || '',
          name: s.name || '(结果)',
          arguments: '',
          result: typeof s.content === 'string' ? s.content : JSON.stringify(s.content ?? ''),
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
  }

  return {
    messages,
    sessions,
    activeSessionId,
    persistSessions,
    findSessionIndex,
    getActiveSession,
    clearAllSessions,
  }
}