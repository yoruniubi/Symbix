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

// ---- 12. doc_to_markdown_file 返回 md_path（以前不在 RESULT_PATH_KEYS 里）----
const mdConv = collectMessageArtifacts([
  {
    name: 'doc_to_markdown_file',
    arguments: JSON.stringify({ file_path: 'C:\\a\\x.docx', out_md_path: 'C:\\a\\x.md' }),
    result: JSON.stringify({ success: true, md_path: 'C:\\a\\x.md' }),
    status: 'done',
  },
])
check('doc_to_markdown_file 产出被识别', mdConv.length, 1)
check('doc_to_markdown_file 路径对', mdConv[0]?.path, 'C:\\a\\x.md')

// ---- 13. open_terminal 里渲染出来的文件要能被列出来 ----
// 以前完全不扫终端输出:渲染 40 个 clip 生成了 mp4,卡片上一条都没有
const term = collectMessageArtifacts([
  {
    name: 'open_terminal',
    arguments: JSON.stringify({ command: 'ffmpeg -i a.mp4 D:\\out\\clip01.mp4' }),
    result: 'rendering...\nDone: D:\\out\\clip01.mp4 (12.3 MB)\nDone: D:\\out\\clip02.mp4 (11.8 MB)',
    status: 'done',
  },
])
check('终端产物: 找到 2 个 mp4', term.length, 2)
check('终端产物: clip01', term.some((a) => a.path === 'D:\\out\\clip01.mp4'), true)
check('终端产物: clip02', term.some((a) => a.path === 'D:\\out\\clip02.mp4'), true)
check('终端产物: kind=image? 不,mp4 归 other', term[0]?.kind, 'other')

// 依赖/缓存目录里的文件不能当产物
const termNoise = collectMessageArtifacts([
  {
    name: 'open_terminal',
    arguments: '{}',
    result: 'wrote C:\\p\\node_modules\\pkg\\index.js\nwrote C:\\p\\.venv\\lib\\x.py\nwrote C:\\p\\node_modules\\a\\logo.png',
    status: 'done',
  },
])
check('终端产物: 过滤 node_modules/.venv', termNoise.length, 0)

// 源码/配置类扩展名不进终端产物(避免把 package.json 当产物)
const termSrc = collectMessageArtifacts([
  {
    name: 'open_terminal',
    arguments: '{}',
    result: 'edited C:\\proj\\src\\App.vue\nread C:\\proj\\package.json\nwrote C:\\proj\\out\\report.pdf',
    status: 'done',
  },
])
check('终端产物: 只认 report.pdf', termSrc.length, 1)
check('终端产物: 是 pdf', termSrc[0]?.path, 'C:\\proj\\out\\report.pdf')

// 去重:同一路径在 stdout 出现两次只占一格
const termDup = collectMessageArtifacts([
  {
    name: 'open_terminal',
    arguments: '{}',
    result: 'writing E:\\o\\a.mp4 ...\nwrote E:\\o\\a.mp4 (5MB)\nverifed E:\\o\\a.mp4',
    status: 'done',
  },
])
check('终端产物: 重复路径去重', termDup.length, 1)

// 未完成的终端步骤不算
const termNotDone = collectMessageArtifacts([
  { name: 'open_terminal', arguments: '{}', result: 'wrote E:\\o\\b.mp4', status: 'running' },
])
check('终端产物: running 不算', termNotDone.length, 0)

// ══════════════ 磁盘快照 diff（fileChanges）优先 ══════════════
// 后端在一轮开始/结束时各拍一次 uploads+工作区 的快照,比对出差集下发。
// 这路与「哪个工具干的」解耦,所以下面的例子故意用「终端命令」和「MCP」
// 这些 step 推断覆盖不到/会误判的场景。

// 1) 终端 cp 静默写盘:step 推断漏,但磁盘 diff 看得到
const cpSilent = collectMessageArtifacts(
  [{ name: 'open_terminal', arguments: '{}', result: '', status: 'done' }],
  [{ path: 'E:\\out\\b.mp4', op: 'create', size: 5242880 }],
)
check('diff: 终端静默写盘能识别', cpSilent.length, 1)
check('diff: 文件名', cpSilent[0].name, 'b.mp4')
check('diff: 目录', cpSilent[0].dir, 'E:\\out')
check('diff: op', cpSilent[0].op, 'create')
check('diff: size', cpSilent[0].size, 5242880)

// 2) ffmpeg -i input.mp4 out.mp4:step 推断会把输入当产物,diff 只有真的 output
const ffmpegInput = collectMessageArtifacts(
  [{ name: 'open_terminal', arguments: '{}', result: 'ffmpeg -i E:\\in\\input.mp4 E:\\out\\output.mp4', status: 'done' }],
  [{ path: 'E:\\out\\output.mp4', op: 'create', size: 1024 }],
)
check('diff: ffmpeg 输入文件不被当产物', ffmpegInput.length, 1)
check('diff: 只剩 output', ffmpegInput[0].name, 'output.mp4')

// 3) 修改/删除 也要报（以前完全看不到）
const editDel = collectMessageArtifacts(
  [],
  [
    { path: 'E:\\w\\a.md', op: 'edit', size: 200 },
    { path: 'E:\\w\\b.txt', op: 'delete', size: 50 },
  ],
)
check('diff: edit + delete 都列', editDel.length, 2)
check('diff: edit op', editDel.find((a) => a.name === 'a.md')?.op, 'edit')
check('diff: delete op', editDel.find((a) => a.name === 'b.txt')?.op, 'delete')
check('diff: 删除项不可预览', canPreviewArtifact(editDel.find((a) => a.name === 'b.txt')!), false)

// 4) diff 里没有的路径不能被 step 推断拉回来
const notInDiff = collectMessageArtifacts(
  [step('create_file', { file_path: 'E:\\ghost\\x.md' }, 'File created: E:\\ghost\\x.md')],
  [{ path: 'E:\\real\\y.md', op: 'create', size: 10 }],
)
check('diff: 只信 diff,不拉回 ghosts', notInDiff.length, 1)
check('diff: 保留真产物', notInDiff[0].name, 'y.md')

// 5) 下载/绘图提示能美化 op（diff 只说 create，tools 说 download）
//    注意 result 必须是**合法 JSON**：JSON 里 `\d` 不是合法转义，
//    所以路径分隔符要写成 `\\`。
const dlDiff = collectMessageArtifacts(
  [step('download_file', { url: 'https://x/a.zip' }, '{"status":"ok","path":"E:\\\\dl\\\\a.zip"}')],
  [{ path: 'E:\\dl\\a.zip', op: 'create', size: 999 }],
)
check('diff: download 提示被采纳', dlDiff[0].op, 'download')

// 6) 脏数据容错
check('diff: 非数组容错', collectMessageArtifacts([], 'nope').length, 0)
check('diff: 缺 path 丢弃', collectMessageArtifacts([], [{ op: 'create' }]).length, 0)
check('diff: 未知 op 丢弃', collectMessageArtifacts([], [{ path: 'E:\\a.md', op: 'rename' }]).length, 0)
// 相对路径/无扩展名仍然不能进清单
check('diff: 相对路径丢弃', collectMessageArtifacts([], [{ path: 'a.md', op: 'create' }]).length, 0)
check('diff: 无扩展名丢弃', collectMessageArtifacts([], [{ path: 'E:\\a', op: 'create' }]).length, 0)
// 空数组 → 退回 steps 推断（历史会话走这条）
check(
  'diff: 空数组退回 steps 推断',
  collectMessageArtifacts([step('create_file', { file_path: 'E:\\k\\z.md' }, 'File created: E:\\k\\z.md')], []).length,
  1,
)

if (failed > 0) {
  console.error(`\n${failed} 项失败`)
  process.exit(1)
}
console.log('\n全部通过')
