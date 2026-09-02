/**
 * 后端基址 + 通用 fetch 封装。
 * 集中管理,避免各组件各自硬编码 127.0.0.1:8000。
 */

export const BACKEND_URL = 'http://127.0.0.1:8000'

export interface VoiceConfigResp {
  tts: {
    enabled: boolean
    priority: string[]
    voice_edge: string
    voice_openai: string
    speed: number
    openai_base_url: string
    openai_api_key: string
    openai_model: string
  }
  stt: {
    enabled: boolean
    priority: string[]
    language: string
    threads: number
    use_vad: boolean
    chunk_size: number
    min_mute_chunks: number
    max_nomute_chunks: number
    use_prefix: boolean
    use_itn: boolean
    capture_device: number
    no_gpu: boolean
    flash_attn: boolean
    openai_base_url: string
    openai_api_key: string
    openai_model: string
    funasr_ws_url: string
    xfyun_app_id: string
    xfyun_api_key: string
    xfyun_api_secret: string
  }
  status: {
    tts: Record<string, { available: boolean; voices: { value: string; label: string }[] }>
    stt: Record<string, { available: boolean; cloud: boolean }>
  }
}

export async function getVoiceConfig(): Promise<VoiceConfigResp> {
  const res = await fetch(`${BACKEND_URL}/voice/config`)
  if (!res.ok) throw new Error(`GET /voice/config ${res.status}`)
  return res.json()
}

export async function updateVoiceConfig(patch: { tts?: Record<string, unknown>; stt?: Record<string, unknown> }): Promise<void> {
  const res = await fetch(`${BACKEND_URL}/voice/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`POST /voice/config ${res.status}`)
}

/** 试听 TTS:返回 Blob URL 供 <audio> 播放。 */
export async function previewTts(text: string, speed?: number, engine?: string): Promise<string> {
  const body: Record<string, unknown> = { text }
  if (speed !== undefined) body.speed = speed
  if (engine) body.engine = engine
  const res = await fetch(`${BACKEND_URL}/voice/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`POST /voice/tts ${res.status}`)
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

/** 剥离 markdown 语法,返回纯文本(用于 TTS 朗读) */
function stripMarkdown(text: string): string {
  return text
    // 移除代码块
    .replace(/```[\s\S]*?```/g, '')
    // 移除行内代码
    .replace(/`([^`]+)`/g, '$1')
    // 移除标题符号
    .replace(/^#{1,6}\s+/gm, '')
    // 移除加粗/斜体
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    // 移除链接,保留文本
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    // 移除图片
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '')
    // 移除列表符号
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    // 移除引用符号
    .replace(/^>\s+/gm, '')
    // 移除多余空行
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

/** 全局 TTS 朗读:创建 <audio> 自动播放并自动释放。
 *  已有播放在播则先停止旧的再播新的。
 */
let _speakAudio: HTMLAudioElement | null = null
export function speak(text: string) {
  if (_speakAudio) { _speakAudio.pause(); _speakAudio = null }
  // 剥离 markdown 符号,避免朗读出 ✳✳、#、* 等
  const plainText = stripMarkdown(text)
  if (!plainText) return
  previewTts(plainText).then(url => {
    const audio = new Audio(url)
    audio.onended = () => { URL.revokeObjectURL(url); _speakAudio = null }
    audio.play().catch(() => { /* 自动播放被浏览器阻止,静默忽略 */ })
    _speakAudio = audio
  })
}
