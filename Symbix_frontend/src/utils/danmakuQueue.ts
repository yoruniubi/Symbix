/**
 * 弹幕事件的转发队列。
 *
 * 背景：弹幕窗改成**按需创建**（有弹幕才建，屏上清空就 close）之后，它不再
 * 自己订阅后端 SSE —— 它挂载的时刻已经晚于触发建窗的那条事件，自己连必然错过。
 * 于是由常驻的 Home 窗口做唯一消费者，把事件通过 Tauri event 转发过去。
 *
 * 这里的核心难点不是转发，而是**送达判定**：
 *   · 窗口从 new WebviewWindow() 到 Vue 挂载 + register listener 有几百毫秒；
 *   · 这期间 emitTo() 既不报错也不返回失败 —— 它只是把事件交给一个不存在的
 *     监听者，静默丢弃。所以「try 没抛异常」根本不能当作送达。
 *   · 只能靠弹幕窗主动回一句 ready 才算握手完成，之前的全部押在队列里。
 *
 * 这个文件把「队列 + ready 门控」抽出来，好处是能用假的 transport 直接单测，
 * 不必启动 Tauri 实例。
 */

/** 队列长度上限。弹幕本身稀疏（空闲弹幕 10 分钟一条），8 条足够覆盖建窗窗口期，
 *  再多说明窗口长时间建不起来，此时丢最老的比无限堆积更合理。 */
export const MAX_PENDING = 8

/** 队列需要的外部能力。抽成接口是为了让测试注入假实现。 */
export interface DanmakuTransport {
  /** 目标窗口当前是否真的存在 */
  windowExists(): Promise<boolean>
  /** 把一条事件投递给目标窗口。窗口已销毁时应当抛错。 */
  emit(payload: unknown): Promise<void>
}

export interface DanmakuQueue {
  /** 入队一条事件并立即尝试投递（未 ready 时会留在队列里） */
  push(payload: unknown): Promise<void>
  /** 弹幕窗挂上 listener 了，可以把积压的补发出去 */
  markReady(): Promise<void>
  /** 窗口已销毁 / 投递途中失败：作废握手状态，等下次 ready */
  markLost(): void
  /** 当前待投递的条数（测试与诊断用） */
  size(): number
  /** listener 是否已握手 */
  isReady(): boolean
}

export function createDanmakuQueue(transport: DanmakuTransport): DanmakuQueue {
  let ready = false
  let pending: unknown[] = []
  // 串行化：push / markReady 可能并发（SSE 事件连着来 + ready 恰好到达），
  // 两个 flush 同时跑会把同一条发两遍。
  let flushing: Promise<void> | null = null

  async function doFlush(): Promise<void> {
    if (!ready || pending.length === 0) return
    if (!(await transport.windowExists())) {
      // 窗口被空闲销毁了：握手作废，事件留着等下一次建窗
      ready = false
      return
    }
    // 用快照遍历 + 逐条确认，中途失败就停下，剩下的留给下一次 ready
    const snapshot = pending
    pending = []
    for (let i = 0; i < snapshot.length; i++) {
      try {
        await transport.emit(snapshot[i])
      } catch {
        // 这条没送出去 → 连同它后面的全部退回队列
        pending = snapshot.slice(i).concat(pending)
        ready = false
        return
      }
    }
  }

  // 串行化，但必须是「排空式」的：正在 flush 时新来了事件，不能简单返回
  // 那个已进行到一半的 promise —— 它的快照早就取好了，新事件不会被发出去，
  // 会一直卡在队列里直到下一次 ready。所以这里是个循环：一轮排完再看还有
  // 没有新积压，有就再来一轮。
  function flush(): Promise<void> {
    if (!flushing) {
      // 用一个独立的布尔锁 + 递归：不能用 ``flushing === run`` 判断，
      // 因为 doFlush() 可能同步返回（队列空 / 未 ready），finally 会在
      // run 赋值之前就跑到。
      const run = (async (): Promise<void> => {
        while (ready && pending.length > 0) {
          await doFlush()
          if (!ready) break
        }
      })()
      flushing = run
      void run.finally(() => {
        // 只有当前这把锁还是自己时才释放；已被新轮次接管就交给新的那一轮
        if (flushing === run) flushing = null
      })
    }
    return flushing
  }

  return {
    async push(payload: unknown) {
      pending.push(payload)
      if (pending.length > MAX_PENDING) pending.shift()
      await flush()
    },
    async markReady() {
      ready = true
      await flush()
    },
    markLost() {
      ready = false
    },
    size() {
      return pending.length
    },
    isReady() {
      return ready
    },
  }
}
