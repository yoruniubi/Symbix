/**
 * 内存哨兵。
 *
 * 实测:应用长时间运行后,WebView2 的 renderer 私有内存能涨到 6 GB 级
 * (两个窗口各 6.3 GB,pagefile 被顶到 11.5 GB)。Chromium 侧没有可以硬性限制
 * JS heap 的开关,所以只能自己看着:
 *
 * 1. 定期采样(heap / DOM 节点数 / 消息条数),每 5 分钟报一条到后端日志 ——
 *    下次出问题就有增长曲线可看,能定位到是哪个窗口在涨;
 * 2. 越过警戒线就提示用户,越过硬线就在安全时机自动重载当前 webview。
 *
 * 自动重载是安全的:会话正文已经双写(localStorage + 后端 Markdown 存档),
 * 重载只会丢掉还没落盘的流式片段,所以 `canReload()` 为 false(正在对话)时绝不动手。
 */

/** 前端一条采样。 */
export interface MemorySample {
  window: string
  heapMB: number
  nodes: number
  messages: number
  uptimeMin: number
}

export interface MemorySentinelOptions {
  /** 窗口标识,进日志用 */
  window: string
  /** 当前消息条数(可选,用于判断是否和 DOM 一起涨) */
  messages?: () => number
  /** 软提示阈值(MB),默认 1200 */
  warnMB?: number
  /** 硬线阈值(MB),默认 2500 */
  hardMB?: number
  /** 越软线时回调(有 10 分钟冷却) */
  onWarn?: (sample: MemorySample) => void
  /** 越硬线时回调(有 2 分钟冷却) */
  onHard?: (sample: MemorySample) => void
  /** 返回 false 时绝不自动重载 —— 正在流式对话时必须为 false */
  canReload?: () => boolean
  /** 越硬线后是否自动重载,默认 true */
  autoReload?: boolean
  /** 采样周期(ms),默认 30s;测试时注入小值 */
  intervalMs?: number
  /** 上报周期(ms),默认 5min;<= 0 表示不上报 */
  reportMs?: number
  /** 重载前的等待(ms),默认 1500;给提示留出显示时间 */
  reloadDelayMs?: number
  /** 采样上报地址;留空则不上报(测试与独立窗口用) */
  reportUrl?: string
}

const SAMPLE_MS = 30_000
const REPORT_MS = 5 * 60_000
const WARN_COOLDOWN_MS = 10 * 60_000
const HARD_COOLDOWN_MS = 2 * 60_000

/** 采一次样。`performance.memory` 只有 Chromium 有,拿不到就退化成 0。 */
export function sampleMemory(windowName: string, messages: number = 0): MemorySample {
  const perf = performance as Performance & {
    memory?: { usedJSHeapSize: number }
  }
  const heap = perf.memory?.usedJSHeapSize
  let nodes = 0
  try {
    nodes = document.getElementsByTagName('*').length
  } catch {
    // 非浏览器环境(单测)没有 document —— 采样本身不该抛
  }
  return {
    window: windowName,
    heapMB: heap ? heap / (1024 * 1024) : 0,
    nodes,
    messages,
    uptimeMin: Math.round(performance.now() / 60_000),
  }
}

/**
 * 启动哨兵。返回停止函数(组件卸载或窗口关闭时调用)。
 *
 * Args:
 *   opts: 见 MemorySentinelOptions
 * Returns:
 *   () => void —— 停止采样
 */
export function startMemorySentinel(opts: MemorySentinelOptions): () => void {
  const {
    window: windowName,
    messages,
    warnMB = 1200,
    hardMB = 2500,
    onWarn,
    onHard,
    canReload = () => true,
    autoReload = true,
    intervalMs = SAMPLE_MS,
    reportMs = REPORT_MS,
    reloadDelayMs = 1500,
    reportUrl = '',
  } = opts

  let lastWarn = 0
  let lastHard = 0
  let lastReport = 0
  let warnedHeap = 0

  const tick = () => {
    const s = sampleMemory(windowName, messages ? messages() : 0)
    const now = Date.now()

    // heap 拿不到时(0)只能靠上报的曲线看 DOM 节点增长,不做阈值判断
    if (s.heapMB > 0 && s.heapMB > hardMB && now - lastHard > HARD_COOLDOWN_MS) {
      lastHard = now
      onHard?.(s)
      if (autoReload && canReload()) {
        // 数据已双写,重载是安全的;给回调留出弹提示的时间
        window.setTimeout(() => window.location.reload(), reloadDelayMs)
        return
      }
    } else if (s.heapMB > 0 && s.heapMB > warnMB && now - lastWarn > WARN_COOLDOWN_MS) {
      // 只在明显继续增长时才重复提醒,避免每次都弹
      if (s.heapMB > warnedHeap * 1.25) {
        warnedHeap = s.heapMB
        lastWarn = now
        onWarn?.(s)
      }
    }

    if (reportUrl && reportMs > 0 && now - lastReport > reportMs) {
      lastReport = now
      void reportSample(reportUrl, s)
    }
  }

  tick()
  const timer = window.setInterval(tick, intervalMs)
  return () => window.clearInterval(timer)
}

/** 上报一条采样到后端日志。失败静默 —— 诊断功能不能反过来制造噪音。 */
async function reportSample(url: string, s: MemorySample): Promise<void> {
  try {
    await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        window: s.window,
        heap_mb: Math.round(s.heapMB),
        nodes: s.nodes,
        messages: s.messages,
        uptime_min: s.uptimeMin,
      }),
    })
  } catch {
    /* 后端没起来 / 端口未知时静默 */
  }
}
