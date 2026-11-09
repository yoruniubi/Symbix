/**
 * 「聊天区内容突然没了,但后端 checkpoint 有记录」的回归测试。
 *
 * 运行:`node --experimental-strip-types tests/chatPersist.test.ts`
 *
 * 盯两件事:
 * 1. 当前会话 id 必须落盘 —— 否则 webview 一重载就回到 null,messages 初始为空,
 *    表现为「侧栏里会话还在、聊天区全空」;
 * 2. localStorage 写失败不能静默 —— 以前是 `catch {}`,用户只会看到历史凭空消失。
 */

const KEY_SESSIONS = 'symbix_chat_sessions'
const KEY_ACTIVE = 'symbix_active_session'

let failed = 0
function check(name: string, actual: unknown, expected: unknown) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  console.log(ok ? `  PASS ${name}` : `  FAIL ${name}: got ${JSON.stringify(actual)} want ${JSON.stringify(expected)}`)
  if (!ok) failed++
}

/** 最小的 localStorage 替身,可切换成「写就爆」模式模拟配额超限。 */
function makeStorage(seed: Record<string, string>, opts: { failWrite?: boolean } = {}) {
  const map = new Map(Object.entries(seed))
  return {
    map,
    getItem: (k: string) => (map.has(k) ? map.get(k)! : null),
    setItem: (k: string, v: string) => {
      if (opts.failWrite) throw new Error('QuotaExceededError')
      map.set(k, v)
    },
    removeItem: (k: string) => { map.delete(k) },
    clear: () => map.clear(),
  }
}

const sessionsPayload = JSON.stringify([
  { id: 'sess-1', title: '旧对话', messages: [{ role: 'user', content: 'hi' }] },
  { id: 'sess-2', title: '上次在看的', messages: [{ role: 'user', content: 'yo' }] },
])

// ── 1. 恢复:last active id 要能读回来 ────────────────────────
;(globalThis as any).localStorage = makeStorage({
  [KEY_SESSIONS]: sessionsPayload,
  [KEY_ACTIVE]: 'sess-2',
})
const store = (await import('../src/composables/useChatStore.ts')).useChatStore()
const { activeSessionId, sessions, clearAllSessions, persistError } = store

check('sessions 恢复', sessions.value.map(s => s.id), ['sess-1', 'sess-2'])
check('activeSessionId 从 localStorage 恢复', activeSessionId.value, 'sess-2')

// ── 2. 切换要落盘 ───────────────────────────────────────────
activeSessionId.value = 'sess-1'
await new Promise(r => setTimeout(r, 0))
check('切换会话写进 localStorage', (globalThis as any).localStorage.getItem(KEY_ACTIVE), 'sess-1')

// ── 3. 「新对话」= null,必须把键删掉而不是留旧值 ─────────────
activeSessionId.value = null
await new Promise(r => setTimeout(r, 0))
check('newChat 清掉 active 键', (globalThis as any).localStorage.getItem(KEY_ACTIVE), null)

// ── 4. 清空全部会话,两个键都不能残留 ────────────────────────
activeSessionId.value = 'sess-1'
clearAllSessions()
await new Promise(r => setTimeout(r, 0))
check('clearAllSessions 清 sessions', (globalThis as any).localStorage.getItem(KEY_SESSIONS), null)
check('clearAllSessions 清 active', (globalThis as any).localStorage.getItem(KEY_ACTIVE), null)

// ── 5. 写失败要暴露出来(不能静默)───────────────────────────
;(globalThis as any).localStorage = makeStorage({}, { failWrite: true })
const store2 = (await import('../src/composables/useChatStore.ts')).useChatStore()
check('正常时 persistError 为空', store2.persistError.value, '')
store2.persistSessions()
check('写失败时 persistError 非空', store2.persistError.value, 'QuotaExceededError')

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exit(failed === 0 ? 0 : 1)
