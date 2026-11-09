/**
 * 桌宠帧纹理缓存的回归测试。
 *
 * 运行:node --experimental-strip-types tests/petFrameCache.test.ts
 *
 * 这个测试盯死的是一个真实事故:每次状态切换都 `new Texture({source})`,
 * 而 Pixi v8 的 `Texture.source` setter 会往长命的 TextureSource 上挂一个
 * `resize` 监听且永不解除 —— 桌宠一天切几千次状态,几万个 Texture 被强引用,
 * renderer 私有内存涨到 6.3 GB。
 *
 * 所以这里不只测「缓存命中」,更要测「source 上的监听器数量不再增长」——
 * 那才是内存是否止血的直接指标。
 */

import { TextureSource } from 'pixi.js'
import { createPetFrameGetter } from '../src/utils/petFrameCache.ts'

let failed = 0
function check(name: string, actual: unknown, expected: unknown) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  console.log(ok ? `  PASS ${name}` : `  FAIL ${name}: got ${JSON.stringify(actual)} want ${JSON.stringify(expected)}`)
  if (!ok) failed++
}

/** TextureSource 上挂了多少个 resize 监听(Pixi 用 EventEmitter3,单个监听不是数组) */
function resizeListeners(src: TextureSource): number {
  const ev = (src as any)._events?.resize
  if (!ev) return 0
  return Array.isArray(ev) ? ev.length : 1
}

// ── 1. 先证明「不缓存会涨」——这是修复的前提,机制变了这个测试要跟着变 ──
const bare = new TextureSource({ width: 512, height: 512 })
check('新 source 初始无监听', resizeListeners(bare), 0)
// 每次 1 帧、50 次 → 50 个 Texture → 50 个监听
for (let i = 0; i < 50; i++) {
  createPetFrameGetter(64, 64)(bare, i % 3, 1, undefined)
}
check('不缓存:50 次调用留下 50 个监听(证明机制存在)', resizeListeners(bare), 50)

// ── 2. 缓存后:同参数反复取,监听器数量恒定 ──
const src = new TextureSource({ width: 512, height: 512 })
const getFrames = createPetFrameGetter(64, 64)

const first = getFrames(src, 2, 8, [0, 1, 2, 3, 4, 5, 6, 7])
check('首次取到 8 帧', first.length, 8)
const listenersAfterFirst = resizeListeners(src)

for (let i = 0; i < 500; i++) {
  getFrames(src, 2, 8, [0, 1, 2, 3, 4, 5, 6, 7])
}
check('500 次重复取 → 监听器不涨', resizeListeners(src), listenersAfterFirst)

// ── 3. 同参数返回同一批对象(不是重建) ──
const again = getFrames(src, 2, 8, [0, 1, 2, 3, 4, 5, 6, 7])
check('缓存命中返回同一数组', again === first, true)
check('缓存命中帧对象也相同', again[0] === first[0], true)

// ── 4. 不同状态各建一次,互不串味 ──
const idle = getFrames(src, 0, 4)
const run = getFrames(src, 1, 6, [0, 1, 2, 3, 4, 5])
check('idle 4 帧', idle.length, 4)
check('run 6 帧', run.length, 6)
check('两批首帧不同', idle[0] === run[0], false)
check('不同状态各自只建一次', resizeListeners(src), listenersAfterFirst + 10)

// 再取一遍不同的两个状态:数量不该再动
getFrames(src, 0, 4)
getFrames(src, 1, 6, [0, 1, 2, 3, 4, 5])
check('重复取其他状态也不涨', resizeListeners(src), listenersAfterFirst + 10)

// ── 5. 帧矩形切分正确 ──
const g = createPetFrameGetter(192, 208)
const frames = g(src, 3, 2)
check('第 0 帧 x', (frames[0] as any).frame.x, 0)
check('第 0 帧 y = row*208', (frames[0] as any).frame.y, 624)
check('第 1 帧 x = 192', (frames[1] as any).frame.x, 192)
check('帧宽高', [(frames[0] as any).frame.width, (frames[0] as any).frame.height], [192, 208])

// ── 6. frameIndices 会改变实际取哪几帧,且和默认序列分开缓存 ──
const seq = g(src, 3, 2, [2, 4])
check('按索引取帧:第 0 帧 x = 2*192', (seq[0] as any).frame.x, 384)
check('按索引取帧:第 1 帧 x = 4*192', (seq[1] as any).frame.x, 768)
check('自定义序列与默认序列分开缓存', seq === g(src, 3, 2), false)

// ── 7. 不同 source 各自独立(换皮肤) ──
const src2 = new TextureSource({ width: 512, height: 512 })
const onSrc2 = g(src2, 3, 2)
check('换 source 不会复用旧帧', onSrc2[0] === g(src, 3, 2)[0], false)

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exit(failed === 0 ? 0 : 1)
