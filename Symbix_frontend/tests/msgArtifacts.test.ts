/**
 * 聊天页「本轮产物卡片」取路径的回归测试。
 *
 * 运行:`node --experimental-strip-types tests/msgArtifacts.test.ts`
 *
 * 重点盯两类翻车:
 * 1. 把**读入**的文件当成产物(read_file / list_files / search_files 的结果不许进清单);
 * 2. 没落盘的步骤(等审批 / 被拒 / 调用中)提前出现在卡片里。
 */

import {
  artifactKindOf,
  canPreviewArtifact,
  collectMessageArtifacts,
} from '../src/utils/msgArtifacts.ts'

let failed = 0

function check(name: string, actual: unknown, expected: unknown) {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a !== e) {
    console.error(`FAIL ${name}: got ${a}, want ${e}`)
    failed++
  } else {
    console.log(`ok   ${name}`)
  }
}

const step = (name: string, args: unknown, result: unknown, status = 'done') => ({
  id: `${name}-1`,
  name,
  arguments: typeof args === 'string' ? args : JSON.stringify(args),
  result,
  status,
})

// ---- 1. create_file / edit_file:入参 file_path ----
const created = collectMessageArtifacts([
  step('create_file', { file_path: 'C:\\work\\报告.md', content: '正文里也可能出现 D:\\假路径.txt' }, 'File created: C:\\work\\报告.md'),
])
check('create_file 抓到 1 条', created.length, 1)
check('create_file 路径', created[0]?.path, 'C:\\work\\报告.md')
check('create_file op=create', created[0]?.op, 'create')
check('create_file 文件名/目录', [created[0]?.name, created[0]?.dir], ['报告.md', 'C:\\work'])

const edited = collectMessageArtifacts([
  step('edit_file', { file_path: 'C:\\work\\报告.md', new_content: 'x' }, 'File saved: C:\\work\\报告.md'),
])
check('edit_file op=edit', edited[0]?.op, 'edit')

// 同一文件先建后改 -> 只占一格且升级成 edit
const dup = collectMessageArtifacts([
  step('create_file', { file_path: 'C:\\work\\a.md' }, 'File created: C:\\work\\a.md'),
  step('edit_file', { file_path: 'C:\\work\\a.md' }, 'File saved: C:\\work\\a.md'),
])
check('先建后改去重为 1 条', dup.length, 1)
check('先建后改 op 升级', dup[0]?.op, 'edit')

// ---- 2. doc_tools:返回值 JSON 里的 path ----
const docx = collectMessageArtifacts([
  step('md_to_docx', { md_content: '# t', out_path: 'C:\\out\\报告.docx' }, JSON.stringify({ success: true, path: 'C:\\out\\报告.docx', note: 'via python-docx' })),
])
check('md_to_docx 抓到 1 条', docx.length, 1)
check('md_to_docx kind=doc', docx[0]?.kind, 'doc')

// ---- 3. download_file:返回值 JSON path ----
const dl = collectMessageArtifacts([
  step('download_file', { url: 'https://x/y.png' }, JSON.stringify({
    status: 'ok', path: 'C:\\data\\downloads\\abc_screen.png', filename: 'abc_screen.png', size: 1234,
  })),
])
check('download_file op=download', dl[0]?.op, 'download')
check('download_file kind=image', dl[0]?.kind, 'image')

// ---- 4. MCP 绘图落盘标记 ----
const mcpImg = collectMessageArtifacts([
  step('mcp__pixeldraw__draw', {}, 'done\n[Image saved: C:\\temp\\preview.png]\n'),
])
check('MCP 图片抓到 1 条', mcpImg.length, 1)
check('MCP 图片 op=image', mcpImg[0]?.op, 'image')

// ---- 5. 读类工具的结果一律不算产物 ----
const readOnly = collectMessageArtifacts([
  step('read_file', { file_path: 'C:\\work\\已有.txt' }, 'File content: ...'),
  step('list_files', { path: 'C:\\work' }, JSON.stringify({ files: [{ path: 'C:\\work\\x.md' }] })),
  step('search_files', { query: 'foo', path: 'C:\\work' }, JSON.stringify({ results: [{ file: 'C:\\work\\y.md' }] })),
])
check('读类工具不产生产物', readOnly.length, 0)

// ---- 6. 没落盘的步骤不算 ----
const pending = collectMessageArtifacts([
  step('create_file', { file_path: 'C:\\work\\b.md' }, '', 'awaiting_approval'),
  step('create_file', { file_path: 'C:\\work\\c.md' }, '', 'rejected'),
  step('create_file', { file_path: 'C:\\work\\d.md' }, '', 'running'),
])
check('等审批/被拒/调用中都不算', pending.length, 0)

// ---- 7. 相对路径 / 无扩展名的目录 ----
// 隐藏配置(.env)算真产物,保留;但相对路径和目录必须挡掉
const junk = collectMessageArtifacts([
  step('create_file', { file_path: 'reports/a.md' }, 'File created: reports/a.md'),
  step('create_file', { file_path: 'C:\\work' }, 'File created: C:\\work'),
  step('create_file', { file_path: 'C:\\work\\.env' }, 'File created: C:\\work\\.env'),
])
check('相对路径与目录被挡掉(保留 .env)', junk.map(a => a.name), ['.env'])

// ---- 8. 失败结果里的路径不算(Error: ...) ----
const err = collectMessageArtifacts([
  step('create_file', { file_path: 'C:\\work\\e.md' }, 'Error creating file C:\\work\\e.md: Permission denied', 'done'),
])
// 入参本身是合法绝对路径 -> 仍会列出来(文件可能已建成但返回报错),只要求不重复
check('报错步骤不重复计数', err.length, 1)

// ---- 9. 上限 24 条 ----
const many = collectMessageArtifacts(
  Array.from({ length: 40 }, (_, i) =>
    step('create_file', { file_path: `C:\\work\\f${i}.md` }, `File created: C:\\work\\f${i}.md`),
  ),
)
check('超过 24 条被截断', many.length, 24)

// ---- 10. kind / preview 判定 ----
check('kind: .webp', artifactKindOf('a.webp'), 'image')
check('kind: .docx', artifactKindOf('a.docx'), 'doc')
check('kind: .xlsx', artifactKindOf('a.xlsx'), 'sheet')
check('kind: .pptx', artifactKindOf('a.pptx'), 'slide')
check('kind: .pdf', artifactKindOf('a.pdf'), 'pdf')
check('kind: .md', artifactKindOf('a.md'), 'text')
check('kind: .py', artifactKindOf('a.py'), 'code')
check('kind: .zip', artifactKindOf('a.zip'), 'archive')
check('kind: 未知扩展名', artifactKindOf('a.bin'), 'other')
check('可预览: 图片', canPreviewArtifact({ kind: 'image' } as never), true)
check('可预览: 文本', canPreviewArtifact({ kind: 'text' } as never), true)
check('不可预览: docx', canPreviewArtifact({ kind: 'doc' } as never), false)

// ---- 11. 空 / 脏数据不炸 ----
check('空 steps', collectMessageArtifacts(undefined).length, 0)
check('非数组 steps', collectMessageArtifacts({ a: 1 }).length, 0)
check('缺字段 steps', collectMessageArtifacts([{ name: 'create_file' }]).length, 0)
check('入参不是 JSON', collectMessageArtifacts([{ name: 'create_file', arguments: 'not json', status: 'done' }]).length, 0)

if (failed > 0) {
  console.error(`\n${failed} 项失败`)
  process.exit(1)
}
console.log('\n全部通过')
