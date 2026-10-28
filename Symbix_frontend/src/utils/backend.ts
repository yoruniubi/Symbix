
export let BACKEND_URL = 'http://127.0.0.1:8000'

/** 源码里还留着二十多处写死的 8000,统一在 fetch 改写里兜住(见 installLegacyUrlRewrite) */
const LEGACY_BASES = ['http://127.0.0.1:8000', 'http://localhost:8000']

/** 换掉当前 base(唯一入口:状态里的 url 是权威值) */
export function setBackendUrl(url: string) {
  const clean = (url || '').replace(/\/+$/, '')
  if (clean && clean !== BACKEND_URL) {
    console.log('[backend] API base ->', clean)
    BACKEND_URL = clean
  }
}

/** 把后端状态里的地址应用进来。url 为空 = Rust 侧还没选好端口,保持默认 */
export function applyBackendStatus(status: BackendStatus | null) {
  if (status?.url) setBackendUrl(status.url)
}

/**
 * 启动时确定后端地址。
 *
 * 端口在 Rust 侧「拉起后端之前」就定了,所以一般问一次就够;万一早于 setup
 * 完成(拿到空 url),短暂重试几次再放弃 —— 拿不到就用默认值,不影响启动。
 */
export async function resolveBackendUrl(tries = 8): Promise<string> {
  for (let i = 0; i < tries; i++) {
    const status = await fetchBackendStatus()
    if (status?.url) {
      applyBackendStatus(status)
      return BACKEND_URL
    }
    // null = 不在 Tauri 里(纯浏览器 npm run dev),不用等,直接用默认值
    if (status === null) break
    await new Promise((r) => setTimeout(r, 120))
  }
  return BACKEND_URL
}

/** 把请求地址里的旧常量换成当前 base;不是自家地址的原样返回 */
export function rewriteLegacyUrl(url: string): string {
  for (const base of LEGACY_BASES) {
    if (url === base || url.startsWith(base + '/') || url.startsWith(base + '?')) {
      return BACKEND_URL + url.slice(base.length)
    }
  }
  return url
}

/**
 * 让写死 8000 的老代码也跟上动态端口:包一层 fetch,把第一个参数里的旧地址
 * 改写成当前 base。只在这一处施展魔法,好过改六十多个调用点(而且以后新代码
 * 写回字面量也不会隐性失效)。
 *
 * `EventSource` 不走 fetch,那两处已改成用 BACKEND_URL(见 ChatInput.vue /
 * DanmakuWindow.vue),以后新增 SSE 也请直接用它。
 */
export function installLegacyUrlRewrite() {
  const w = window as unknown as { __symbixFetchPatched?: boolean }
  if (w.__symbixFetchPatched) return
  w.__symbixFetchPatched = true
  const original = window.fetch.bind(window)
  window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    if (typeof input === 'string') {
      input = rewriteLegacyUrl(input)
    } else if (input instanceof URL) {
      input = new URL(rewriteLegacyUrl(input.href))
    } else if (input instanceof Request) {
      const url = rewriteLegacyUrl(input.url)
      if (url !== input.url) {
        try {
          input = new Request(url, input)
        } catch {
          // 极少见(body 已被消费的 Request):保底用原请求
        }
      }
    }
    return original(input as RequestInfo, init)
  }) as typeof window.fetch
}
/** 后端进程状态,字段与 src-tauri/src/backend.rs 的 BackendStatus 一一对应 */
export interface BackendStatus {
  state: 'external' | 'starting' | 'ready' | 'exited' | 'failed' | 'missing'
  /** true = 后端是 Tauri 拉起来的,应用退出时由 Tauri 收掉 */
  managed: boolean
  url: string
  detail: string | null
}

/**
 * 主动查一次后端状态。
 *
 * 状态事件(`backend-status`)在 webview 加载完成之前就可能发过了,只订阅会漏掉
 * 第一条,所以挂载时先拉一次。返回 null = 当前不在 Tauri 里(纯浏览器跑
 * `npm run dev` 时没有这个命令),调用方直接忽略即可。
 */
export async function fetchBackendStatus(): Promise<BackendStatus | null> {
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    return await invoke<BackendStatus>('backend_status')
  } catch {
    return null
  }
}

/** 订阅后端状态变化;非 Tauri 环境静默降级(返回一个空函数) */
export async function onBackendStatus(
  cb: (status: BackendStatus) => void,
): Promise<() => void> {
  try {
    const { listen } = await import('@tauri-apps/api/event')
    const unlisten = await listen<BackendStatus>('backend-status', (e) => cb(e.payload))
    return unlisten
  } catch {
    return () => {}
  }
}

export interface VoiceConfigResp {
  tts: {
    enabled: boolean
    priority: string[]
    voice_edge: string
    voice_openai: string
    voice_custom: string
    custom_servers: string
    speed: number
    openai_base_url: string
    openai_api_key: string
    openai_model: string
    edge_auto_update: boolean
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
  }
  status: {
    tts: Record<string, { available: boolean; voices: { value: string; label: string }[] }>
    stt: Record<string, { available: boolean; cloud: boolean }>
    edgeVersion: string
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

/** 本机音频捕获设备(stream.exe 枚举),供设置页下拉选择麦克风。 */
export async function listSttDevices(): Promise<{ id: number; name: string }[]> {
  const res = await fetch(`${BACKEND_URL}/voice/stt/devices`)
  if (!res.ok) throw new Error(`GET /voice/stt/devices ${res.status}`)
  const data = await res.json()
  return data.devices || []
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
  if (!res.ok) throw new Error(await readErrorDetail(res, 'POST /voice/tts'))
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

/**
 * 读出后端错误体里的 detail。后端会把「哪个引擎为什么失败」拼成长文案
 * (例如 edge 403 的「升级 edge-tts」建议),不能解析时退回「路径 + 状态码」。
 */
export async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json()
    const detail = (data as { detail?: unknown })?.detail
    if (typeof detail === 'string' && detail) return detail
    if (detail) return JSON.stringify(detail)
  } catch {
    // 非 JSON 响应(如 502 HTML)走 fallback
  }
  return `${fallback} ${res.status}`
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
    // 移除未闭合的残留星号/下划线(截断或流式中半截)
    .replace(/\*+/g, '')
    .replace(/_{1,2}/g, '')
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

// ─────────────────────────────────────────────────────────────
// 句子级流式朗读(方案 A:句子切分 + 排队播放)
// ─────────────────────────────────────────────────────────────

/** 句子切分配置:中文标点任意切;英文句点要求“空格+大写”才切(避免误切 3.14 / file.txt 等)。 */
const SENTENCE_END_RE = /(?<=[。！？!?；;])\s*(?![）)]$)|(?<=\.)\s+(?=[A-Z])/
/** 句子最小长度:太短的不切(避免把「嗯」「好」之类单个字拆出去单独播)。 */
const MIN_SENTENCE_LEN = 4

/**
 * 把增量文本切分成“完整句子”列表。
 * 保留未完成尾巴(buffer)留给下一次 feed。
 * 例:feed("你好,世界。这是" ) → ["你好,世界。"] + buffer="这是"
 */
export function splitSpeechSentences(buffer: string, chunk: string): { sentences: string[]; buffer: string } {
  const merged = buffer + chunk
  const sentences: string[] = []
  const parts = merged.split(SENTENCE_END_RE)
  // 最后一段视为未完成(可能是句子中部,也可能到句末但缺标点)
  let pending = parts.pop() || ''
  for (const p of parts) {
    const t = p.trim()
    if (t) sentences.push(t)
  }
  // 若 pending 已经是完整句(末尾带句末标点),直接送出,不留 buffer
  if (pending.trim() && /[。！？!?；;.]$/.test(pending.trim())) {
    sentences.push(pending.trim())
    pending = ''
  }
  // 过短的尾巴:如果整段只有一句且太短,直接当句子送走(避免永远等不到完整句)
  if (pending.trim() && sentences.length === 0 && merged.trim().length > 0 && merged.trim().length < MIN_SENTENCE_LEN) {
    sentences.push(pending.trim())
    pending = ''
  }
  return { sentences, buffer: pending }
}

/** 全局排队播放状态。 */
let _speakBuffer = ''
/** 待合成队列(纯文本,逐句出队合成)。 */
let _speakQueue: string[] = []
/** 已合成待播缓存(预合成结果,播放器只从这里取句)。 */
let _speakReady: { text: string; url: string }[] = []
/** 当前播放的 audio 元素(用于打断时 pause + 释放)。 */
let _speakAudio: HTMLAudioElement | null = null
/** 当前正在播放的 URL(独立追踪,切轮/停止时 revoke,防止泄漏)。 */
let _speakCurrentUrl = ''
/** 是否正在播放中。 */
let _speakPlaying = false
/** 停止标记:置 true 时清空队列并停掉当前播放。 */
let _speakStopRequested = false
/** 预合成协程是否运行中(防重入)。 */
let _speakHydrating = false
/** 会话令牌:每次 speakStart 自增,拦截旧会话在途合成结果混入新一轮。 */
let _speakSession = 0
/** 预合成超前上限:已合成未播最多缓存句数,避免过度堆积(停止时需全部 revoke)。 */
const MAX_PREFETCH = 6

/**
 * 私有:预合成协程。逐句从待合成队列取句 → 后台合成 MP3 放入已合成缓存。
 * 播放器播完当前句直接从缓存取下一句,消除“播完才合成”的句间延迟。
 */
async function _hydrateQueue() {
  if (_speakHydrating || _speakStopRequested) return
  _speakHydrating = true
  const session = _speakSession
  try {
    while (
      !_speakStopRequested &&
      _speakSession === session &&
      _speakQueue.length > 0 &&
      _speakReady.length < MAX_PREFETCH
    ) {
      const raw = _speakQueue.shift()!
      const plain = stripMarkdown(raw)
      if (!plain) continue
      // 每个 in-flight 合成都带上会话令牌,防止旧会话结果混入新一轮
      const mySession = session
      try {
        const url = await previewTts(plain)
        if (_speakStopRequested || _speakSession !== mySession) {
          // 停止或切轮后的结果直接丢弃
          URL.revokeObjectURL(url)
          return
        }
        _speakReady.push({ text: plain, url })
        // 有空闲播放器 → 立即开播(合成完成即播,不等队列累积)
        if (!_speakPlaying) _playNextSentence()
      } catch {
        // 单句合成失败:跳过,继续下一句
      }
    }
  } finally {
    _speakHydrating = false
  }
}

/** 私有:从已合成缓存取下一句播放。无缓存但有未合成句时补一次预合成。 */
function _playNextSentence() {
  if (_speakStopRequested) {
    _speakPlaying = false
    _speakQueue = []
    return
  }
  const next = _speakReady.shift()
  if (!next) {
    _speakPlaying = false
    // 待合成队列仍有句子 → 触发预合成,合成完成后由 _hydrateQueue 再次开播
    if (_speakQueue.length > 0) void _hydrateQueue()
    return
  }
  _speakPlaying = true
  _speakCurrentUrl = next.url
  const audio = new Audio(next.url)
  _speakAudio = audio
  const finish = () => {
    URL.revokeObjectURL(next.url)
    if (_speakCurrentUrl === next.url) _speakCurrentUrl = ''
    _speakAudio = null
    // 当前会话未被停止才继续播下一句;并指未被合成的队列继续补满
    if (!_speakStopRequested) {
      if (_speakQueue.length > 0) void _hydrateQueue()
      _playNextSentence()
    } else {
      _speakPlaying = false
    }
  }
  audio.onended = finish
  audio.onerror = finish
  audio.onpause = () => {
    // 只在非主动暂停时标记结束(防 stop 时重复触发)
    if (_speakStopRequested) {
      _speakAudio = null
      if (_speakCurrentUrl === next.url) {
        URL.revokeObjectURL(next.url)
        _speakCurrentUrl = ''
      }
    }
  }
  audio.play().catch(() => {
    // 自动播放被浏览器阻止:跳过本句继续播下一句,不卡死队列
    URL.revokeObjectURL(next.url)
    if (_speakCurrentUrl === next.url) _speakCurrentUrl = ''
    _speakAudio = null
    _playNextSentence()
  })
}

/**
 * 开始一轮朗读:清空旧队列并重置会话状态。
 * 用于“新回复开始时”调用,保证新回复覆盖旧回复。
 */
export function speakStart() {
  // 新会话:令牌自增,使旧会话在途合成结果在返回时被丢弃
  _speakSession++
  _speakStopRequested = false
  _speakQueue = []
  // 清空旧预合成缓存(新回复覆盖旧回复)
  for (const item of _speakReady) {
    URL.revokeObjectURL(item.url)
  }
  _speakReady = []
  _speakBuffer = ''
  if (_speakAudio) {
    _speakAudio.pause()
    _speakAudio = null
  }
  // 释放正在播放的 URL(切轮/新开)
  if (_speakCurrentUrl) {
    URL.revokeObjectURL(_speakCurrentUrl)
    _speakCurrentUrl = ''
  }
  _speakPlaying = false
  _speakHydrating = false
}

/**
 * 喂入一段增量文本,可拆出完整句子立即入队预合成。
 * [A] 供流式合成:每收到一段 delta 就调用,内部按句末标点切分。
 */
export function feedSpeechSentence(chunk: string) {
  if (!chunk || _speakStopRequested) return
  const { sentences, buffer } = splitSpeechSentences(_speakBuffer, chunk)
  _speakBuffer = buffer
  for (const s of sentences) {
    _speakQueue.push(s)
  }
  void _hydrateQueue()
}

/**
 * 流式朗读结束:把剩余尾巴作为最后一整句送出(若有)。
 */
export function flushSpeechSentence() {
  const tail = _speakBuffer.trim()
  _speakBuffer = ''
  if (tail) {
    _speakQueue.push(tail)
  }
  void _hydrateQueue()
}

/** 停止当前 TTS 朗读并清空队列。 */
export function stopSpeak() {
  // 令牌自增:使所有在途合成返回时被丢弃(与 speakStart 同理)
  _speakSession++
  _speakStopRequested = true
  _speakQueue = []
  // 释放已预合成的 URL,避免内存泄漏
  for (const item of _speakReady) {
    URL.revokeObjectURL(item.url)
  }
  _speakReady = []
  _speakBuffer = ''
  if (_speakAudio) {
    _speakAudio.pause()
    _speakAudio = null
  }
  if (_speakCurrentUrl) {
    URL.revokeObjectURL(_speakCurrentUrl)
    _speakCurrentUrl = ''
  }
  _speakPlaying = false
}

/**
 * 兼容旧接口:整段朗读(Home 定时任务 bubble 等仍走这里)。
 * 内部改为句子级切分后排队播放,行为与旧版“打断旧播新”等价,更流畅。
 */
export function speak(text: string) {
  speakStart()
  feedSpeechSentence(text)
  flushSpeechSentence()
}
