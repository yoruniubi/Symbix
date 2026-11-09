/**
 * 内存哨兵的回归测试。
 *
 * 运行:`node --experimental-strip-types tests/memorySentinel.test.ts`
 *
 * 这套逻辑会主动 reload 用户窗口,误判的代价比泄漏还大 —— 所以死盯三件事:
 * 1. 没越线绝不能动;
 * 2. 正在流式对话(canReload 为 false)时绝不能 reload;
 * 3. 拿不到 performance.memory(non-Chromium / 老版本)时不能崩。
 */

let failed = 0
function check(name: string, actual: unknown, expected: unknown) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  console.log(ok ? `  PASS ${name}` : `  FAIL ${name}: got ${JSON.stringify(actual)} want ${JSON.stringify(expected)}`)
  if (!ok) failed++
}

const MB = 1024 * 1024
let heap = 100 * MB
let reloads = 0

// 最小浏览器替身:performance.memory + window.location.reload + setInterval
;(globalThis as any).document = { getElementsByTagName: () => [] }
;(globalThis as any).performance = {
  memory: { get usedJSHeapSize() { return heap } },
  now: () => 0,
}
;(globalThis as any).window = {
  setInterval: (fn: () => void, ms: number) => (globalThis as any).setInterval(fn, ms),
  clearInterval: (id: any) => (globalThis as any).clearInterval(id),
  setTimeout: (fn: () => void, ms: number) => (globalThis as any).setTimeout(fn, ms),
  location: { reload: () => { reloads++ } },
}

const { startMemorySentinel, sampleMemory } = await import('../src/utils/memorySentinel.ts')

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

// ── 1. sampleMemory 在无 document 环境下也不崩 ───────────────
const s = sampleMemory('probe', 3)
check('采样 heap 换算正确', s.heapMB, 100)
check('采样带窗口名', s.window, 'probe')
check('采样带消息数', s.messages, 3)

// ── 2. 未越线:一次回调都不该有 ──────────────────────────────
heap = 100 * MB
let warns = 0
let hards = 0
let stop = startMemorySentinel({
  window: 'test',
  warnMB: 1200,
  hardMB: 2500,
  intervalMs: 5,
  reportMs: 0,
  onWarn: () => warns++,
  onHard: () => hards++,
})
await sleep(40)
check('未越线不触发 warn', warns, 0)
check('未越线不触发 hard', hards, 0)
check('未越线不 reload', reloads, 0)

// ── 3. 越过软线:只提示,不 reload ──────────────────────────
heap = 1500 * MB
await sleep(40)
check('越软线触发 warn', warns >= 1, true)
check('越软线不 reload', reloads, 0)
stop()

// ── 4. 越过硬线 + 正在流式对话:必须忍住 ────────────────────
heap = 3000 * MB
let stop2 = startMemorySentinel({
  window: 'test',
  hardMB: 2500,
  intervalMs: 5,
  reportMs: 0,
  canReload: () => false,
  onHard: () => hards++,
})
await sleep(40)
check('流式中触发 hard 回调', hards >= 1, true)
check('流式中绝不 reload', reloads, 0)
stop2()

// ── 5. 越过硬线 + 空闲:才 reload ───────────────────────────
heap = 3000 * MB
let stop3 = startMemorySentinel({
  window: 'test',
  hardMB: 2500,
  intervalMs: 5,
  reportMs: 0,
  canReload: () => true,
  reloadDelayMs: 1,
})
await sleep(60)
check('空闲时越硬线才 reload', reloads, 1)
stop3()

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exit(failed === 0 ? 0 : 1)
