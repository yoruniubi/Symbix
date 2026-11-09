/**
 * 把后端 `save_markdown` 存档的 Markdown 还原成消息列表。
 *
 * 存档格式(sessions.py `save_markdown`):
 * ```
 * # {title}
 *
 * ### **User**:
 * {content}
 *
 * ---
 *
 * ### **Assistant**:
 * {content}
 *
 * ---
 * ```
 * 只还原 role + content —— steps / 审批卡本来就没进存档,恢复不出来也不假装有。
 */

import type { Message } from '@/composables/useChatStore'

/** 段头:`### **User**:` / `### **Assistant**:`,大小写不敏感 */
const HEADER_RE = /^###[ \t]*\*\*(user|assistant)\*\*[ \t]*:[ \t]*$/gim

export function parseSessionMarkdown(md: string): Message[] {
  const text = String(md || '')
  if (!text.trim()) return []

  const headers = Array.from(text.matchAll(HEADER_RE))
  const out: Message[] = []
  for (let i = 0; i < headers.length; i++) {
    const h = headers[i]
    const from = (h.index ?? 0) + h[0].length
    const to = i + 1 < headers.length ? (headers[i + 1].index ?? text.length) : text.length
    const body = text
      .slice(from, to)
      .replace(/^\n+/, '')
      // 段尾的分隔线归上一段,不归下一段头
      .replace(/\n+---[ \t]*\n*$/, '')
      .replace(/\s+$/, '')
    if (!body) continue
    out.push({
      role: h[1].toLowerCase() === 'user' ? 'user' : 'assistant',
      content: body,
    })
  }
  return out
}
