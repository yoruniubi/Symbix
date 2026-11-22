/**
 * 两个「长跑必爆」的内存回归测试。
 *
 * 运行:`node --experimental-strip-types tests/memLeakWaves.test.ts`
 *
 * 背景(真实采样):
 *   - 用户机器 16GB,弹幕窗 renderer 单进程冲到 **8268MB**,总 RENDER 峰值 13.2GB,
 *     系统只剩 2.1GB;关掉弹幕窗后**立刻**回落到 727MB。
 *   - 该窗口 2520x1680 物理分辨率(DPI 2x)、全屏透明。
 *   - 同期 chat 窗口恒 190MB、JS 堆 40MB、blobs=0 —— 完全无辜。
 *
 * 两波修复:
 *   第一波:ChatMessage 稳定 key / Audio 收尾幂等 / 哨兵补 blobs
 *   第二波(本文件):弹幕窗合成层 + 桌宠换肤并发竞态
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

let failed = 0
function check(name: string, ok: boolean, detail = '') {
  console.log(ok ? `  PASS ${name}` : `  FAIL ${name}${detail ? ': ' + detail : ''}`)
  if (!ok) failed++
}

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const danmakuSrc = readFileSync(resolve(root, 'src/pages/DanmakuWindow.vue'), 'utf8')
const homeSrc = readFileSync(resolve(root, 'src/pages/Home.vue'), 'utf8')

/** 去掉 /* *\/ 注释与 // 行注释,免得注释里提到的属性名把断言搞成假阴性 */
function stripComments(s: string): string {
  return s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
}

/** 按「大括号配对」从一个 `{` 的位置截出完整块(内含嵌套对象也不会截断) */
function sliceBraceBlock(src: string, startIdx: number): string {
  const open = src.indexOf('{', startIdx)
  if (open < 0) return ''
  let depth = 0
  for (let i = open; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}') {
      depth--
      if (depth === 0) return src.slice(open + 1, i)
    }
  }
  return ''
}

// ── 1. 弹幕窗:每个气泡一个合成层,不能用常驻 will-change ─────────
{
  const clean = stripComments(danmakuSrc)
  // 注意：JS 里也有 querySelector('.danmaku-item.dm-proactive')，必须定位到样式规则
  const at = clean.indexOf('.danmaku-item {')
  const block = at >= 0 ? sliceBraceBlock(clean, at) : ''
  check('抽到 .danmaku-item 样式块', block.length > 0)
  check(
    '.danmaku-item 不再常驻 will-change:transform',
    !/will-change\s*:\s*transform/.test(block),
    '全屏透明窗里每个气泡都会被强升独立图层',
  )
  check('气泡仍然在飘(danmaku-move 保留)', /animation:\s*danmaku-move/.test(block))
}

// ── 2. 弹幕窗:无限循环动画不能动 box-shadow ──────────────────────
{
  const clean = stripComments(danmakuSrc)
  const at = clean.indexOf('@keyframes proactive-pulse')
  const kf = at >= 0 ? sliceBraceBlock(clean, at) : ''
  check('抽到 proactive-pulse keyframes', kf.length > 0)
  check(
    'proactive-pulse 不再动画 box-shadow',
    !/box-shadow/.test(kf),
    'box-shadow 每帧整层重光栅化且不进缓存 —— 8.2GB 的直接原因',
  )
  check(
    '呼吸感改用合成器友好属性(opacity/border-color)',
    /opacity|border-color/.test(kf),
  )
}

// ── 3. 弹幕窗:气泡数量必须有上限 ─────────────────────────────────
{
  const clean = stripComments(danmakuSrc)
  const m = clean.match(/const\s+MAX_ACTIVE_DANMAKU\s*=\s*(\d+)/)
  check('存在 MAX_ACTIVE_DANMAKU 常量', !!m, '没有上限时密集推送会把层数堆到爆')
  if (m) {
    const cap = Number(m[1])
    check('上限是有限正整数', Number.isInteger(cap) && cap > 0 && cap <= 200, `cap=${cap}`)
  }
  // 必须真的用上限裁剪,且裁剪发生在 push 之后
  const pushIdx = clean.indexOf('activeDanmaku.value.push(item)')
  const useIdx = clean.indexOf('MAX_ACTIVE_DANMAKU', clean.indexOf('activeDanmaku.value.push(item)'))
  check('push 之后用 MAX_ACTIVE_DANMAKU 裁剪', pushIdx > 0 && useIdx > pushIdx)
  check(
    '裁剪用的是 slice/splice(真的缩短数组)',
    /activeDanmaku\.value\s*=\s*activeDanmaku\.value\.slice\(/.test(clean),
  )
}

// ── 4. 弹幕窗:哨兵必须上报(否则涨到 8GB 日志里都看不到)──────────
{
  const clean = stripComments(danmakuSrc)
  const at = clean.indexOf('startMemorySentinel(')
  const opts = at >= 0 ? sliceBraceBlock(clean, at) : ''
  check('抽到 startMemorySentinel 调用', opts.length > 0)
  check(
    '弹幕窗哨兵传了 reportUrl',
    /reportUrl\s*:/.test(opts),
    '之前没传 → 日志里从来没有 window=danmaku,监控盲区',
  )
  check('弹幕窗哨兵上报 messages(气泡条数)', /messages\s*:/.test(opts))
}

// ── 5. 桌宠换肤:并发竞态必须用令牌拦掉 ───────────────────────────
{
  check('存在 textureLoadSeq 令牌', /let\s+textureLoadSeq\s*=\s*0/.test(homeSrc))
  const idxFn = homeSrc.indexOf('async function loadPetTexture')
  const idxSeq = homeSrc.indexOf('const mySeq = ++textureLoadSeq')
  const idxLoad = homeSrc.indexOf('const texture = await loadWithRetry', idxFn)
  const idxStale = homeSrc.indexOf('if (mySeq !== textureLoadSeq)', idxLoad)
  check('令牌在 loadPetTexture 内领取', idxSeq > idxFn && idxSeq > 0)
  check('令牌在 await 载入之前领取(否则抢不到)', idxSeq < idxLoad)
  check('await 回来后检查令牌是否过期', idxStale > idxLoad, '过期必须整体作废')
  // 过期分支必须自己收掉刚载进来的图集,否则只是换成了另一种泄漏
  const staleBlock = idxStale >= 0 ? sliceBraceBlock(homeSrc, idxStale) : ''
  check(
    '过期分支卸载自己刚载的图集',
    /Assets\.unload\(loadPath\)/.test(staleBlock),
    'invalid-async 的白载不能留着',
  )
}

// ── 6. 令牌语义:模拟两个并发换肤,只有最新的能落地 ────────────────
{
  // 复刻 Home.vue 的令牌判定,验证「后发者赢、先发者丢弃且不碰全局状态」
  let seq = 0
  const state = { loaded: 'initial', sprite: 'initial' }
  const unloaded: string[] = []

  /** 模拟一次换肤:载入耗时 loadMs,期间可能有别的请求插入 */
  function switchTo(url: string, loadMs: number): Promise<void> {
    const mySeq = ++seq
    return new Promise<void>((res) => {
      setTimeout(() => {
        if (mySeq !== seq) {
          unloaded.push(url) // 作废:收掉自己刚载的
          res()
          return
        }
        const prev = state.loaded
        state.loaded = url
        state.sprite = url
        if (prev && prev !== url && mySeq === seq) unloaded.push(prev)
        res()
      }, loadMs)
    })
  }

  await Promise.all([
    switchTo('A', 50), // 慢:先发但后到
    switchTo('B', 10), // 快:后发但先到 → 应该赢
  ])

  check('并发换肤后最终生效的是最后一次请求', state.sprite === 'B', `实际 ${state.sprite}`)
  check('过期的那次把自己载的图集收掉了', unloaded.includes('A'), `unloaded=${unloaded}`)
  check('当前在用的图集没被误卸载', !unloaded.includes('B'), `unloaded=${unloaded}`)

  // 对照:没有令牌时(修复前)会发生什么 —— 先发的慢请求会把 sprite 覆回旧图集
  let seq2 = 0
  const bad = { loaded: 'initial', sprite: 'initial' }
  function badSwitch(url: string, loadMs: number): Promise<void> {
    seq2++
    return new Promise<void>((res) => {
      setTimeout(() => {
        bad.loaded = url
        bad.sprite = url // 无条件覆盖 → 慢请求后到就把快的盖掉
        res()
      }, loadMs)
    })
  }
  await Promise.all([badSwitch('A', 50), badSwitch('B', 10)])
  check(
    '反向锚点:无令牌时最终生效的是「先发后到」的那个(错误)',
    bad.sprite === 'A',
    `实际 ${bad.sprite}`,
  )
}

if (failed > 0) {
  console.log(`\n${failed} 项失败`)
  process.exit(1)
}
console.log('\n全部通过')
