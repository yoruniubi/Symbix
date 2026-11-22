/**
 * 「聊天窗消息列表不做窗口化」的回归测试。
 *
 * 运行:`node --experimental-strip-types tests/chatWindowVirtual.test.ts`
 *
 * 为什么值得单独测:
 * 后端日志里 `[mem] window=chat` 的实测数据表明,聊天窗 DOM 节点数随消息数
 * **严格线性**增长(每条约 230 个节点):
 *
 *   messages=2   nodes=804      messages=26  nodes=6776
 *   messages=18  nodes=4888     messages=46  nodes=10511
 *   messages=50  nodes=10599
 *
 * 而 `performance.memory` 报的 JS 堆一直只有 20~45MB —— 因为 DOM 节点的内存
 * 大头记在 Blink 的 C++ 侧,JS 堆看不到。这就是「哨兵显示健康、实际内存却在
 * 涨」的原因,也让前几轮排查完全跑偏(去查了弹幕窗)。
 *
 * 修法是只挂载最近 HISTORY_TAIL 条。这个测试锁住几个关键点,防止被改回去:
 *   1. 必须用 `v-if` 而不是 `v-show` —— v-show 只切 display,DOM 一个不少;
 *   2. `v-for` 与 `v-if` 不能同级(Vue 里 v-if 优先级高于 v-for,`idx` 会
 *      ReferenceError),必须用 `<template v-for>` 包一层;
 *   3. cutoff 必须是「冻结的下标」而不是 `length - TAIL` —— 后者每来一条新
 *      消息就推进一位,会把用户正在看的历史悄悄卸掉,整屏上移;
 *   4. 折叠面板(ChatMessage 里 reasoning / step-details)也必须是 `v-if`,
 *      因为 step.result 是工具返回全文,常常几 KB。
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const chatWin = readFileSync(resolve(here, '../src/pages/ChatWindow.vue'), 'utf8')
const chatMsg = readFileSync(resolve(here, '../src/components/ChatMessage.vue'), 'utf8')

let failed = 0
function check(name: string, cond: boolean, detail = '') {
  if (cond) {
    console.log(`  ok   ${name}`)
  } else {
    console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`)
    failed++
  }
}

console.log('聊天窗窗口化 / 折叠面板 v-if')

// ── ChatWindow:用 template v-for 包裹,内部 v-if 控制挂载 ──────────────
check(
  '消息列表用 <template v-for> 包裹',
  /<template v-for="\(msg, idx\) in messages"/.test(chatWin),
)

check(
  'ChatMessage 由 v-if 控制挂载(historyCutoff)',
  /<ChatMessage\s*\n\s*v-if="idx >= historyCutoff"/.test(chatWin),
)

check(
  'v-for 与 v-if 没有写在同一个元素上',
  !/<ChatMessage[^>]*v-for=[^>]*v-if=/.test(chatWin) &&
    !/<ChatMessage[^>]*v-if=[^>]*v-for=/.test(chatWin),
)

// ── cutoff 必须是冻结下标,不能直接 length - TAIL ──────────────────────
check(
  'historyCutoff 用的是冻结下标(historyCutoffLocked)',
  /const historyCutoff = computed\(\(\) =>\s*historyExpanded\.value \? 0 : historyCutoffLocked\.value,?\s*\)/.test(
    chatWin,
  ),
)

check(
  'cutoff 只在用户贴着底部时才推进',
  /function syncHistoryCutoff\(\)[\s\S]{0,400}isNearBottom\(\)/.test(chatWin),
)

check(
  '切会话时重置折叠状态',
  /watch\(activeSessionId,[\s\S]{0,200}historyCutoffLocked\.value = 0/.test(chatWin),
)

// ── 折叠面板:两条 v-show 必须都换成 v-if ────────────────────────────
check(
  'reasoning 面板用 v-if',
  /<div v-if="showReasoning" class="reasoning-text">/.test(chatMsg),
)
check(
  'reasoning 面板不再用 v-show',
  !/<div v-show="showReasoning"/.test(chatMsg),
)

check(
  'step-details 面板用 v-if',
  /<div v-if="expandedSteps\[Number\(i\)\]" class="step-details">/.test(chatMsg),
)
check(
  'step-details 面板不再用 v-show',
  !/<div v-show="expandedSteps/.test(chatMsg),
)

// ── 空消息隐藏仍应保留 v-show(它只是临时隐藏,不是省内存) ─────────────
check(
  'hideDuringLoading 仍用 v-show(临时隐藏空气泡,语义不变)',
  /v-show="!hideDuringLoading\(msg\)"/.test(chatWin),
)

console.log('')
if (failed > 0) {
  console.log(`${failed} 项失败`)
  process.exit(1)
}
console.log('全部通过')
