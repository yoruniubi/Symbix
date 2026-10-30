/**
 * 聊天页「预览卡」取路径的回归测试。
 *
 * 运行:`node --experimental-strip-types tests/petRigPreview.test.ts`
 * (Node 22.18+/24 自带类型擦除,不用起 vite/tsc)
 *
 * 覆盖两次真实误报:
 * 1. 只是**列目录 / 读已有皮肤**(MCP filesystem 还回 `file://` URI)→ 不该弹预览;
 * 2. 工具输出里出现文档中的格式说明 `[Image saved: <绝对路径>]` → 不该按占位符去请求图片。
 */
import { pickPreviewRigPath, pickPreviewImagePath, normalizeFsPath } from '../src/utils/petRig.ts'

let failed = 0

function eq(label: string, got: string, want: string): void {
  const ok = got === want
  if (!ok) failed++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`)
  if (!ok) console.log(`      got=${JSON.stringify(got)}  want=${JSON.stringify(want)}`)
}

// ── pet-forge 预览:只有真的在造桌宠才显示 ──
eq(
  '列目录(MCP filesystem 回 file:// URI)不预览',
  pickPreviewRigPath([{
    name: 'filesystem__list_directory',
    status: 'done',
    arguments: { path: 'F:/Symbix/Symbix_frontend/public/pixiv_pet' },
    result: '[{"uri":"file:///F:/Symbix/Symbix_frontend/public/pixiv_pet/%E5%85%94%E5%AD%90/base.svg"}]',
  }]),
  '',
)
eq(
  '读已有皮肤的 base.svg 不预览',
  pickPreviewRigPath([{
    name: 'read_file',
    status: 'done',
    arguments: { path: 'F:/Symbix/Symbix_frontend/public/pixiv_pet/可爱的小兔子/base.svg' },
    result: '<svg/>',
  }]),
  '',
)
eq(
  'create_file 写 base.svg 要预览',
  pickPreviewRigPath([{
    name: 'create_file',
    status: 'done',
    arguments: { path: 'F:/tmp/rig/base.svg', content: '<svg/>' },
    result: 'written',
  }]),
  'F:/tmp/rig/base.svg',
)
eq(
  'build_theme.py 的 out_dir(file:// + 百分号转义)归一化后预览',
  pickPreviewRigPath([{
    name: 'run_command',
    status: 'done',
    arguments: { command: 'python .../pet-forge/scripts/build_theme.py --rig F:/tmp/rig/base.svg' },
    result: 'OK: {"out_dir":"file:///F:/Symbix/Symbix_frontend/public/pixiv_pet/%E5%B0%8F%E7%8C%AB"}',
  }]),
  'F:/Symbix/Symbix_frontend/public/pixiv_pet/小猫/base.svg',
)
eq(
  'build_theme.py 的 Windows 路径预览',
  pickPreviewRigPath([{
    name: 'run_command',
    status: 'done',
    arguments: { command: 'python F:/x/pet-forge/scripts/build_theme.py' },
    result: 'OK: {"out_dir":"F:\\\\Symbix\\\\public\\\\pixiv_pet\\\\小猫"}',
  }]),
  'F:\\Symbix\\public\\pixiv_pet\\小猫\\base.svg',
)

// ── MCP 图片预览:只认真的绝对图片路径 ──
eq(
  '文档里的占位符 [Image saved: <绝对路径>] 不预览',
  pickPreviewImagePath([{
    name: 'read_file',
    status: 'done',
    result: '把图片存成 `[Image saved: <绝对路径>]` 这种标记给前端',
  }]),
  '',
)
eq(
  '真实落盘路径要预览',
  pickPreviewImagePath([{
    name: 'pixeldraw__draw',
    status: 'done',
    result: 'ok\n[Image saved: F:/tmp/pix/out.png]',
  }]),
  'F:/tmp/pix/out.png',
)
eq(
  'file:// URI + 百分号转义归一化后预览',
  pickPreviewImagePath([{
    name: 'pixeldraw__draw',
    status: 'done',
    result: '[Image saved: file:///F:/tmp/%E7%8C%AB/p.png]',
  }]),
  'F:/tmp/猫/p.png',
)
eq(
  '非图片扩展名不预览',
  pickPreviewImagePath([{ name: 'pixeldraw__draw', status: 'done', result: '[Image saved: F:/tmp/a.txt]' }]),
  '',
)
eq(
  '相对路径不预览',
  pickPreviewImagePath([{ name: 'pixeldraw__draw', status: 'done', result: '[Image saved: out/p.png]' }]),
  '',
)

// ── 路径归一化 ──
eq('file:///C:/a%20b/c.svg', normalizeFsPath('file:///C:/a%20b/c.svg'), 'C:/a b/c.svg')
eq('POSIX 绝对路径保持原样', normalizeFsPath('/home/u/a.svg'), '/home/u/a.svg')

console.log(failed === 0 ? '\nALL PASS' : `\n${failed} FAILED`)
if (failed) process.exitCode = 1
