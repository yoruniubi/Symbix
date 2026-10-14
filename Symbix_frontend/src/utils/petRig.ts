/**
 * pet-forge 的 rig 源文件(base.svg)定位工具。
 *
 * 聊天页的「桌宠形象预览」卡靠它决定两件事:
 * 1. **要不要显示**(`pickPreviewRigPath`)—— 只有 rig 真的被生成出来才显示;
 * 2. **显示哪一份**(优先级见 `pickPreviewRigPath` 注释)。
 *
 * 为什么需要判断:一轮 pet-forge 里带 `base.svg` 字样的工具调用非常多 ——
 * skill 正文、read_file、list_files、propose_plan 的参数里都有,但它们只代表
 * 「看了一眼模板」,不代表用户的桌宠已经生成。不判断的话,预览卡从开工第一秒
 * 就挂着 skill 自带的 `assets/fixtures/base.svg`,用户会以为那就是自己的形象。
 */

/**
 * 匹配一段「以 base.svg 结尾、且看着真的像路径」的片段。
 *
 * 不能写成 `[^"'\s,;]*base\.svg`:工具参数里经常混着自然语言说明(例如
 * 「...产出遵循你固定的桌宠资源结构(base.svg)」),那样会把一整句话当成路径,
 * 前端就会拿着这段乱码反复去读文件,把后端 404 刷屏。所以这里:
 * - 字符集只留路径里真会出现的:字母数字 / `_` `.` `-` / 斜杠 / 盘符冒号 / 中文;
 * - 中文标点、括号、空白、引号一律不跨过(匹配会被截断或直接失败);
 * - 必须带目录分隔符,光一个 `base.svg` 定位不到文件。
 */
const RIG_HIT = /[A-Za-z0-9_\u4e00-\u9fff.\-\\/:]+[\\/][A-Za-z0-9_\u4e00-\u9fff.\-\\/:]*base\.svg/i

/** 产物目录下的 base.svg(pixiv_pet / codex_pet 任一子目录)。 */
const SHIPPED_RIG_HIT = new RegExp(
  '[A-Za-z0-9_\\u4e00-\\u9fff.\\-\\\\/:]*[\\\\/](?:pixiv_pet|codex_pet)[\\\\/]' +
  '[A-Za-z0-9_\\u4e00-\\u9fff.\\-\\\\/:]*base\\.svg', 'i',
)

/** 只提到产物目录本身(build_theme.py 的 out_dir),没带 base.svg。 */
const SHIPPED_DIR_HIT = new RegExp(
  '[A-Za-z0-9_\\u4e00-\\u9fff.\\-\\\\/:]*[\\\\/](?:pixiv_pet|codex_pet)[\\\\/]' +
  '[A-Za-z0-9_\\u4e00-\\u9fff.\\-]+', 'i',
)

/**
 * 只有「写文件」类工具才算把 rig 生成出来了。
 *
 * 读类工具(read_file / list_files / search_files)和 skill__pet-forge、propose_plan 这些
 * 也会在参数里带 base.svg,但它们只是看一眼模板,不算产出。
 */
const RIG_WRITE_TOOLS = new Set([
  'create_file',
  'edit_file',
  'write_to_file',
  'replace_in_file',
  'search_and_replace',
])

/** 还没落地的状态:调用中 / 等审批 / 被拒 / 被跳过 —— 这些都还没真的写出文件。 */
const RIG_UNLANDED_STATUS = new Set(['pending', 'awaiting_approval', 'rejected', 'skipped'])

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

/** 路径是否落在 skill 目录里(skill 自带的模板 rig,不是用户的产出)。 */
function isSkillTemplate(path: string): boolean {
  const p = '/' + path.replace(/\\/g, '/').toLowerCase()
  return p.includes('/installed_skills/') || p.includes('/assets/fixtures/')
}

/** 该步骤是不是「写 rig」的步骤(读/查看模板不算,理由见 RIG_WRITE_TOOLS 注释)。 */
function isRigWriteStep(step: unknown): boolean {
  const name = String((step as { name?: unknown } | null)?.name || '').trim().toLowerCase()
  return RIG_WRITE_TOOLS.has(name)
}

/**
 * 该步骤是否已「落地」(写出动作已经结束)。
 *
 * 预览卡只在生成**完成**后出现:否则 create_file 刚发出、文件还没建好就去读,
 * 只能读到 404(还要重试一次),体验上也不符合「生成完再展示」。
 * 状态缺失视为已落地(兼容旧消息)。
 */
function isRigLandedStep(step: unknown): boolean {
  const status = String((step as { status?: unknown } | null)?.status || '').trim().toLowerCase()
  return !RIG_UNLANDED_STATUS.has(status)
}

/**
 * 从工具调用的 arguments 里取出 base.svg 路径(不含任何「是否已生成」的判断)。
 * 取不到(与 pet-forge 无关的步骤)返回空串。
 */
function extractRigPath(argumentsRaw: unknown): string {
  const text = asText(argumentsRaw)
  if (!text || !/base\.svg/i.test(text)) return ''
  let hit = ''
  try {
    const parsed = JSON.parse(text)
    hit = findInValue(parsed)
  } catch {
    // 不是合法 JSON:走下面的正则兜底
  }
  if (!hit) {
    const fallback = text.match(RIG_HIT)
    hit = fallback ? unescapePath(fallback[0]) : ''
  }
  if (!hit || isSkillTemplate(hit)) return ''
  return hit
}

/**
 * 在整段文本里找「产物目录下的 rig」。
 *
 * 不走 findInValue:命令类参数(例如 `cp /tmp/base.svg <产物目录>/base.svg`)里
 * 往往同时出现源和目的两个路径,而 findInValue 只返第一个(源,在临时目录)。
 * 另外 `build_theme.py` 的权威路径打在**输出**里(`OK: {... "out_dir": "..."}`),
 * 所以调用方会把参数和输出拼在一起传进来。
 */
function findShippedRigPath(raw: unknown): string {
  // 先还原转义反斜杠:输出里常见 `{"out_dir":"F:\\Symbix\\..."}` 这种双反斜杠,
  // 不还原的话路径正则会直接断在反斜杠处
  const text = unescapePath(asText(raw))
  if (!text || !/[\\/](pixiv_pet|codex_pet)[\\/]/i.test(text)) return ''
  const withFile = text.match(SHIPPED_RIG_HIT)
  if (withFile) return withFile[0]
  // 只提到目录(build_theme.py 的 out_dir):拼上约定文件名 base.svg
  const dir = text.match(SHIPPED_DIR_HIT)
  if (!dir) return ''
  const base = dir[0]
  return base + (base.includes('\\') ? '\\' : '/') + 'base.svg'
}

/**
 * 从一条消息的步骤里选出用于预览的 rig 路径。
 *
 * 分两档:
 * 1. **产物目录优先** —— 参数或输出里出现 `public/pixiv_pet/<名字>/**base.svg`
 *    或 `public/codex_pet/<名字>/**base.svg` 就算。这一档不可能落在 skill 模板上,
 *    而且能拿到「用户最终看到的皮肤」那份路径(临时 rig 随时会被清理掉);
 * 2. **否则只认写文件类步骤**(见 RIG_WRITE_TOOLS)写出的 rig,并排除 skill 模板目录。
 *
 * 两档都要求该步骤已**落地**(见 isRigLandedStep):写动作还没结束时不展示,
 * 卡片的出现时机就是「生成完成」。
 *
 * 读模板 / 列目录 / 调 skill / 提计划虽然也会在参数里带 `base.svg`,但都不算「已生成」,
 * 一律不进候选;找不到就返回空串(预览卡整块不显示)。
 */
export function pickPreviewRigPath(steps: unknown): string {
  const list = Array.isArray(steps) ? steps : []
  const shipped: string[] = []
  const written: string[] = []
  for (const step of list) {
    if (!isRigLandedStep(step)) continue
    const rec = step as { arguments?: unknown; result?: unknown } | null
    const shippedHit = findShippedRigPath(`${asText(rec?.arguments)}\n${asText(rec?.result)}`)
    if (shippedHit && !shipped.includes(shippedHit)) shipped.push(shippedHit)
    if (!isRigWriteStep(step)) continue
    const hit = extractRigPath(rec?.arguments)
    if (hit && !written.includes(hit)) written.push(hit)
  }
  if (shipped.length) return shipped[shipped.length - 1]
  return written.length ? written[written.length - 1] : ''
}

/** 取 base.svg 所在目录名(皮肤名),用于预览卡标题。 */
export function rigFolderName(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean)
  return parts.length >= 2 ? parts[parts.length - 2] : ''
}