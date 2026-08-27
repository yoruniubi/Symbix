/**
 * 后端基址 + 通用 fetch 封装。
 * 集中管理,避免各组件各自硬编码 127.0.0.1:8000。
 */

export const BACKEND_URL = 'http://127.0.0.1:8000'

export interface VoiceConfigResp {
  tts: {
    priority: string[]
    voice_piper: string
    voice_edge: string
    speed: number
  }
  stt: {
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
    funasr_ws_url: string
    openai_api_key: string
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
export async function previewTts(text: string, speed?: number): Promise<string> {
  const res = await fetch(`${BACKEND_URL}/voice/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, speed }),
  })
  if (!res.ok) throw new Error(`POST /voice/tts ${res.status}`)
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}
