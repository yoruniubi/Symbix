/**
 * 桌宠皮肤纹理「切来切去」不泄漏的回归测试。
 *
 * 运行:`node --experimental-strip-types tests/petSkinTexture.test.ts`
 *
 * 背景:Home.vue 的 onMounted 初次加载过 `Assets.load(assetUrl(path))`,
 * 但只在 `loadPetTexture()` 里才给 `loadedAssetUrl` 赋值。于是第一次换肤时
 * `if (loadedAssetUrl)` 是 null → 跳过 unload → 首张图集永久留在
 * Pixi 的 `loader.promiseCache` + `Cache` 里,再也回收不掉。
 *
 * 另一个放大器:SkinWindow 一次换肤会连发三条信号
 * (emit 全局 / emitTo(main) / localStorage petSwitchSignal),而
 * `onPetSwitched` 里的"去重"是个空壳 if(体里什么都没有),导致一次换肤
 * 跑 2~3 遍完整的 unload + load。
 *
 * 这里用真实的 pixi Loader 复刻这两条路径,钉住行为。
 */
import { Loader } from 'pixi.js'

let failed = 0
function check(name: string, ok: boolean, detail = '') {
  console.log(ok ? `  PASS ${name}` : `  FAIL ${name}${detail ? ': ' + detail : ''}`)
  if (!ok) failed++
}

const PATH = '/codex_pet/frieren/spritesheet.webp'
const CACHE_BUST = 1700000000000

/** 造一个只操作 promiseCache 的假 loader（等价真实 Loader 的缓存语义）。 */
function makeLoader() {
  const L = new Loader() as any
  L.promiseCache = Object.create(null)
  const fakeLoad = (url: string) => {
    L.promiseCache[url] = {
      promise: Promise.resolve({ destroyed: false, src: url }),
      parser: { unload: (a: any) => { a.destroyed = true } },
    }
  }
  // 复刻 Loader.unload 的真实实现:查不到就静默返回（不报错、也不释放）
  const unload = (url: string): boolean => {
    if (!L.promiseCache[url]) return false
    delete L.promiseCache[url]
    return true
  }
  return { L, fakeLoad, unload, count: () => Object.keys(L.promiseCache).length }
}

// ── 1. 修复前：初次不登记 → 首张图集永久漏 ──────────────
{
  const { fakeLoad, unload, count } = makeLoader()
  let loaded: string | null = null // ← 关键：初次加载没赋值
  fakeLoad(`http://h${PATH}`)
  for (let i = 0; i < 10; i++) {
    if (loaded) unload(loaded)
    const u = `http://h${PATH}?_t=${CACHE_BUST + i}`
    fakeLoad(u)
    loaded = u
  }
  check('修复前的行为：确实会漏 1 张图集', count() === 2, `残留 ${count()} 条`)
}

// ── 2. 修复后：初次登记 + 先载入后卸载 → 恒为 1 ──────────
{
  const { fakeLoad, unload, count } = makeLoader()
  let cur = `http://h${PATH}`
  fakeLoad(cur) // 初次加载并登记
  let hits = 0
  for (let i = 0; i < 10; i++) {
    const prev = cur
    const u = `http://h${PATH}?_t=${CACHE_BUST + i}`
    fakeLoad(u)            // 1) 先载入新的
    cur = u                // 2) sprite.textures 换过去
    if (unload(prev)) hits++ // 3) 再卸载旧的
  }
  check('修复后：切 10 次全部命中卸载', hits === 10, `${hits}/10`)
  check('修复后：缓存恒为 1 条（只留当前用的）', count() === 1, `残留 ${count()} 条`)
}

// ── 3. 去重：同 key 连发只处理一次，但过一会儿/换别的要生效 ──
{
  const DEDUP_MS = 1500
  let lastKey = ''
  let lastAt = 0
  let processed = 0
  const onSwitched = (key: string, now: number): boolean => {
    if (key && key === lastKey && now - lastAt < DEDUP_MS) return false
    lastKey = key
    lastAt = now
    processed++
    return true
  }
  const t0 = CACHE_BUST
  onSwitched('frieren|/a.webp', t0)         // emit 全局
  onSwitched('frieren|/a.webp', t0 + 20)    // emitTo(main)
  onSwitched('frieren|/a.webp', t0 + 40)    // localStorage storage 事件
  check('三条连发只处理 1 次', processed === 1, `处理了 ${processed} 次`)

  onSwitched('frieren|/a.webp', t0 + 5000)  // 用户 5s 后手动再点同一个 → 必须生效
  check('超过窗口后同 key 可再次生效', processed === 2, `处理了 ${processed} 次`)

  onSwitched('other|/b.webp', t0 + 5020)    // 立刻换别的皮肤 → 必须生效
  check('换不同皮肤立刻生效', processed === 3, `处理了 ${processed} 次`)
}

// ── 4. 空壳 if 的静态检查：源码里不该再有那种写法 ──────────
{
  const { readFileSync } = await import('node:fs')
  const { fileURLToPath } = await import('node:url')
  const { dirname, resolve } = await import('node:path')
  const here = dirname(fileURLToPath(import.meta.url))
  const src = readFileSync(resolve(here, '../src/pages/Home.vue'), 'utf8')

  // 空壳去重的特征：if (...) { 只有注释 }
  const hollow = /if \(key && key === lastPetSwitchKey\) \{\s*\/\/[^\n]*\n\s*\}/
  check('onPetSwitched 不再有空壳去重', !hollow.test(src))

  check('去重带时间窗口', /lastPetSwitchAt/.test(src))
  check('去重窗口有常量', /SKIN_SWITCH_DEDUP_MS\s*=\s*\d+/.test(src))

  // 卸载必须在 sprite.textures 赋值之后
  const fnStart = src.indexOf('async function loadPetTexture')
  const fnEnd = src.indexOf('async function onPetSwitched')
  const body = src.slice(fnStart, fnEnd)
  const iAssign = body.indexOf('sprite.textures =')
  const iUnload = body.indexOf('Assets.unload(prevAssetUrl)')
  check('loadPetTexture 找得到 sprite.textures 赋值', iAssign > 0)
  check('loadPetTexture 找得到卸载旧图集', iUnload > 0)
  check(
    '卸载发生在换纹理之后（先切引用再销毁）',
    iUnload > iAssign,
    `textures@${iAssign} unload@${iUnload}`,
  )

  // 初次加载必须登记 loadedAssetUrl
  const mountStart = src.indexOf('onMounted(async () => {')
  const mountBody = src.slice(mountStart, mountStart + 6000)
  check('初次加载登记 initialAssetUrl', /initialAssetUrl\s*=\s*assetUrl\(/.test(mountBody))
  check('初次加载写回 loadedAssetUrl', /loadedAssetUrl\s*=\s*initialAssetUrl/.test(mountBody))
}

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exit(failed === 0 ? 0 : 1)
