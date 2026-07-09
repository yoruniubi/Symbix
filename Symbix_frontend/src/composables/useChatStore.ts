import { ref } from 'vue'

export interface ToolCallStep {
  id: string
  name: string
  arguments: string // 原始 JSON 字符串
  // 运行时状态
  result?: string
  status: 'pending' | 'awaiting_approval' | 'approved' | 'rejected' | 'done' | 'skipped'
  need_approval?: boolean
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  steps?: ToolCallStep[] // 本轮 assistant 消息内的工具调用步骤
  approval_id?: string // 待审批任务的 ID（pending_approval 时存在）
}

interface Session { title: string; messages: Message[] }

const CHAT_STORE_KEY = 'symbix_chat_sessions'

function loadPersistedSessions(): Session[] {
  try {
    const raw = localStorage.getItem(CHAT_STORE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {}
  return []
}

function saveSessionsToLocal(sessions: Session[]) {
  try {
    localStorage.setItem(CHAT_STORE_KEY, JSON.stringify(sessions))
  } catch {}
}

const messages = ref<Message[]>([])
const sessions = ref<Session[]>(loadPersistedSessions())
const activeSession = ref(-1)

/**
 * 把后端 /chat 返回的 steps 数组映射成前端 ToolCallStep[]。
 * 后端 step 形如:
 *   { type: 'reasoning', content }
 *   { type: 'tool_call', id, name, arguments, need_approval }
 *   { type: 'tool_result', id, output }
 * pending_tool: 当轮待审批的工具调用（若有），用于高亮 awaiting_approval。
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
      // 批量工具调用（流式 /chat/stream 的 steps 事件）
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
        target.result = typeof s.content === 'string' ? s.content : (typeof s.output === 'string' ? s.output : JSON.stringify(s.content ?? s.output ?? ''))
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

  function clearAllSessions() {
    sessions.value = []
    messages.value = []
    activeSession.value = -1
    localStorage.removeItem(CHAT_STORE_KEY)
  }

  return { messages, sessions, activeSession, persistSessions, clearAllSessions }
}