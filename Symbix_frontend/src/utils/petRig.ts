/**
 * pet-forge 的 rig 源文件(base.svg)定位工具。
 *
 * Agent 调 create_file / execute_command 时参数里会带 base.svg 路径:
 * - create_file 的 arguments 是 JSON 文本,Windows 路径里的反斜杠被转义成 `\\`;
 * - execute_command 的 command 是普通字符串,路径可能用正斜杠、也可能带引号。
 * 这里统一还原成真实路径,交给 /api/files/read 读取。
 */

/**
 * 匹配一段「以 base.svg 结尾、且看着真的像路径」的片段。
 *
 * 不能写成 `[^"'\s,;]*base\.svg`:工具参数里经常混着自然语言说明(例如
 * 「…产出遵循你固定的桌宠资源结构(base.svg)」),那样会把一整句话当成路径,
 * 前端就会拿着这段乱码反复去读文件,把后端 404 刷屏。所以这里:
 * - 字符集只留路径里真会出现的:字母数字 / `_` `.` `-` / 斜杠 / 盘符冒号 / 中文;
 * - 中文标点、括号、空白、引号一律不跨过(匹配会被截断或直接失败);
 * - 必须带目录分隔符,光一个 `base.svg` 定位不到文件。
 */
const RIG_HIT = /[A-Za-z0-9_\u4e00-\u9fff.\-\\/:]+[\\/][A-Za-z0-9_\u4e00-\u9fff.\-\\/:]*base\.svg/i

/** JSON 文本里的转义反斜杠还原成单斜杠(`F:\\a\\base.svg` → `F:\a\base.svg`)。 */
function unescapePath(raw: string): string {
  return raw.replace(/\\\\/g, '\\')
}

function asText(raw: unknown): string {
  if (typeof raw === 'string') return raw
  if (raw === null || raw === undefined) return ''
  try {
    return JSON.stringify(raw) || ''
  } catch {
    return ''
  }
}

/** 在解析后的参数对象里找第一个命中 base.svg 的字符串(优先 path 字段)。 */
function findInValue(value: unknown, depth = 0): string {
  if (depth > 6) return ''
  if (typeof value === 'string') {
    const hit = value.match(RIG_HIT)
    return hit ? hit[0] : ''
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const hit = findInValue(item, depth + 1)
      if (hit) return hit
    }
    return ''
  }
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    // 路径通常在 path / file / --rig 这类字段里,先看它们,避免误取 content 里的 SVG 文本
    for (const key of ['path', 'file', 'file_path', 'rig', 'target']) {
      const hit = findInValue(record[key], depth + 1)
      if (hit) return hit
    }
    for (const item of Object.values(record)) {
      const hit = findInValue(item, depth + 1)
      if (hit) return hit
    }
  }
  return ''
}

/**
 * 从工具调用的 arguments 里取出 base.svg 路径。
 * 取不到(与 pet-forge 无关的步骤)返回空串。
 */
export function extractRigPath(argumentsRaw: unknown): string {
  const text = asText(argumentsRaw)
  if (!text || !/base\.svg/i.test(text)) return ''
  try {
    const parsed = JSON.parse(text)
    const hit = findInValue(parsed)
    if (hit) return hit
  } catch {
    // 不是合法 JSON:走下面的正则兜底
  }
  const fallback = text.match(RIG_HIT)
  return fallback ? unescapePath(fallback[0]) : ''
}

/** 取 base.svg 所在目录名(皮肤名),用于预览卡标题。 */
export function rigFolderName(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean)
  return parts.length >= 2 ? parts[parts.length - 2] : ''
}
