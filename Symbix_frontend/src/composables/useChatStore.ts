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
}

interface Session { title: string; messages: Message[] }

const messages = ref<Message[]>([])
const sessions = ref<Session[]>([])
const activeSession = ref(-1)

export function useChatStore() {
  return { messages, sessions, activeSession }
}