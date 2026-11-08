/**
 * 从一条 assistant 消息的工具步骤里提取「本轮真正产出的文件」。
 *
 * 背景:Agent 写完文件往往只在正文里说一句「已保存到 C:\...\报告.docx」,用户还得照着
 * 路径去翻。这份清单喂给 MessageArtifactBar,把产物直接列成卡片(打开 / 定位 / 预览)。
 *
 * 判定原则 —— 宁可少列,也不要乱列:
 * 1. 只认 `status === 'done'` 的步骤:调用中 / 等审批 / 被拒 / 跳过都没有真的落盘;
 * 2. 只认绝对路径 + 带扩展名:相对路径判断不了落在哪,而 `path: "."` 这类入参满地都是;
 * 3. 路径来源分三路,且都要求该步骤是「会写盘的工具」:
 *    - 入参里的输出字段(create_file/edit_file 的 file_path、doc_tools 的 out_path);
 *    - 返回值里的输出字段(doc_tools / download_file 的 JSON `path`、
 *      search_and_replace 的 `results[].file`、`File created:` / `File saved:` 文案);
 *    - MCP 绘图工具的落盘标记 `[Image saved: <路径>]`(任何工具都可能带,标记本身够唯一);
 *    读类工具(read_file / list_files / search_files)的返回值一律不扫,否则会把
 *    「读到的文件」当成「产出的文件」;
 * 4. 同一路径多次出现按「先新建后改写」只占一格,不重复列。
 */

export type ArtifactKind =
  | 'image'
  | 'doc'
  | 'sheet'
  | 'slide'
  | 'pdf'
  | 'text'
  | 'code'
  | 'archive'
  | 'other'

/** 产物是怎么来的:新建 / 改写 / 下载 / 绘图落盘。 */
export type ArtifactOp = 'create' | 'edit' | 'download' | 'image'

export interface MessageArtifact {
  /** 绝对路径原样(Windows 反斜杠保留),直接喂 /files/read 与 revealItemInDir */
  path: string
  /** 文件名 */
  name: string
  /** 所在目录,卡片副标题 */
  dir: string
  kind: ArtifactKind
  op: ArtifactOp
}

/** 单条消息最多列多少个产物,避免脚本批量写盘时把聊天页撑炸 */
const MAX_ARTIFACTS = 24

const KIND_BY_EXT: Record<string, ArtifactKind> = {
  '.png': 'image', '.jpg': 'image', '.jpeg': 'image', '.gif': 'image',
  '.webp': 'image', '.bmp': 'image', '.svg': 'image', '.ico': 'image',
  '.docx': 'doc', '.doc': 'doc', '.odt': 'doc', '.rtf': 'doc',
  '.xlsx': 'sheet', '.xls': 'sheet', '.csv': 'sheet',
  '.pptx': 'slide', '.ppt': 'slide',
  '.pdf': 'pdf',
  '.md': 'text', '.txt': 'text', '.log': 'text',
  '.zip': 'archive', '.7z': 'archive', '.rar': 'archive', '.gz': 'archive', '.tar': 'archive',
}

const CODE_EXTS = new Set([
  '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.vue', '.py', '.rs', '.go',
  '.java', '.c', '.cc', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php', '.sh',
  '.ps1', '.bat', '.cmd', '.html', '.css', '.scss', '.less', '.json', '.yaml',
  '.yml', '.toml', '.ini', '.xml', '.sql', '.lua', '.kt', '.swift',
])

/** 写入类工具 → 入参里代表「输出文件」的字段名(按优先级)。 */
const WRITE_ARG_TOOLS: Record<string, string[]> = {
  create_file: ['file_path'],
  edit_file: ['file_path'],
  write_to_file: ['file_path', 'path'],
  replace_in_file: ['file_path', 'path'],
  md_to_docx: ['out_path'],
  md_to_xlsx: ['out_path'],
  md_to_pptx: ['out_path'],
  md_to_pdf: ['out_path'],
}

/** 允许扫描返回值找输出路径的工具(必须是「会写盘」的,读类工具不许进来)。 */
const RESULT_SCAN_TOOLS = new Set([
  'create_file', 'edit_file', 'write_to_file', 'replace_in_file',
  'search_and_replace',
  'md_to_docx', 'md_to_xlsx', 'md_to_pptx', 'md_to_pdf',
  'download_file',
])

/** 返回值里代表输出路径的 JSON 字段名。 */
const RESULT_PATH_KEYS = new Set([
  'path', 'file', 'file_path', 'out_path', 'output_path', 'saved_to', 'dest',
])

const EDIT_TOOLS = new Set(['edit_file', 'write_to_file', 'replace_in_file', 'search_and_replace'])
const DOWNLOAD_TOOLS = new Set(['download_file'])

/** `[Image saved: C:\a\b.png]` —— connector 把 MCP 返回的图片落盘后打的标记。 */
const IMAGE_MARK = /\[Image saved:\s*([^\]\r\n]+?)\s*\]/

/** `File created: <路径>` / `File saved: <路径>`(file_tools 的固定文案)。 */
const FILE_TEXT_MARK = /File (?:created|saved):\s*([^\r\n]+)/

/**
 * 该路径像不像「真的产出文件」:绝对路径 + 带扩展名。
 * 相对路径、目录、`Error: ...` 文案都会被这一条挡掉。
 */
function looksProducedPath(path: string): boolean {
  if (!/^(?:[A-Za-z]:[\\/]|\\\\|\/)/.test(path)) return false
  if (path.length > 500) return false
  if (/^[A-Za-z]:[\\/]?$/.test(path)) return false
  return /\.[A-Za-z0-9]{1,8}$/.test(path)
}

/** 去掉包裹的引号/括号/句末标点,便于后续判绝对路径。 */
function cleanPath(raw: unknown): string {
  if (typeof raw !== 'string') return ''
  let s = raw.trim()
  s = s.replace(/^[`'"<(\[【]+/, '').replace(/[`'">)\]】，。；;,]+$/, '')
  return s.trim()
}

function extOf(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i).toLowerCase() : ''
}

/** 按扩展名判产物类型。 */
export function artifactKindOf(name: string): ArtifactKind {
  const ext = extOf(name)
  if (KIND_BY_EXT[ext]) return KIND_BY_EXT[ext]
  if (CODE_EXTS.has(ext)) return 'code'
  return 'other'
}

/** 拆出文件名与所在目录(兼容 `/` 与 `\`)。 */
function splitPath(path: string): { name: string; dir: string } {
  const norm = path.replace(/\//g, '\\')
  const i = norm.lastIndexOf('\\')
  if (i < 0) return { name: norm, dir: '' }
  return { name: norm.slice(i + 1), dir: norm.slice(0, i) }
}

function asText(v: unknown): string {
  if (typeof v === 'string') return v
  try {
    return JSON.stringify(v ?? '')
  } catch {
    return ''
  }
}

/** 从入参 JSON 里取指定字段。入参在 steps 里是字符串,解析失败就当没有。 */
function argsObject(raw: unknown): Record<string, unknown> | null {
  if (raw && typeof raw === 'object') return raw as Record<string, unknown>
  const text = typeof raw === 'string' ? raw.trim() : ''
  if (!text.startsWith('{')) return null
  try {
    const parsed = JSON.parse(text)
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null
  } catch {
    return null
  }
}

/** 递归收集 JSON 结构里 RESULT_PATH_KEYS 指定的路径(限深,防大结果把栈打穿)。 */
function collectJsonPaths(value: unknown, out: string[], depth = 0): void {
  if (depth > 4 || value == null || out.length >= MAX_ARTIFACTS) return
  if (Array.isArray(value)) {
    for (const v of value) collectJsonPaths(v, out, depth + 1)
    return
  }
  if (typeof value !== 'object') return
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    if (typeof v === 'string' && RESULT_PATH_KEYS.has(k.toLowerCase())) {
      const p = cleanPath(v)
      if (looksProducedPath(p)) out.push(p)
      continue
    }
    collectJsonPaths(v, out, depth + 1)
  }
}

/** 从某一步的返回值里挖输出路径。 */
function pathsFromResult(result: unknown): string[] {
  const found: string[] = []
  const text = asText(result).trim()
  if (!text) return found
  if (text.startsWith('{') || text.startsWith('[')) {
    try {
      collectJsonPaths(JSON.parse(text), found)
    } catch {
      // 不是严格 JSON,继续走文案匹配
    }
  }
  const file = FILE_TEXT_MARK.exec(text)
  if (file) {
    const p = cleanPath(file[1])
    if (looksProducedPath(p)) found.push(p)
  }
  return found
}

/**
 * 同一路径多次出现时的取舍:先用 create 列出,后续变成 edit 就升级展示,
 * 下载/绘图标记比泛化路径更具体,优先覆盖。
 */
function opRank(op: ArtifactOp): number {
  return op === 'image' ? 4 : op === 'download' ? 3 : op === 'edit' ? 2 : 1
}

function safeOp(name: string): ArtifactOp {
  if (DOWNLOAD_TOOLS.has(name)) return 'download'
  if (EDIT_TOOLS.has(name)) return 'edit'
  return 'create'
}

/**
 * 主入口:把一条消息的 steps 变成产物清单(按出现顺序,已去重)。
 *
 * @param steps Message.steps(形状 {name,arguments,result,status}[])
 * @returns 产物清单;没有产物时返回空数组,调用方据此整块不渲染
 */
export function collectMessageArtifacts(steps: unknown): MessageArtifact[] {
  const list = Array.isArray(steps) ? steps : []
  const byPath = new Map<string, MessageArtifact>()

  const push = (rawPath: string, op: ArtifactOp) => {
    const path = cleanPath(rawPath)
    if (!looksProducedPath(path)) return
    const key = path.toLowerCase()
    const { name: fileName, dir } = splitPath(path)
    const existing = byPath.get(key)
    if (existing) {
      if (opRank(op) > opRank(existing.op)) existing.op = op
      return
    }
    if (byPath.size >= MAX_ARTIFACTS) return
    byPath.set(key, { path, name: fileName, dir, kind: artifactKindOf(fileName), op })
  }

  for (const step of list) {
    const rec = step as { name?: unknown; arguments?: unknown; result?: unknown; status?: unknown } | null
    if (!rec) continue
    // 只有真的落地的步骤才算:调用中 / 等审批 / 被拒 / 跳过都还没写盘
    if (String(rec.status || '').trim().toLowerCase() !== 'done') continue
    const tool = String(rec.name || '').trim().toLowerCase()
    if (!tool) continue

    // ① 入参:写盘类工具明确的输出字段
    const argKeys = WRITE_ARG_TOOLS[tool]
    if (argKeys) {
      const args = argsObject(rec.arguments)
      for (const k of argKeys) {
        const v = args?.[k]
        if (typeof v !== 'string') continue
        push(v, safeOp(tool))
        break
      }
    }

    // ② 返回值:只扫会写盘的工具(读类工具的返回值是「读到的」,不是「产出的」)
    if (RESULT_SCAN_TOOLS.has(tool)) {
      for (const p of pathsFromResult(rec.result)) {
        // 图片落盘标记统一在 ③ 里按 image 归类,这里不重复判定
        push(p, safeOp(tool))
      }
    }

    // ③ MCP 绘图落盘标记:任何工具都可能带,标记本身足够唯一
    const imgMark = IMAGE_MARK.exec(asText(rec.result))
    if (imgMark) {
      const p = cleanPath(imgMark[1])
      if (looksProducedPath(p)) push(p, 'image')
    }
  }

  return Array.from(byPath.values())
}

/** 卡片上「能不能点开看」:图片走字节流,文本/代码走 /files/read。 */
export function canPreviewArtifact(a: MessageArtifact): boolean {
  return a.kind === 'image' || a.kind === 'text' || a.kind === 'code'
}
