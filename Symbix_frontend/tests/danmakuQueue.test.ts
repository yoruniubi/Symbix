/**
 * 弹幕转发队列的回归测试。
 *
 * 运行:`node --experimental-strip-types tests/danmakuQueue.test.ts`
 *
 * 这个队列解决的是「弹幕窗按需创建」带来的送达问题：窗口从 new 到挂上
 * listener 有几毫秒到几百毫秒的空档，这期间 emitTo **不报错**、只是静默丢包。
 * 所以重点盯这几类翻车：
 *   1. 窗口还没 ready 就把事件发出去（现实里表现为「搭话飘不出来」）；
 *   2. 投递途中窗口没了，事件被丢而不是退回队列；
 *   3. 窗口重建后仍带着旧 ready 状态，导致新窗口一条都收不到；
 *   4. 并发 push 把同一条事件发两遍。
 */

import { createDanmakuQueue, MAX_PENDING } from '../src/utils/danmakuQueue.ts'

let failed = 0

function check(name: string, actual: unknown, expected: unknown) {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a !== e) {
    console.error(`FAIL ${name}: got ${a}, want ${e}`)
    failed++
  } else {
    console.log(`ok   ${name}`)
  }
}

/** 造一个假的 transport：记录实际送达的事件，可随时「销毁」窗口或让 emit 失败 */
function makeTransport(opts: { exists?: boolean; failUntil?: number } = {}) {
  const delivered: unknown[] = []
  let exists = opts.exists ?? true
  let failRemaining = opts.failUntil ?? 0
  return {
    delivered,
    setExists(v: boolean) {
      exists = v
    },
    failNext(n: number) {
      failRemaining = n
    },
    transport: {
      async windowExists() {
        return exists
      },
      async emit(payload: unknown) {
        if (!exists) throw new Error('window gone')
        if (failRemaining > 0) {
          failRemaining--
          throw new Error('emit failed')
        }
        delivered.push(payload)
      },
    },
  }
}

async function main() {
  // ── 1. 未 ready 时不下发 ──
  {
    const h = makeTransport()
    const q = createDanmakuQueue(h.transport)
    await q.push({ text: 'A' })
    check('未 ready:不发', h.delivered.length, 0)
    check('未 ready:留在队列', q.size(), 1)
    check('未 ready:isReady 为 false', q.isReady(), false)

    await q.markReady()
    check('ready 后补发', h.delivered, [{ text: 'A' }])
    check('ready 后队列清空', q.size(), 0)
  }

  // ── 2. ready 之后立即下发 ──
  {
    const h = makeTransport()
    const q = createDanmakuQueue(h.transport)
    await q.markReady()
    await q.push({ text: 'B' })
    check('ready 后即时投递', h.delivered, [{ text: 'B' }])
  }

  // ── 3. 窗口掉了 → 握手作废，事件留着 ──
  {
    const h = makeTransport()
    const q = createDanmakuQueue(h.transport)
    await q.markReady()
    h.setExists(false)
    await q.push({ text: 'C' })
    check('窗口不在:不发', h.delivered.length, 0)
    check('窗口不在:事件保留', q.size(), 1)
    check('窗口不在:ready 作废', q.isReady(), false)
  }

  // ── 4. 窗口重建后重新握手，旧事件仍然送达（不丢搭话） ──
  {
    const h = makeTransport()
    const q = createDanmakuQueue(h.transport)
    await q.markReady()
    h.setExists(false)
    await q.push({ text: 'D' })
    h.setExists(true)
    await q.markReady()
    check('重建后旧事件补发', h.delivered, [{ text: 'D' }])
  }

  // ── 5. 投递中途失败 → 未送达的（含失败那条）全部退回 ──
  {
    const h = makeTransport()
    const q = createDanmakuQueue(h.transport)
    await q.markReady()
    h.failNext(1)
    await q.push({ text: 'E' })
    check('投递失败:一条都没送到', h.delivered.length, 0)
    check('投递失败:事件留在队列', q.size(), 1)
    check('投递失败:ready 作废', q.isReady(), false)

    await q.markReady()
    check('重新 ready 后送到', h.delivered, [{ text: 'E' }])
  }

  // ── 6. 前端锁：并发 push 不重复发送 ──
  {
    const h = makeTransport()
    const q = createDanmakuQueue(h.transport)
    await q.markReady()
    await Promise.all([q.push({ text: 'F1' }), q.push({ text: 'F2' }), q.push({ text: 'F3' })])
    check('并发 push:每条只发一次', h.delivered.length, 3)
    check(
      '并发 push:内容齐全',
      (h.delivered as any[]).map((x) => x.text).sort(),
      ['F1', 'F2', 'F3'],
    )
    check('并发 push:队列清空', q.size(), 0)
  }

  // ── 7. markLost 之后 push 不会下发（窗口正在销毁） ──
  {
    const h = makeTransport()
    const q = createDanmakuQueue(h.transport)
    await q.markReady()
    q.markLost()
    await q.push({ text: 'G' })
    check('markLost 后不发', h.delivered.length, 0)
    check('markLost 后入队', q.size(), 1)
  }

  // ── 8. 队列有上限，长期建不起窗时丢最老的 ──
  {
    const h = makeTransport({ exists: false })
    const q = createDanmakuQueue(h.transport)
    for (let i = 0; i < MAX_PENDING + 5; i++) await q.push({ text: `H${i}` })
    check('队列封顶', q.size(), MAX_PENDING)
    h.setExists(true)
    await q.markReady()
    // 丢的是最老的 5 条
    check('保留的是最新的', (h.delivered as any[])[0].text, 'H5')
    check('送达条数等于上限', h.delivered.length, MAX_PENDING)
  }

  // ── 9. 从未 ready 时反复 push 不应触发任何 transport.emit ──
  {
    const h = makeTransport()
    const q = createDanmakuQueue(h.transport)
    for (let i = 0; i < 3; i++) await q.push({ text: `I${i}` })
    check('全程未 ready:零投递', h.delivered.length, 0)
    check('全程未 ready:全在队列', q.size(), 3)
  }

  // ── 10. flush 进行中来的新事件必须也能发出去（排空式串行化）──
  // 典型场景：一条事件正在 emitTo（跨进程，几毫秒），这时又来一条。
  // 如果只返回那个在途 promise，后到的那条会卡在队列里直到下一次 ready，
  // 而 ready 可能十分钟后才来 —— 表现为「弹幕偶尔漏一条」。
  {
    const delivered: unknown[] = []
    let release: (() => void) | null = null
    const q = createDanmakuQueue({
      async windowExists() {
        return true
      },
      async emit(payload: unknown) {
        delivered.push(payload)
        if ((payload as any).text === 'J1') {
          // 先把第一条的 emit 挂起，模拟跨进程延迟
          await new Promise<void>((r) => {
            release = r
          })
        }
      },
    })
    await q.markReady()
    const p1 = q.push({ text: 'J1' })
    const p2 = q.push({ text: 'J2' })
    // 等第一个 emit 真正进入挂起状态（它是异步链上的，不能同步断定已赋值）
    await new Promise<void>((r) => setTimeout(r, 0))
    check('排空式:第一条正在发送', delivered.length, 1)
    // 注意不能断言 q.size() >= 1：J2 可能已经被第一轮 doFlush 的快照带走了。
    // 真正要验证的是「J2 不会因为 flush 已在跑就被漏掉」—— 看最终 delivered。
    release!()
    await Promise.all([p1, p2])
    check('排空式:两条都送到', (delivered as any[]).map((x) => x.text), ['J1', 'J2'])
    check('排空式:队列清空', q.size(), 0)
  }

  if (failed > 0) {
    console.error(`\n${failed} 项失败`)
    process.exit(1)
  }
  console.log('\n全部通过')
}

void main()
