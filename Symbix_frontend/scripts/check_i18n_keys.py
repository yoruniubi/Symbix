#!/usr/bin/env python3
"""扫描代码里所有 t('ns.key') / $t('ns.key') 调用，与 zh-CN.ts 字典实际 key set 做 diff，
定位"代码引用了但字典没有"的缺失 key。仅静态字符串字面量；含 ${} 插值的动态 key 会单独列出。"""
import re, os
SRC_DIR = 'src'

# 1) 收集代码里所有 t('...') / $t('...') 调用的 key 字面量
key_pattern = re.compile(r"""\$(?:t|tc)\(\s*['"]([\w.\-]+)['"]|\b(?:t|tc)\(\s*['"]([\w.\-]+)['"]""")
unresolved = []  # 动态拼接，无法静态解析
used = {}        # key -> [file:line]

for root, _, files in os.walk(SRC_DIR):
    if 'node_modules' in root:
        continue
    for fn in files:
        if not (fn.endswith('.vue') or fn.endswith('.ts')):
            continue
        if fn in ('zh-CN.ts', 'en.ts'):
            continue
        path = os.path.join(root, fn)
        for i, line in enumerate(open(path, encoding='utf-8').read().splitlines(), 1):
            # 跳过 i18n 字典定义行（key: '...'）
            if re.match(r"\s*[a-zA-Z_]+:\s*['\"]", line):
                continue
            for m in key_pattern.finditer(line):
                key = m.group(1) or m.group(2)
                if not key:
                    continue
                # 动态拼接：含 ${} 表示插值，无法静态解析
                seg_end = min(len(line), m.end() + 40)
                if '${' in line[m.start():seg_end]:
                    unresolved.append((os.path.relpath(path), i, line.strip()[:140]))
                    continue
                # 抓调用括号之后下个非空白字符，若是 + 表示动态拼接
                tail = line[m.end():].lstrip()
                if tail.startswith('+'):
                    unresolved.append((os.path.relpath(path), i, line.strip()[:140]))
                    continue
                used.setdefault(key, []).append(f"{os.path.relpath(path)}:{i}")

# 2) 解析 zh-CN.ts 抓所有完全限定 key (namespace.key)
ns_keys = set()
text = open(os.path.join(SRC_DIR, 'i18n/locales/zh-CN.ts'), encoding='utf-8').read()
for ns_match in re.finditer(r"^\s*([a-zA-Z_][\w]*):\s*\{(.*?)\n  \},", text, re.DOTALL | re.MULTILINE):
    ns = ns_match.group(1)
    for k in re.findall(r"^\s*([a-zA-Z_][\w]*):", ns_match.group(2), re.MULTILINE):
        ns_keys.add(f"{ns}.{k}")

# 3) diff
missing = sorted(k for k in used if k not in ns_keys)
print(f"used keys: {len(used)}  dict keys: {len(ns_keys)}")
if missing:
    print("\n====== MISSING KEYS (代码用 t()/\$t() 引用但字典无此 key) ======")
    for k in missing:
        print(f"  {k}")
        for loc in used[k][:5]:
            print(f"      -> {loc}")
else:
    print("ALL OK - no missing keys")

print(f"\n(unresolved 动态拼接 {len(unresolved)} 处，需人工肉眼确认)：")
for p, i, l in unresolved[:30]:
    print(f"  {p}:{i}  {l}")
