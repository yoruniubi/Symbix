/**
 * 对 .vue 文件做真正的类型检查。
 *
 * 项目里没有装 vue-tsc，而 `tsc --noEmit` 即使 tsconfig 的 include 里写了
 * src 下的 vue 通配符，也**完全不解析 .vue**（tsc 只认 .ts/.tsx/.d.ts）。
 * 结果就是所有 .vue 里的类型错误从来没被检查过 ——
 * 例如 d84408b 给消息加 uid 时漏了类型定义，tsc 报 OK，编辑器却一直飘红。
 *
 * 做法：用 @vue/compiler-sfc 把 <script setup> 抽成 .ts（生成到 src 内部，
 * 这样相对 import 和 @/ 别名都还能解析），再让项目自己的 tsc 去检查。
 *
 * 注意：这是近似检查 —— 模板里的类型（v-for 变量、props 绑定）不在覆盖范围，
 *      只覆盖 <script> 里的 TS 错误。要全量覆盖仍建议装 vue-tsc。
 *
 * 运行：node scripts/check-vue-types.mjs
 */
import { createRequire } from 'node:module'
import { readdirSync, statSync, readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs'
import { join, resolve, dirname, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const require = createRequire(import.meta.url)
const { parse, compileScript } = require('@vue/compiler-sfc')

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const srcDir = join(root, 'src')
// 生成在 src 内部：相对 import 与 @/ 别名都能按原样解析
const genDir = join(srcDir, '__vue_typecheck__')
const tmpConfig = join(root, '.tmp-vue-types.tsconfig.json')

/** 递归找出所有 .vue（跳过生成目录自身） */
function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (name === '__vue_typecheck__') continue
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) walk(p, out)
    else if (name.endsWith('.vue')) out.push(p)
  }
  return out
}

const vueFiles = walk(srcDir)
console.log(`找到 ${vueFiles.length} 个 .vue 文件`)

rmSync(genDir, { recursive: true, force: true })
mkdirSync(genDir, { recursive: true })

const genFiles = []
for (const file of vueFiles) {
  const source = readFileSync(file, 'utf8')
  const { descriptor, errors } = parse(source, { filename: file })
  if (errors.length) {
    console.log(`  解析失败 ${relative(root, file)}: ${errors[0].message}`)
    continue
  }
  if (!descriptor.script && !descriptor.scriptSetup) continue
  let code
  try {
    code = compileScript(descriptor, { id: 'x' }).content
  } catch (e) {
    console.log(`  抽取失败 ${relative(root, file)}: ${e.message}`)
    continue
  }
  const tag = relative(srcDir, file).replace(/[\\/]/g, '__').replace(/\.vue$/, '')
  const outPath = join(genDir, `${tag}.generated.ts`)
  writeFileSync(outPath, code, 'utf8')
  genFiles.push({ outPath, tag, rel: relative(root, file) })
}
console.log(`抽取了 ${genFiles.length} 个 script 块`)

if (genFiles.length === 0) {
  rmSync(genDir, { recursive: true, force: true })
  console.log('没有可检查的 script')
  process.exit(0)
}

// paths 不能走命令行（TS6064），必须写进临时 tsconfig
writeFileSync(
  tmpConfig,
  JSON.stringify(
    {
      compilerOptions: {
        noEmit: true,
        strict: true,
        skipLibCheck: true,
        target: 'ESNext',
        module: 'ESNext',
        moduleResolution: 'bundler',
        jsx: 'preserve',
        esModuleInterop: true,
        resolveJsonModule: true,
        isolatedModules: true,
        lib: ['ESNext', 'DOM'],
        types: ['node', 'vite/client'],
        // TS 7 移除了 baseUrl，paths 现在直接相对 tsconfig 所在目录
        paths: { '@/*': ['./src/*'] },
      },
      include: ['src/__vue_typecheck__/**/*.ts', 'src/vite-env.d.ts'],
    },
    null,
    2,
  ),
  'utf8',
)

const tscBin = join(root, 'node_modules/typescript/bin/tsc')

// 不管检查结果如何，都别把生成物留在 src 里（否则会被误提交）
function cleanup() {
  rmSync(genDir, { recursive: true, force: true })
  rmSync(tmpConfig, { force: true })
}

let failed = false
let out = ''
try {
  const res = spawnSync(process.execPath, [tscBin, '-p', tmpConfig], {
    cwd: root,
    encoding: 'utf8',
  })

  out = `${res.stdout || ''}${res.stderr || ''}`.trim()
  // 把生成文件名映射回 .vue，方便定位
  for (const g of genFiles) {
    out = out.split(g.outPath).join(g.rel).split(g.outPath.replace(/\\/g, '/')).join(g.rel)
  }
  failed = res.status !== 0
} finally {
  // 先清再报，避免异常/非零退出时把生成目录留在 src 里
  cleanup()
}

if (failed) {
  console.log('\n.vue 的 script 存在类型错误：')
  console.log(out)
  process.exit(1)
}
console.log('\n.vue 的 script 类型检查通过')
