import type { Ticker } from 'pixi.js'

export interface TickerResilienceOptions {
  /** 多久没推进就判定 rAF 停摆(ms)。默认 400,约 24 帧 */
  stallMs?: number
  /** 兜底驱动间隔(ms)。默认 1000/60,与 Pixi 默认 60Hz 对齐 */
  fallbackMs?: number
  /** 检查间隔(ms)。默认 500,只看是否停摆,不需要太频繁 */
  probeMs?: number
}

export interface TickerResilienceHandle {
  /** 是否正处于「手动驱动」状态(便于排查/测试) */
  readonly isFallback: () => boolean
  /** 解绑监听与定时器 */
  stop: () => void
}

/**
 * 给 ticker 装上 rAF 停摆兜底。
 *
 * Args:
 *   ticker: Pixi 的 ticker(`app.ticker`)
 *   options: 阈值配置,一般不用改
 *
 * Returns:
 *   TickerResilienceHandle: 可用于查询状态与解绑
 */
export function installTickerResilience(
  ticker: Ticker,
  options: TickerResilienceOptions = {},
): TickerResilienceHandle {
  const stallMs = options.stallMs ?? 400
  const fallbackMs = options.fallbackMs ?? 1000 / 60
  const probeMs = options.probeMs ?? 500

  let lastProgress = performance.now()
  /** 当前这一帧是不是我们自己手动驱动的 */
  let drivenByUs = false
  let fallback = false
  let disposed = false
  let probeTimer: ReturnType<typeof setInterval> | null = null

  const onTick = () => {
    // 自然帧回来了 → 退出兜底,还给 rAF
    if (fallback && !drivenByUs) {
      fallback = false
      stopDrive()
      console.info('[pet] rAF 已恢复,交回浏览器驱动')
    }
    lastProgress = performance.now()
    drivenByUs = false
  }

  let driveTimer: ReturnType<typeof setInterval> | null = null

  function startDrive() {
    if (driveTimer !== null) return
    // 注:用 setInterval 而非 rAF,但**不要**指望它精确到 fallbackMs ——
    // Windows 的定时器粒度约 15.6ms,1000/60 实际会跑成 ~16ms 或 ~31ms。
    // 动画速度不会因此失真:ticker.update() 内部按 performance.now() 算 deltaTime,
    // 所以哪怕只跑 30fps,动作时间轴依旧是对的。
    driveTimer = setInterval(() => {
      if (disposed) return
      drivenByUs = true
      ticker.update(performance.now())
    }, fallbackMs)
  }

  function stopDrive() {
    if (driveTimer !== null) {
      clearInterval(driveTimer)
      driveTimer = null
    }
  }

  ticker.add(onTick)

  // 窗口从最小化/隐藏恢复时重置基准,避免刚恢复就被判定成停摆而抖一下
  const onVisibility = () => {
    if (!document.hidden) lastProgress = performance.now()
  }
  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('focus', onVisibility)

  probeTimer = setInterval(() => {
    if (disposed) return
    if (document.hidden) {
      // 页面本来就不可见,不动画是正常的,不触发兜底
      lastProgress = performance.now()
      return
    }
    if (!fallback && performance.now() - lastProgress >= stallMs) {
      fallback = true
      console.warn('[pet] 检测到 rAF 停摆(窗口被遮挡?),切到手动驱动保持动画')
      startDrive()
    }
  }, probeMs)

  return {
    isFallback: () => fallback,
    stop() {
      disposed = true
      fallback = false   // 解绑后 isFallback() 不应再报 true
      stopDrive()
      if (probeTimer !== null) clearInterval(probeTimer)
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('focus', onVisibility)
      ticker.remove(onTick)
    },
  }
}