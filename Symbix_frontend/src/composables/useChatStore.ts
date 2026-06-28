import { ref } from 'vue'

interface Message { role: 'user' | 'assistant'; content: string }
interface Session { title: string; messages: Message[] }

const messages = ref<Message[]>([])
const sessions = ref<Session[]>([])
const activeSession = ref(-1)

export function useChatStore() {
  return { messages, sessions, activeSession }
}