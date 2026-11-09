import { Rectangle, Texture, TextureSource } from 'pixi.js'

/**
 * 造一个「帧纹理获取器」，同一个 TextureSource 下每种帧组合只建一次。
 *
 * 必须缓存的原因：Pixi v8 的 `Texture.source =` setter 里有一句
 * `value.on('resize', this.update, this)` —— 每 `new` 一个 Texture 就往
 * 长命的 `TextureSource` 上挂一个 resize 监听，而且**整个 Pixi 里没有任何
 * 地方会解除它**（实测：对一个 source 建 100 个 Texture 后，
 * `source._events.resize` 就有 100 个监听器）。
 *
 * 桌宠一天切几千次状态、每次 8 帧，就是几万个 Texture 被同一个 source
 * 强引用住，GC 回收不掉 —— renderer 私有内存实测涨到 6.3 GB。
 *
 * 状态组合本身有限（行 × 帧数 × 序列，几十种），建一次终身复用即可。
 * 用 WeakMap 挂 source：换皮肤时 baseSource 被替换，旧的一整批自动可回收。
 *
 * Args:
 *   frameW: 单帧宽（px）
 *   frameH: 单帧高（px）
 * Returns:
 *   getFrames(source, row, frameCount, frameIndices?) -> Texture[]
 */
export function createPetFrameGetter(frameW: number, frameH: number) {
  const cache = new WeakMap<TextureSource, Map<string, Texture[]>>()

  return function getFrames(
    source: TextureSource,
    row: number,
    frameCount: number,
    frameIndices?: readonly number[],
  ): Texture[] {
    let perSource = cache.get(source)
    if (!perSource) {
      perSource = new Map()
      cache.set(source, perSource)
    }
    const key = `${row}:${frameCount}:${frameIndices ? frameIndices.join(',') : ''}`
    const cached = perSource.get(key)
    if (cached) return cached
    const frames = Array.from({ length: frameCount }, (_, i) =>
      new Texture({
        source,
        frame: new Rectangle(
          (frameIndices?.[i] ?? i) * frameW,
          row * frameH,
          frameW,
          frameH,
        ),
      }),
    )
    perSource.set(key, frames)
    return frames
  }
}
