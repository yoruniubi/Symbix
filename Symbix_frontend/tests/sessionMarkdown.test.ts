/**
 * Markdown 存档解析的回归测试。
 *
 * 运行:`node --experimental-strip-types tests/sessionMarkdown.test.ts`
 *
 * 这份解析是「本地缓存丢了之后唯一能把内容捞回来的路」,格式对不上就等于没恢复。
 */

import { parseSessionMarkdown } from '../src/utils/sessionMarkdown.ts'

let failed = 0
function check(name: string, actual: unknown, expected: unknown) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  console.log(ok ? `  PASS ${name}` : `  FAIL ${name}: got ${JSON.stringify(actual)} want ${JSON.stringify(expected)}`)
  if (!ok) failed++
}

// 后端 save_markdown 的真实产物
const md = `# 帮我改一下登录页

### **User**:
把登录页背景换成深色

---

### **Assistant**:
好的，已经改了 \`src/pages/Login.vue\`：

- 背景改成 var(--bg-app)
- 文字颜色同步

---

`
check('两条消息', parseSessionMarkdown(md).map(m => m.role), ['user', 'assistant'])
check('user 正文', parseSessionMarkdown(md)[0].content, '把登录页背景换成深色')
check('assistant 正文', parseSessionMarkdown(md)[1].content,
  '好的，已经改了 `src/pages/Login.vue`：\n\n- 背景改成 var(--bg-app)\n- 文字颜色同步')

// 只有标题没正文
check('空存档', parseSessionMarkdown('# 标题\n'), [])

// 空串 / null
check('空字符串', parseSessionMarkdown(''), [])

// 正文里含 --- 的水平线不能被当成段尾吃掉
const withRule = `### **User**:
上面

---

下面

---`
check('正文内水平线保留', parseSessionMarkdown(withRule)[0].content, '上面\n\n---\n\n下面')

// 大小写不敏感 + 连续同角色
const lower = `### **user**:
a

### **assistant**:
b

### **assistant**:
c`
check('小写段头', parseSessionMarkdown(lower).map(m => m.role), ['user', 'assistant', 'assistant'])
check('连续同角色不合并', parseSessionMarkdown(lower).map(m => m.content), ['a', 'b', 'c'])

console.log(failed === 0 ? '\n全部通过' : `\n${failed} 项失败`)
process.exit(failed === 0 ? 0 : 1)
