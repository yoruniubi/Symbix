/**
 * 工具返回/参数的保留上限回归测试。
 *
 * 运行:`node --experimental-strip-types tests/toolResultClamp.test.ts`
 *
 * 为什么值得单独测:这两处截断发生在**数据写入层**,不是显示层的
 * `truncateResult()`。显示层截断只影响用户看到的 800 字,原文字符串照样
 * 整份留在 `step.result` / `step.arguments` 里 —— 一个 browser_snapshot 或
 * write_file 就是几百 KB,几十轮下来能把 renderer 顶到几百 MB。
 * 所以这层封顶必须真的生效,且必须幂等(每帧都会重新 map 一次)。
 */

let failed = 0
function check(name: string, ok: boolean, detail = '') {
  console.log(ok ? `  PASS ${name}` : `  FAIL ${name}${detail ? ': ' + detail : ''}`)
  if (!ok) failed++
}

const mod = await import('../src/composables/useChatStore.ts')
const {
  clampToolResult,
  clampToolArguments,
  TOOL_RESULT_KEEP,
  TOOL_ARGS_KEEP,
  mapBackendSteps,
} = mod as any

console.log('── clampToolResult ──')
{
  const short = 'ok'
  check('短文本原样返回', clampToolResult(short) === short)

  const exact = 'x'.repeat(TOOL_RESULT_KEEP)
  check('恰好等于上限时不截断', clampToolResult(exact) === exact)

  const huge = 'y'.repeat(200_000)
  const out = clampToolResult(huge)
  check('超长文本被压到上限附近', out.length < TOOL_RESULT_KEEP + 100, `got ${out.length}`)
  check('保留了开头内容', out.startsWith('yyyy'))
  check('尾巴标明了截断', out.includes('已截断'))

  // 幂等:第二轮不能再缩水,也不能再叠一层截断提示
  const twice = clampToolResult(out)
  check('幂等', twice === out)

  check('非字符串原样返回', clampToolResult(undefined as any) === undefined)
}

console.log('── clampToolArguments ──')
{
  const short = '{"a":1}'
  check('短参数原样返回', clampToolArguments(short) === short)

  // write_file 会把整个文件内容当参数传上来
  const wholeFile = JSON.stringify({ path: 'a.ts', content: 'z'.repeat(500_000) })
  const out = clampToolArguments(wholeFile)
  check('整文件参数被压到上限附近', out.length < TOOL_ARGS_KEEP + 60, `got ${out.length}`)
  check('参数截断提示单独一份', out.includes('参数过长已截断'))
  check('参数幂等', clampToolArguments(out) === out)
}

console.log('── mapBackendSteps 全链路 ──')
{
  const bigResult = 'r'.repeat(300_000)
  const bigArgs = JSON.stringify({ content: 'w'.repeat(300_000) })
  const steps = mapBackendSteps([
    { type: 'tool_call', id: 't1', name: 'write_file', arguments: bigArgs },
    { type: 'tool_result', tool_call_id: 't1', name: 'write_file', content: bigResult },
  ])

  check('步骤数为 1', steps.length === 1, `got ${steps.length}`)
  check('arguments 已被截断', steps[0].arguments.length < TOOL_ARGS_KEEP + 60, `got ${steps[0].arguments.length}`)
  check('result 已被截断', steps[0].result.length < TOOL_RESULT_KEEP + 100, `got ${steps[0].result.length}`)

  // 体积对比:不截断的话这两个字段加起来就是 600KB 常驻
  const kept = steps[0].arguments.length + steps[0].result.length
  check('单步内存占用下降一个数量级', kept < 7000, `got ${kept}`)
}

console.log('── 不误伤:正常短返回完整保留 ──')
{
  const steps = mapBackendSteps([
    { type: 'tool_call', id: 't2', name: 'read_file', arguments: '{"path":"a.txt"}' },
    { type: 'tool_result', tool_call_id: 't2', name: 'read_file', content: 'hello world' },
  ])
  check('短参数完整', steps[0].arguments === '{"path":"a.txt"}')
  check('短结果完整', steps[0].result === 'hello world')
  check('状态正常', steps[0].status === 'done')
}

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exit(failed === 0 ? 0 : 1)
