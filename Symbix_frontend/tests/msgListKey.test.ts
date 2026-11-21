/**
 * 「聊天消息列表用下标当 key」的回归测试。
 *
 * 运行:`node --experimental-strip-types tests/msgListKey.test.ts`
 *
 * 为什么值得单独测:
 * `ChatWindow.vue` 原来是 `:key="idx"`,而 `handleEditMessage` /
 * `handleRetryMessage` 都会 `messages.splice(idx)` 截断中间消息。用下标
 * 当 key 时 Vue 会**错位复用**组件实例:
 *
 *   · `onUnmounted` 不触发 → `ChatMessage` 里的 SVG / MCP 图片 Blob URL
 *     永不释放(renderer 私有内存慢性增长,且 JS 堆看不出来);
 *   · 旧 DOM 留着、props.msg 换成新数据 → 会看到内容串行。
 *
 * 正确做法是每条消息带一个创建时生成、终身不变的 `uid`,key 取 `msg.uid`。
 * 这个测试直接读源码断言,防止以后被改回 `:key="idx"`。
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const src = readFileSync(resolve(here, '../src/pages/ChatWindow.vue'), 'utf8')

let failed = 0
function check(name: string, ok: boolean, detail = '') {
  console.log(ok ? `  PASS ${name}` : `  FAIL ${name}${detail ? ': ' + detail : ''}`)
  if (!ok) failed++
}

// ---- 1. v-for 的 key 不能是下标 ----
const forBlock = src.match(/v-for="\(msg, idx\) in messages"[\s\S]{0,120}/)
check('找得到消息列表的 v-for', !!forBlock)
if (forBlock) {
  const block = forBlock[0]
  check(':key 不再用下标 idx', !/:key="idx"/.test(block), block.split('\n')[1])
  check(':key 用 msg.uid', /:key="msg\.uid/.test(block), block.split('\n')[1])
}

// ---- 2. 消息对象必须带 uid ----
const pushCalls = [...src.matchAll(/messages\.value\.push\(\{[\s\S]{0,200}?\}\)/g)]
check('至少找到两处 messages.push', pushCalls.length >= 2, `实际 ${pushCalls.length}`)
let missing = 0
for (const m of pushCalls) {
  // push 出来的是消息对象字面量；只要里面没有 uid 就算漏
  if (!/uid:\s*crypto\.randomUUID\(\)/.test(m[0])) {
    missing++
    console.log(`    漏 uid: ${m[0].replace(/\s+/g, ' ').slice(0, 90)}`)
  }
}
check('所有 push 的消息都带 uid', missing === 0, `${missing} 处漏`)

// ---- 3. 截断消息的函数仍然存在（说明 key 稳定性确实会被用到）----
check('存在 splice 截断（编辑消息）', /messages\.value\.splice\(idx\)/.test(src))
check('存在 splice 截断（重试回复）', /messages\.value\.splice\(userIdx\)/.test(src))

// ---- 4. ChatMessage 卸载时确实释放 blob（key 生效才有意义）----
const cm = readFileSync(resolve(here, '../src/components/ChatMessage.vue'), 'utf8')
check('ChatMessage 在 onUnmounted 释放 SVG blob', /onUnmounted\(\(\) => \{[\s\S]{0,200}releaseRig\(\)/.test(cm))
check('ChatMessage 在 onUnmounted 释放 MCP 图片 blob', /onUnmounted\(\(\) => \{[\s\S]{0,300}releaseMcpImg\(\)/.test(cm))

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exit(failed === 0 ? 0 : 1)
