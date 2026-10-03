"""skill 目录访问辅助:文件清单 / 批量读取 / 路径安全。

`skill__<name>` 工具用这些函数,让模型一次拿到「技能里有什么」并按需批量读取,
不必靠猜路径逐个 read_file(猜错还会白烧一轮往返)。

设计要点:
- 路径安全:realpath 解析后必须仍在 skill 根目录内(挡 `..`、绝对路径、符号链接逃逸)
- 截断按行做,绝不切碎 UTF-8 多字节字符;截断处给出 `offset` 续读提示
- 找不到路径时给最相近的候选,让模型一次改对,而不是继续猜
"""
from __future__ import annotations

import difflib
import json
import os
import re

# 扫描时跳过的目录(技能里常有 node_modules / 构建产物,与指导内容无关)
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build", ".venv", "venv",
    "vendor", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".idea", ".vscode",
    "site-packages", ".next", "coverage",
}
TEXT_EXTS = {
    ".md", ".markdown", ".txt", ".rst", ".py", ".json", ".jsonc", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".ts", ".tsx", ".js", ".jsx", ".vue", ".sh", ".bash",
    ".ps1", ".bat", ".cmd", ".html", ".css", ".scss", ".svg", ".xml", ".csv",
    ".sql", ".java", ".go", ".rs", ".c", ".h", ".cpp", ".env", ".example",
}
# 单文件/单批返回上限(字节):够读一整篇 reference,又不至于把上下文拉爆
READ_MAX_BYTES_DEFAULT = 24000
READ_MAX_BYTES_CAP = 200000
BATCH_TOTAL_BYTES = 96000
SCAN_MAX_FILES = 600
INDEX_MAX_LINES = 60
# 检索(search):多关键词任一命中即可
SEARCH_MAX_HITS = 30
SEARCH_MAX_BYTES = 14000
SEARCH_CONTEXT_DEFAULT = 1
SEARCH_MAX_FILE_BYTES = 512 * 1024
SEARCH_MAX_FILES = 400
SEARCH_HITS_PER_FILE = 8
# 分节(section)
HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")
# 路径可带定位: `a.md#标题` 只读该节; `a.md:100-180` 只读行范围
PATH_SPEC_RE = re.compile(
    r"^(?P<rel>[^#:]+?)\s*(?:#(?P<section>[^:]+?))?\s*(?::(?P<rng>\d+\s*(?:-\s*\d+)?))?$"
)
# SKILL.md 里出现的 "xxx.md / scripts/foo.py" 这类路径,清单里优先列出并标注
_MENTION_RE = re.compile(r"[\w./\\-]+\.(?:md|markdown|py|json|ya?ml|toml|txt|sh|ps1|svg|ts|js|vue)")


def _safe_int(value, default: int = 0) -> int:
    """容错取整(模型可能把数字传成字符串,或传成 None/空)。"""
    if value is None or value == "":
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def normalize_paths(value) -> list[str]:
    """容错归一化模型传来的 paths。

    弱模型常见的几种写法都要能接住:
      "a.md"                    → ["a.md"]
      "a.md, b.md"              → ["a.md", "b.md"]
      '["a.md","b.md"]'         → ["a.md", "b.md"]  (JSON 字符串)
      "a.md\nb.md"              → ["a.md", "b.md"]
      ["a.md", 123, None]       → ["a.md"]  (非字符串项丢弃)
      {"0": "a.md"}             → ["a.md"]
      {"path": "a.md"}          → ["a.md"]  (单键对象)
    """
    if value is None:
        return []
    if isinstance(value, dict):
        # 单键对象视为 {参数名: 值};多键对象按值取
        vals = list(value.values()) if len(value) != 1 else [next(iter(value.values()))]
        return [p for p in (_as_str(v) for v in vals) if p]
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            out.extend(normalize_paths(item))
        return out
    if not isinstance(value, str):
        return []
    text = value.strip()
    if not text:
        return []
    if text[0] in "[{":
        try:
            return normalize_paths(json.loads(text))
        except Exception:
            pass
    parts = re.split(r"[\n,;]+", text)
    return [p.strip().strip("\"'") for p in parts if p.strip().strip("\"'")]


def _as_str(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def _is_under(root_real: str, target: str) -> bool:
    """target(已 realpath)是否在 root_real 内。跨盘符时 commonpath 会抛错,视为越界。"""
    try:
        return os.path.commonpath([root_real, target]) == root_real
    except ValueError:
        return False


def resolve_in_root(root: str, rel: str) -> tuple[str | None, str | None]:
    """把相对路径解析到 skill 根目录内。

    返回 (绝对路径, 错误说明);越界/非法时路径为 None。
    """
    if not rel:
        return None, "路径为空"
    raw = rel.strip().strip("\"'")
    if not raw:
        return None, "路径为空"
    if os.path.isabs(raw) or re.match(r"^[A-Za-z]:[\\/]", raw):
        return None, "请传相对 skill 根目录的路径(不要用绝对路径)"
    root_real = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root_real, raw))
    if not _is_under(root_real, target):
        return None, "路径越出 skill 目录,已拒绝"
    return target, None


def scan_files(root: str) -> list[dict]:
    """扫描 skill 目录下的文本文件(跳过 SKIP_DIRS / 隐藏目录),返回元信息列表。"""
    found: list[dict] = []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.startswith(".") and fn not in (".env", ".example"):
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext not in TEXT_EXTS:
                continue
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            rel = os.path.relpath(full, root).replace("\\", "/")
            found.append({"rel": rel, "size": size, "abs": full})
            if len(found) >= SCAN_MAX_FILES:
                return found
    return found


_NOISE_PREFIXES = (
    "from ", "import ", "def ", "class ", "async def ", "return ", "if ", "elif ", "else",
    "for ", "while ", "try", "except", "with ", "#!", "#!/", "#", "//", "/*", "*",
    "use ", "export ", "const ", "let ", "var ", "package ", "public ", "private ",
    "function ", "type ", "interface ", "<?xml", "<!doctype", "<svg", "<g ", "<", "{", "[",
    "=", "-", "──", "│", "┌", "└", "└", '"', "'", "---",
)
_BAD_FIRST_CHARS = set("{}[]<>|─═=+*/\\\"'!,;)")


def _is_prose(s: str) -> bool:
    """行是否像「一句人话」(适合当清单摘要),滤掉代码/JSON/SVG/分隔线噪音。"""
    if len(s) < 4 or len(s) > 80:
        return False
    if s[0] in _BAD_FIRST_CHARS:
        return False
    low = s.lower()
    if any(low.startswith(p) for p in _NOISE_PREFIXES):
        return False
    letters = sum(1 for c in s if c.isalpha())
    if letters < 2:
        return False
    if s.count("(") + s.count(")") + s.count("=") > 3:
        return False
    return True


def _summarize(path: str) -> str:
    """取一行摘要:Markdown 标题优先,Python 取模块 docstring,其余取首句人话。"""
    ext = os.path.splitext(path)[1].lower()
    # 标记/结构类文件(HTML/CSS/JSON/XML/SVG...)的首行不是人话,不取摘要
    if ext in (".html", ".htm", ".css", ".scss", ".svg", ".xml", ".json", ".jsonc",
               ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv"):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.strip() for _, ln in zip(range(60), f)]
    except OSError:
        return ""

    if ext in (".md", ".markdown", ".rst"):
        for s in lines:
            if s.startswith("#"):
                return s.lstrip("# ").strip()[:60]
    else:
        # Python: 优先取模块 docstring 的首句
        for s in lines:
            if not s or s.startswith(("#!", "# -", "#-")):
                continue
            if s.startswith(('"""', "'''")):
                inner = s.strip('"\'').strip()
                if inner:
                    return inner[:60]
                continue
            break

    for s in lines:
        if _is_prose(s):
            return s[:60]
    return ""


def _human(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / 1024 / 1024:.1f}MB"


def mentioned_paths(skill_md: str) -> set[str]:
    """从 SKILL.md 里提取它明确提到过的文件路径,清单里优先展示。"""
    out: set[str] = set()
    for m in _MENTION_RE.findall(skill_md or ""):
        token = m.replace("\\", "/").lstrip("./")
        # 去掉行首的目录前缀噪音,如 "python scripts/x.py" 里的 "python scripts/x.py"
        if " " in token:
            token = token.split()[-1]
        out.add(token)
    return out


def parse_path_spec(rel: str) -> tuple[str, str | None, tuple[int, int | None] | None]:
    """拆解路径上的定位后缀。

    "references/rig-spec.md#Rig Snail" → ("references/rig-spec.md", "Rig Snail", None)
    "references/rig-spec.md:12-48"  → ("references/rig-spec.md", None, (12, 48))
    "references/rig-spec.md:120"    → ("references/rig-spec.md", None, (120, None))
    """
    raw = (rel or "").strip().strip("\"'")
    m = PATH_SPEC_RE.match(raw)
    if not m:
        return raw, None, None
    rel_only = m.group("rel").strip()
    section = (m.group("section") or "").strip() or None
    rng = None
    if m.group("rng"):
        parts = [p.strip() for p in m.group("rng").split("-")]
        try:
            start = int(parts[0])
            end = int(parts[1]) if len(parts) > 1 and parts[1] else None
            rng = (start, end)
        except ValueError:
            rng = None
    return rel_only or raw, section, rng


def _parse_heading(line: str) -> tuple[int, str] | None:
    m = HEADING_RE.match(line.rstrip())
    if not m:
        return None
    return len(m.group(1)), m.group(2).strip()


def heading_list(lines: list[str]) -> list[tuple[int, int, str]]:
    """所有真标题 [(行下标, 级别, 标题)],跳进代码块内的 `#` 注释(如 shell 注释)。"""
    out: list[tuple[int, int, str]] = []
    fence: str | None = None
    for i, line in enumerate(lines):
        s = line.lstrip()
        if fence:
            if s.startswith(fence):
                fence = None
            continue
        if s.startswith("```") or s.startswith("~~~"):
            fence = s[:3]
            continue
        head = _parse_heading(line)
        if head:
            out.append((i, head[0], head[1]))
    return out


def heading_contexts(lines: list[str]) -> list[str]:
    """逐行的「所属标题」(最多 3 级),同样跳进代码块。"""
    out: list[str] = []
    stack: list[tuple[int, str]] = []
    fence: str | None = None
    for line in lines:
        s = line.lstrip()
        if fence:
            if s.startswith(fence):
                fence = None
        elif s.startswith("```") or s.startswith("~~~"):
            fence = s[:3]
        else:
            head = _parse_heading(line)
            if head:
                stack = [x for x in stack if x[0] < head[0]]
                stack.append(head)
        out.append(" > ".join(t for _, t in stack[-3:]))
    return out


def find_section_range(lines: list[str], query: str) -> tuple[int, int] | None:
    """按标题(部分匹配,不区分大小写)定位一节,返回 [start, stop) 行下标。"""
    q = (query or "").strip().lower()
    if not q:
        return None
    heads = heading_list(lines)
    for pos, (i, level, title) in enumerate(heads):
        if q not in title.lower():
            continue
        stop = len(lines)
        for j, lv, _ in heads[pos + 1:]:
            if lv <= level:
                stop = j
                break
        return i, stop
    return None


def outline(lines: list[str], limit: int = 40) -> str:
    """列出全部标题(带行号),供模型挑一节再读。"""
    heads = heading_list(lines)[:limit]
    if not heads:
        return "(该文件没有 Markdown 标题)"
    return "\n".join(f" - {'#' * lv} {title} (第 {ln + 1} 行)" for ln, lv, title in heads)


def normalize_keywords(value) -> list[str]:
    """归一化检索词:字符串按空白/逗号/分号/竖线切分(多词 OR),数组展平。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for v in value:
            out.extend(normalize_keywords(v))
        return out
    if isinstance(value, dict):
        return normalize_keywords(list(value.values()))
    if not isinstance(value, str):
        return []
    parts = re.split(r"[\s,;|]+", value.strip())
    return [p.strip().strip("\"'") for p in parts if p.strip().strip("\"'")]


def search_files(root: str, keywords: list[str], context: int = SEARCH_CONTEXT_DEFAULT,
                 max_hits: int = SEARCH_MAX_HITS, max_bytes: int = SEARCH_MAX_BYTES,
                 only: list[str] | None = None) -> str:
    """在技能内检索关键词(多词任一命中),返回命中位置 + 所属标题 + 上下文。

    only 给定时只在这些文件/目录里找(限定范围)。
    """
    kws = [k for k in keywords if k]
    if not kws:
        return "[Skill search] 未提供有效的检索关键词。"
    ctx = max(0, min(_safe_int(context, SEARCH_CONTEXT_DEFAULT), 5))
    lows = [k.lower() for k in kws]

    targets: list[str] = []
    if only:
        for rel in only:
            rel_only, _, _ = parse_path_spec(rel)
            target, err = resolve_in_root(root, rel_only)
            if target is None:
                return _not_found_note(root, rel_only, err)
            if os.path.isdir(target):
                for dp, dns, fns in os.walk(target):
                    dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
                    for fn in fns:
                        if os.path.splitext(fn)[1].lower() in TEXT_EXTS:
                            targets.append(os.path.join(dp, fn))
            else:
                targets.append(target)
    else:
        targets = [f["abs"] for f in scan_files(root)][:SEARCH_MAX_FILES]

    header = f"[Skill search] {' | '.join(kws)} → "
    blocks: list[str] = []
    hit_total = 0
    per_kw = {k: 0 for k in kws}
    used = 0
    scanned = 0
    truncated = False

    for path in targets:
        try:
            if os.path.getsize(path) > SEARCH_MAX_FILE_BYTES:
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue
        scanned += 1
        rel = os.path.relpath(path, os.path.abspath(root)).replace("\\", "/")
        heads_at = heading_contexts(lines)
        hits: list[int] = []
        for i, line in enumerate(lines):
            low = line.lower()
            matched = [k for k, kl in zip(kws, lows) if kl in low]
            if matched:
                hits.append(i)
                for k in matched:
                    per_kw[k] += 1

        if not hits:
            continue
        if len(hits) > SEARCH_HITS_PER_FILE:
            truncated = True
            extra = len(hits) - SEARCH_HITS_PER_FILE
            hits = hits[:SEARCH_HITS_PER_FILE]
        else:
            extra = 0

        # 把命中行 ±context 合并成窗口
        windows: list[tuple[int, int, int]] = []
        for i in hits:
            s = max(0, i - ctx)
            e = min(len(lines) - 1, i + ctx)
            if windows and s <= windows[-1][1] + 1:
                ps, pe, ph = windows[-1]
                windows[-1] = (ps, max(pe, e), ph)
            else:
                windows.append((s, e, i))

        parts = []
        for s, e, first_hit in windows:
            title = heads_at[first_hit] if first_hit < len(heads_at) else ""
            parts.append(f"{rel}:{first_hit + 1}" + (f"  [{title}]" if title else ""))
            for i in range(s, e + 1):
                mark = ">" if i in hits else " "
                parts.append(f"{mark} {i + 1:>4}| {lines[i].rstrip()[:200]}")
        if extra:
            parts.append(f"  …该文件还有 {extra} 处命中未显示")
        block = "\n".join(parts)
        used += len(block.encode("utf-8"))
        blocks.append(block)
        hit_total += len(hits)
        if hit_total >= max_hits or used >= max_bytes:
            truncated = True
            break

    if not blocks:
        return (
            f"{header}未命中。\n可以:①换关键词(支持多个词,任一命中即算);"
            "②不带参数看技能文件清单;③用 paths=[\"具体文件\"] 直接读。"
        )

    stats = "、".join(f"{k}={v}" for k, v in per_kw.items() if v)
    out = f"{header}本页 {hit_total} 处命中(扫描 {scanned} 个文件;关键词命中次数 {stats})\n"
    out += "(行首 `>` = 命中行;`文件:行号 [所属标题]` 可直接用于 paths=[\"文件#标题\"] 或 offset 精读)\n"
    out += "\n\n".join(blocks)
    if truncated:
        out += "\n…[结果已截断:命中过多,请用更具体的关键词或 paths 限定范围]"
    return out


def build_index(root: str, skill_md: str = "") -> str:
    """生成文件清单(带大小与首行摘要);文件多时按目录折叠。"""
    files = scan_files(root)
    if not files:
        return "[Skill files] 该技能目录下没有可读的文本文件。"

    mentions = mentioned_paths(skill_md)
    for f in files:
        rel = f["rel"]
        base = os.path.basename(rel)
        f["mentioned"] = rel == "SKILL.md" or rel in mentions or base in mentions or any(
            m.endswith("/" + rel) or rel.endswith(m) for m in mentions
        )
    # 提到的排前面,再按路径稳定排序
    files.sort(key=lambda f: (not f["mentioned"], f["rel"]))

    total = sum(f["size"] for f in files)
    lines = [
        f"[Skill files] {len(files)} 个文本文件 / {_human(total)}"
        f"(已跳过 node_modules / .git / __pycache__ 等目录)"
    ]
    lines.append("读取:skill__<name>(paths=[\"路径\", ...]) 可一次读多个;单文件默认 ≤ 24KB,更大用 offset 续读。")
    lines.append("定位:skill__<name>(search=\"关键词\") 先检索,再用 section=\"标题\" 或 paths=[\"文件#标题\"] / [\"文件:100-180\"] 精读。")
    if any(f["mentioned"] for f in files):
        lines.append("* = SKILL.md 里提到过")

    if len(files) <= INDEX_MAX_LINES:
        for f in files:
            mark = "*" if f["mentioned"] else " "
            head = _summarize(f["abs"])
            lines.append(f"{mark} {f['rel']} — {_human(f['size'])}" + (f" — {head}" if head else ""))
        return "\n".join(lines)

    for f in files[:INDEX_MAX_LINES]:
        mark = "*" if f["mentioned"] else " "
        head = _summarize(f["abs"])
        lines.append(f"{mark} {f['rel']} — {_human(f['size'])}" + (f" — {head}" if head else ""))
    rest = files[INDEX_MAX_LINES:]
    by_dir: dict[str, int] = {}
    for f in rest:
        top = f["rel"].split("/")[0] if "/" in f["rel"] else "(根目录)"
        by_dir[top] = by_dir.get(top, 0) + 1
    summary = "、".join(f"{d}/({n})" for d, n in sorted(by_dir.items()))
    lines.append(f"… 其余 {len(rest)} 个文件未逐条列出,按目录: {summary}")
    lines.append("需要目录内明细时可传 paths=[\"该目录\"] 查看该目录下的文件列表。")
    return "\n".join(lines)


def read_path(root: str, rel: str, offset: int = 0, max_bytes: int = READ_MAX_BYTES_DEFAULT,
              section: str | None = None) -> str:
    """读取 skill 内单个文件(按行截断,可 offset 续读)。

    路径可带定位后缀:`a.md#标题` 只读该节、`a.md:100-180` 只读行范围;
    也可用单独参数 `section=`。offset 始终是**原文件绝对行号**(1 起)。
    """
    rel_only, spec_section, spec_range = parse_path_spec(rel)
    want_section = (section or "").strip() or spec_section
    limit = max(1, min(_safe_int(max_bytes, READ_MAX_BYTES_DEFAULT), READ_MAX_BYTES_CAP))
    target, err = resolve_in_root(root, rel_only)
    if target is None:
        return _not_found_note(root, rel_only, err)
    if os.path.isdir(target):
        entries = sorted(os.listdir(target))[:40]
        return f"=== {rel_only} (目录) ===\n" + "\n".join(entries)
    if not os.path.isfile(target):
        return _not_found_note(root, rel_only, "文件不存在")

    ext = os.path.splitext(target)[1].lower()
    size = os.path.getsize(target)
    if ext not in TEXT_EXTS:
        return f"=== {rel_only} ({_human(size)}) ===\n[二进制/非文本文件,未读取内容]"

    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except OSError as e:
        return f"=== {rel_only} ===\n[读取失败:{e}]"
    total = len(all_lines)

    # 定位窗口(绝对行下标,[btn, top))
    win_from, win_to = 0, total
    scope = ""
    if want_section:
        rng = find_section_range(all_lines, want_section)
        if rng is None:
            return (
                f"=== {rel_only} (共 {total} 行) ===\n"
                f"[未找到标题「{want_section}」;该文件可用标题如下:]\n"
                + outline(all_lines)
                + '\n提示:section 支持标题部分匹配,也可用 paths=["'
                + f'{rel_only}:12-48"] 读行范围。'
            )
        win_from, win_to = rng
        scope = f"节「{want_section}」"
    if spec_range:
        a, b = spec_range
        win_from = max(0, a - 1) if not want_section else max(win_from, a - 1)
        if b:
            win_to = min(win_to, b) if not want_section else min(win_to, b)
        scope = (scope + " " if scope else "") + f"行 {a}~{b if b else total}"

    start = max(win_from, _safe_int(offset, 0) - 1)
    if start >= total or start >= win_to:
        return (
            f"=== {rel_only} ({_human(size)}, 共 {total} 行) ===\n"
            f"[offset={offset} 超出可读范围({win_from + 1}~{win_to})]"
        )

    body: list[str] = []
    used = 0
    end = start
    for line in all_lines[start:win_to]:
        b = len(line.encode("utf-8"))
        if used + b > limit and body:
            break
        body.append(line)
        used += b
        end += 1

    head = f"=== {rel_only} ({_human(size)}, 共 {total} 行"
    if scope:
        head += f", {scope}"
    head += ") ==="
    text = head + "\n" + "".join(body)
    if end < win_to:
        text += (
            f"\n…[已截断:本次返回第 {start + 1}~{end} 行(可读至 {win_to}),共 {total} 行;"
            f"续读用 offset={end + 1}]"
        )
    return text


def _not_found_note(root: str, rel: str, reason: str | None) -> str:
    """找不到路径时,给出最相近的候选,避免模型继续猜。"""
    files = scan_files(root)
    rels = [f["rel"] for f in files]
    base = os.path.basename((rel or "").replace("\\", "/"))
    cands = difflib.get_close_matches(rel or "", rels, n=3, cutoff=0.4)
    if not cands and base:
        cands = [r for r in rels if os.path.basename(r) == base][:3]
    if not cands:
        cands = [r for r in rels if base and base.split(".")[0] in r][:3]
    note = f"=== {rel} ===\n[未找到:{reason or '路径不存在'}]"
    if cands:
        note += "\n最相近的候选:" + "、".join(cands)
    note += "\n(可用 skill__<name>() 查看完整文件清单)"
    return note


def read_many(root: str, paths: list[str], offset: int = 0,
              max_bytes: int = READ_MAX_BYTES_DEFAULT,
              total_bytes: int = BATCH_TOTAL_BYTES,
              section: str | None = None) -> str:
    """批量读取多个文件;超出单批总量时截停在界内并说明剩余。

    section 给定时对每个文件都只读该节(路径自带的 `#标题` 优先)。
    """
    if not paths:
        return ""
    chunks: list[str] = []
    used = 0
    skipped: list[str] = []
    for rel in paths:
        if used >= total_bytes:
            skipped.append(rel)
            continue
        chunk = read_path(root, rel, offset=offset, max_bytes=max_bytes, section=section)
        used += len(chunk.encode("utf-8"))
        chunks.append(chunk)
    out = "\n\n".join(chunks)
    if skipped:
        out += (
            f"\n\n[本批已返回约 {_human(used)},达到单次上限 {_human(total_bytes)};"
            f"以下 {len(skipped)} 个文件未读,请下一批再取: {'、'.join(skipped)}]"
        )
    return out
