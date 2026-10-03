from __future__ import annotations
import json
import os
import re as _re
import shutil
import subprocess
from Symbix_sdk.tools.file_pipeline import (
    assert_path_allowed,
    parse_file_path,
    sandbox_roots,
)
from Symbix_sdk.checkpoint import get_recorder, get_current


_RG_CANDIDATES = [
    # Windows 下常见安装位置（C: 系统盘）
    r"C:\Program Files\ripgrep\rg.exe",
    r"C:\Program Files (x86)\ripgrep\rg.exe",
    # scoop / chocolatey
    os.path.expandvars(r"%USERPROFILE%\scoop\shims\rg.exe"),
    os.path.expandvars(r"%USERPROFILE%\scoop\apps\ripgrep\current\rg.exe"),
    r"C:\ProgramData\chocolatey\bin\rg.exe",
    # pi 自带的 rg
    os.path.expandvars(r"%USERPROFILE%\.pi\agent\bin\rg.exe"),
    # Unix
    "/usr/bin/rg",
    "/usr/local/bin/rg",
    "/opt/homebrew/bin/rg",
]


def _find_rg() -> str | None:
    """定位 ripgrep 可执行文件。返回可执行路径或 None。"""
    env_path = os.environ.get("SYMBIX_RG_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    for name in ("rg", "rg.exe"):
        found = shutil.which(name)
        if found:
            return found
    for cand in _RG_CANDIDATES:
        if cand and os.path.isfile(cand):
            return cand
    return None

def create_file(file_path: str, content: str) -> str:
    """创建新文件并写入内容。

    与 edit_file 的区别:仅用于**新建**文件;文件已存在时返回错误(避免误覆盖已有内容)。
    二进制/办公文档(docx/xlsx/pptx/pdf/图片等)请用 doc_tools 读写。
    """
    if file_path is None or content is None:
        return "Error: file_path 和 content 都不能为空"
    try:
        path = assert_path_allowed(file_path)
        if os.path.isdir(path):
            return f"Error: 路径是目录: {path}"
        if os.path.exists(path):
            return f"Error: 文件已存在: {path}"
        # 职责边界:二进制办公文档/图片/PDF 不能用纯文本创建(会损坏文件)。
        _BIN_SUFFIX = (
            ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
            ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
        )
        if path.lower().endswith(_BIN_SUFFIX):
            return (
                f"create_file 不处理二进制/办公文档({os.path.splitext(path)[1]}),"
                "新建此类文件请用 doc_tools 的 md_to_docx / md_to_xlsx / md_to_pptx / md_to_pdf。"
            )
        # 父目录不存在时自动创建(避免写失败)
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        # ── checkpoint:记录创建事件(新建文件无 before 快照,只记 after)──
        session_id, round_id = get_current()
        try:
            recorder = get_recorder() if (session_id and round_id) else None
        except Exception:
            recorder = None
        if recorder is not None:
            try:
                hash_after = recorder.put_blob(content) if content else None
                recorder.emit_file_op(
                    session_id=session_id,
                    round_id=round_id,
                    op="create",
                    path=path,
                    size_before=None,
                    size_after=len(content),
                    hash_before=None,
                    hash_after=hash_after,
                    blob_stored=bool(content),
                )
            except Exception:
                pass  # checkpoint 失败不影响主流程
        return f"File created: {path}"
    except Exception as e:
        return f"Error creating file {file_path}: {e}"
    
def edit_file(file_path: str, new_content: str) -> str:
    """编辑(覆盖写入)文件 —— 仅限纯文本类文件(md/txt/代码/配置)。"""
    if file_path is None or new_content is None:
        return "Error: file_path 和 new_content 都不能为空"
    try:
        path = assert_path_allowed(file_path)
        # 职责边界:二进制办公文档/图片/PDF 不能用纯文本覆盖写(会损坏文件)。
        # 这类文件请用 doc_to_markdown/doc_to_markdown_file 读出 md 后,
        # 修改内容,再用 md_to_docx/md_to_xlsx/md_to_pptx/md_to_pdf 写回。
        _BIN_SUFFIX = (
            ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
            ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
        )
        if path.lower().endswith(_BIN_SUFFIX):
            return (
                f"edit_file 不处理二进制/办公文档({os.path.splitext(path)[1]}),"
                "直接用文本覆盖会损坏文件。请改用专门工具:\n"
                "  1) 读取内容 → doc_to_markdown 或 doc_to_markdown_file\n"
                "  2) 修改得到的 Markdown\n"
                "  3) 写回 → md_to_docx / md_to_xlsx / md_to_pptx / md_to_pdf(视目标格式)\n"
            )
        # ── checkpoint：仅当处于工具执行上下文时，做前后快照 + 记录 ──
        session_id, round_id = get_current()
        try:
            recorder = get_recorder() if (session_id and round_id) else None
        except Exception:
            recorder = None
        blob_stored = False
        size_before = None
        hash_before = None
        size_after = None
        hash_after = None
        if recorder is not None:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existed_old = f.read()
                size_before = len(existed_old)
                if existed_old:
                    hash_before = recorder.put_blob(existed_old)
                    blob_stored = True
            except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError, PermissionError):
                pass  # 新文件 / 二进制 / 目录：不存 before
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        if recorder is not None:
            size_after = len(new_content)
            if new_content:
                hash_after = recorder.put_blob(new_content)
                blob_stored = True
            recorder.emit_file_op(
                session_id=session_id,
                round_id=round_id,
                op="write",
                path=path,
                size_before=size_before,
                size_after=size_after,
                hash_before=hash_before,
                hash_after=hash_after,
                blob_stored=blob_stored,
            )
        return f"File saved: {path}"
    except Exception as e:
        return f"Error editing file {file_path}: {e}"


def list_files(directory: str = ".", recursive: bool = False, max_entries: int = 500) -> str:
    """列出指定目录下的文件和子目录

    Args:
        directory: 要列出的目录,默认当前目录。
        recursive: 是否递归列出子目录,默认否。
        max_entries: 最多返回多少条目,超出截断并提示(防止递归大目录如 node_modules 一次返回几万条把 LLM 上下文撑爆)。

    Returns:
        条目列表文本(每行一个),超出 max_entries 时末尾带截断提示。
    """
    import os
    try:
        directory = assert_path_allowed(directory)
        entries = []
        truncated = False
        omit_dirs = {"node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build"}
        if recursive:
            for root, dirs, files in os.walk(directory):
                # 跳过常见超大目录,避免把 node_modules / .git 等塞进上下文
                dirs[:] = [d for d in dirs if d not in omit_dirs]
                rel = os.path.relpath(root, directory)
                prefix = "" if rel == "." else rel + "/"
                for d in dirs:
                    entries.append(f"{prefix}{d}/")
                    if len(entries) >= max_entries:
                        truncated = True
                        break
                if truncated:
                    break
                for f in files:
                    entries.append(f"{prefix}{f}")
                    if len(entries) >= max_entries:
                        truncated = True
                        break
                if truncated:
                    break
        else:
            for name in os.listdir(directory):
                full = os.path.join(directory, name)
                if os.path.isdir(full):
                    entries.append(f"{name}/")
                else:
                    entries.append(name)
                if len(entries) >= max_entries:
                    truncated = True
                    break
        result = "\n".join(sorted(entries)) if entries else "(empty)"
        if truncated:
            result += f"\n...(已截断,目录内容过多,仅列出前 {len(entries)} 条;如需查看子目录请递归指定具体路径)"
        return result
    except Exception as e:
        return f"Error listing directory {directory}: {e}"


def read_file(file_path: str) -> str:
    """读取文件内容 —— 仅限纯文本文件(md/txt/代码/配置)。"""
    try:
        path = assert_path_allowed(file_path)
        _BIN_SUFFIX = (
            ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
            ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
        )
        if path.lower().endswith(_BIN_SUFFIX):
            return (
                f"read_file 不处理二进制/办公文档({os.path.splitext(path)[1]}),"
                "请改用 doc_to_markdown(解析为 Markdown 文本)或 doc_to_markdown_file(转成 .md 文件)。"
            )
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file {file_path}: {e}"


def parse_file(file_path: str, max_chars: int = 50000) -> str:
    """结构化解析文件（txt/md/json/csv/pdf/docx/图片元信息），返回可读文本摘要。"""
    try:
        max_chars = int(max_chars) if max_chars is not None else 50000
    except (TypeError, ValueError):
        max_chars = 50000
    max_chars = max(500, min(max_chars, 200_000))

    try:
        parsed = parse_file_path(
            file_path,
            max_chars=max_chars,
            include_image_base64=False,
        )
        if parsed.get("status") != "ok":
            return parsed.get("message") or f"Error parsing {file_path}"
        kind = parsed.get("kind") or "file"
        name = parsed.get("filename") or file_path
        path = parsed.get("path") or file_path
        body = parsed.get("text") or ""
        size = parsed.get("size")
        header = f"[{kind}] {name} ({size} bytes)\npath: {path}\n"
        return header + body
    except Exception as e:
        return f"Error parsing file {file_path}: {e}"


def search_files(
    query: str,
    path: str,
    glob: str | None = None,
    max_results: int = 100,
    timeout: int = 30,
) -> dict:
    """使用 ripgrep 在文件中搜索关键词/正则，返回匹配列表。
    rg 不可用时自动回退到 Python os.walk + re 搜索，保证总能工作。
    """
    if not path or not query:
        return {"success": False, "error_msg": "path 和 query 均不能为空", "results": []}
    # 统一通过沙箱解析相对路径（相对项目根优先，避免依赖进程 cwd）
    try:
        root_path = assert_path_allowed(path)
    except Exception as e:
        return {"success": False, "error_msg": f"路径不被允许: {e}", "results": []}
    if not os.path.exists(root_path):
        return {"success": False, "error_msg": f"路径不存在: {root_path}", "results": []}

    rg_path = _find_rg()
    if rg_path:
        return _search_with_rg(
            rg_path, query, root_path, glob, max_results, timeout
        )
    return _search_with_python(query, root_path, glob, max_results, timeout)


def _search_with_rg(
    rg_path: str,
    query: str,
    root_path: str,
    glob: str | None,
    max_results: int,
    timeout: int,
) -> dict:
    cmd = [rg_path, "--json", query, root_path]
    if glob:
        cmd += ["--glob", glob]
    cmd += ["--max-count", str(max_results)]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error_msg": f"搜索超时(超过 {timeout} 秒),请缩小搜索范围", "results": []}
    except OSError as e:
        # rg 调起失败（权限/文件损伤等）→ 退化到 Python 回退
        return _search_with_python(query, root_path, glob, max_results, timeout, note=f"rg 调起失败: {e}")
    if result.returncode == 2:
        return {"success": False, "error_msg": f"rg 执行出错: {result.stderr.strip()}", "results": []}

    matches = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "match":
            continue
        matches.append({
            "file": obj["data"]["path"]["text"],
            "line_number": obj["data"]["line_number"],
            "line_content": obj["data"]["lines"]["text"].rstrip("\n"),
        })
    truncated = False
    if len(matches) > max_results:
        matches = matches[:max_results]
        truncated = True
    return {"success": True, "error_msg": None, "results": matches, "truncated": truncated}


# Python 回退时的默认忽略目录（保持与 rg .gitignore 默认行为接近）
_PY_FALLBACK_IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
}


def _search_with_python(
    query: str,
    root_path: str,
    glob: str | None,
    max_results: int,
    timeout: int,
    note: str | None = None,
) -> dict:
    """rg 不可用时用 Python 实现 grep。支持正则（re.search）与 glob 过滤。"""
    try:
        pattern = _re.compile(query, _re.IGNORECASE)
    except _re.error as e:
        return {"success": False, "error_msg": f"无效的正则表达式 '{query}': {e}", "results": []}
    glob_re = None
    if glob:
        try:
            glob_re = _re.compile(_re.escape(glob).replace(r"\*", ".*").replace(r"\?", "."))
        except _re.error:
            glob_re = None

    matches: list[dict] = []
    truncated = False
    import time
    deadline = time.time() + timeout
    try:
        for dirpath, dirnames, filenames in os.walk(root_path):
            if time.time() > deadline:
                return {"success": False, "error_msg": f"搜索超时(超过 {timeout} 秒),请缩小搜索范围", "results": []}
            # 裁剪忽略目录
            dirnames[:] = [d for d in dirnames if d not in _PY_FALLBACK_IGNORE_DIRS]
            for name in filenames:
                if glob_re and not glob_re.search(name):
                    continue
                fpath = os.path.join(dirpath, name)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        for lineno, line in enumerate(f, 1):
                            if pattern.search(line):
                                matches.append({
                                    "file": fpath,
                                    "line_number": lineno,
                                    "line_content": line.rstrip("\n"),
                                })
                                if len(matches) >= max_results:
                                    truncated = True
                                    break
                            if time.time() > deadline:
                                return {"success": False, "error_msg": f"搜索超时(超过 {timeout} 秒),请缩小搜索范围", "results": []}
                        if truncated:
                            break
                except (OSError, UnicodeDecodeError, PermissionError):
                    continue
            if truncated:
                break
    except OSError as e:
        return {"success": False, "error_msg": f"遍历失败: {e}", "results": []}
    return {
        "success": True,
        "error_msg": None,
        "results": matches,
        "truncated": truncated,
        "fallback": True,
        "note": note or "ripgrep 不可用，已使用 Python 内置搜索（较慢，请考虑安装 ripgrep）",
    }

# 帮助Agent找到文件中具体的某一部分，然后再实施替换
def search_and_replace(
    query: str = "",
    new_content: str = "",
    path: str = ".",
    max_length: int = 100,
) -> dict:
    """搜索文件中匹配 query 的位置，然后用 new_content 替换该行。

    适合代码片段替换、配置项修改等场景。返回替换后的结果字典。
    """
    if not query or not new_content:
        return {"success": False, "error_msg": "query 和 new_content 都不能为空", "results": []}

    # 搜索（限制到 3 处，避免太多结果）
    search_res = search_files(
        query=query,
        path=path,
        max_results=3,
        timeout=20,
    )
    if not search_res.get("success") or not search_res["results"]:
        return search_res

    results = search_res["results"]
    if len(results) > 1:
        return {
            "success": False,
            "error_msg": f"找到 {len(results)} 处匹配，请指定要替换哪一个（可再调用 search_files 确认）",
            "results": results,
        }

    match = results[0]
    file_path = match["file"]
    line_number = match["line_number"]
    original_line = match["line_content"]

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if 0 <= line_number - 1 < len(lines):
            lines[line_number - 1] = new_content.rstrip() + "\n" if new_content else ""
        new_file_content = "".join(lines)

        # 使用 edit_file 写入整个新内容
        edit_file(file_path, new_file_content)

        return {
            "success": True,
            "file": file_path,
            "replaced_line": line_number,
            "original_line": original_line,
            "new_line": new_content,
            "message": f"已成功替换第 {line_number} 行"
        }
    except Exception as e:
        return {"success": False, "error_msg": f"替换失败: {e}", "results": []}

# 根据文件名查找文件,输入文件名，返回路径
def search_file_with_name(
    file_name: str,
    root_path: str | None = None,
    max_results: int = 50,
    timeout: int = 30,
) -> dict:
    """根据文件名在指定根目录下递归查找文件,返回匹配的路径列表。

    用于用户只提供了文件名、需要定位完整路径的场景(如查看某配置、引用文件实际位置)。
    底层用 ripgrep --files + 过滤,比 os.walk 快很多;ripgrep 不存在时回退到 os.walk。
    root_path 缺省时覆盖整个可访问工作区(项目根 + uploads + 后端 + 文件面板授权过的目录),
    避免只搜一个小目录导致“找不到”。
    """
    if not file_name:
        return {"success": False, "error_msg": "file_name 不能为空", "results": []}

    # 确定搜索根:缺省 → 整个可访问工作区;显式传 → 沙箱校验后单根。
    roots: list[str] = []
    if root_path:
        try:
            r = assert_path_allowed(root_path)
        except Exception as e:
            return {"success": False, "error_msg": f"根路径不被允许: {e}", "results": []}
        if not os.path.isdir(r):
            return {"success": False, "error_msg": f"不是目录或不存在: {r}", "results": []}
        roots = [r]
    else:
        for r in sandbox_roots():
            r = os.path.abspath(r)
            if os.path.isdir(r) and r not in roots:
                roots.append(r)

    # 用 ripgrep --files 列出所有文件,然后客户端模糊匹配文件名(包含)。
    # 这样能复用 ripgrep 的 .gitignore / 隐藏文件过滤逻辑,避免扫到 node_modules。
    results: list[dict] = []
    needle = file_name.lower()
    use_walk = False
    rg_path = _find_rg()
    try:
        if rg_path:
            proc = subprocess.run(
                [rg_path, "--files", "-S", "--hidden", *roots],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout,
            )
            if proc.returncode not in (0, 1):  # 1 = 无匹配,是正常
                use_walk = True
            else:
                for line in proc.stdout.splitlines():
                    if not line:
                        continue
                    base = os.path.basename(line)
                    if needle in base.lower():
                        results.append({"file": line, "name": base})
                        if len(results) >= max_results:
                            break
        else:
            use_walk = True
    except FileNotFoundError:
        use_walk = True
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error_msg": f"查找超时(超过 {timeout} 秒),请缩小 root_path 或减少 node_modules",
            "results": [],
        }
    except Exception:
        use_walk = True

    # 回退:ripgrep 不可用时用 os.walk
    if use_walk:
        # 跳过常见大目录,避免扫死项目
        _SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".next", "dist", "build", ".venv", "venv"}
        for root in roots:
            for dirpath, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
                for name in files:
                    if needle in name.lower():
                        results.append({
                            "file": os.path.join(dirpath, name),
                            "name": name,
                        })
                        if len(results) >= max_results:
                            break
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break

    truncated = len(results) >= max_results
    if not results:
        return {
            "success": True,
            "error_msg": None,
            "results": [],
            "truncated": False,
            "message": f"未找到匹配 {file_name!r} 的文件",
        }
    return {
        "success": True,
        "error_msg": None,
        "results": results,
        "truncated": truncated,
        "message": f"找到 {len(results)} 个匹配文件",
    }
# ---------------------------------------------------------------------------
# 工具 schema 注册表 (供 tool_setup.py 统一注册)
# ---------------------------------------------------------------------------

FILE_TOOLS_SCHEMAS = {
    "create_file": {
        "risk_channel": "write",
        "func": create_file,
        "description": (
            "创建新文件并写入内容(仅用于新建文件,文件已存在时返回错误,不会覆盖)。"
            "适合新建代码/配置/markdown/文本文件。"
            "修改已存在的文件请用 edit_file(支持覆盖写入含新建);"
            "docx/xlsx/pptx/pdf/图片等二进制文件不要用本工具(会损坏),请用 md_to_* 生成。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要创建的文件路径（新文件,父目录不存在会自动创建）",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的文件内容",
                },
            },
            "required": ["file_path", "content"],
        },
    },
    "edit_file": {
        "risk_channel": "write",
        "func": edit_file,
        "description": "编辑或创建文本文件(md/txt/代码/配置),将内容写入指定路径。注意:docx/xlsx/pptx/pdf/图片等二进制文件不要用本工具(会损坏文件),请用 doc_to_markdown 读取 + md_to_* 写回。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要编辑的文件路径",
                },
                "new_content": {
                    "type": "string",
                    "description": "要写入的新内容",
                },
            },
            "required": ["file_path", "new_content"],
        },
    },
    "list_files": {
        "risk_channel": "read",
        "func": list_files,
        "description": "列出指定目录下的文件和文件夹。如果不知道要读什么文件,先调用此工具浏览目录结构。工作目录是 F:\\Symbix,源代码在 backend/ 和 Symbix_frontend/ 中。",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "要浏览的目录路径,默认为当前工作目录 (F:\\Symbix)",
                    "default": ".",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "是否递归列出所有子目录和文件,默认为 false。注意:递归大目录(如 node_modules)会被自动截断到 500 条内",
                    "default": False,
                },
                "max_entries": {
                    "type": "integer",
                    "description": "最多返回多少条目,默认 500;超出截断并提示(防止大目录撑爆上下文)",
                    "default": 500,
                },
            },
            "required": [],
        },
    },
    "read_file": {
        "risk_channel": "read",
        "func": read_file,
        "description": "读取指定路径的文本文件(md/txt/代码/配置/json 等)内容。先用 list_files 浏览目录结构确定文件路径,再用本工具读取。工作目录是 F:\\Symbix。注意:docx/xlsx/pptx/pdf/图片等二进制文件不要用本工具,请用 doc_to_markdown。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要读取的文件路径(相对于工作目录 F:\\Symbix 的路径或绝对路径)",
                },
            },
            "required": ["file_path"],
        },
    },
    "parse_file": {
        "risk_channel": "read",
        "func": parse_file,
        "description": (
            "结构化解析本地/上传文件内容并返回文本摘要。"
            "支持 txt/md/json/csv/代码、PDF、DOCX、图片元信息。"
            "用户附件路径一般在 backend/uploads/<session_id>/ 下；"
            "比 read_file 更适合 PDF/表格/二进制文档。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件绝对路径或工作区内路径（上传接口返回的 path 可直接使用）",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "返回文本最大字符数，默认 50000",
                    "default": 50000,
                },
            },
            "required": ["file_path"],
        },
    },
    "search_and_replace": {
        "risk_channel": "write",
        "func": search_and_replace,
        "description": (
            "搜索文件中匹配 query 的位置，然后用 new_content 替换该行。"
            "适合代码片段替换、配置项修改等场景。先用 search_files 定位，再调用本工具精确替换。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要搜索的关键词或正则（如 'def search_and_replace'、'# TODO'）",
                },
                "new_content": {
                    "type": "string",
                    "description": "替换后的新行内容（完整一行代码或文本）",
                },
                "path": {
                    "type": "string",
                    "description": "搜索根目录，默认当前工作目录",
                    "default": ".",
                },
                "max_length": {
                    "type": "integer",
                    "description": "替换行最大长度（可选）",
                    "default": 100,
                },
            },
            "required": ["query", "new_content"],
        },
    },
    "search_files": {
        "risk_channel": "read",
        "func": search_files,
        "description": (
            "在指定路径下使用 ripgrep 进行正则/关键词搜索（类似 grep）。"
            "用于快速定位某个函数定义、类名、TODO 注释、配置项或任何文本片段的位置。"
            "返回匹配所在的文件路径、行号和行内容；支持 glob 过滤文件类型（如 *.py、*.vue）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要搜索的文本或正则表达式，如 'def search_files' 或 'TODO'",
                },
                "path": {
                    "type": "string",
                    "description": "要搜索的根目录路径，如 '.' 或 'backend/'",
                },
                "glob": {
                    "type": "string",
                    "description": "可选的文件匹配模式，如 '*.py'、'*.{ts,vue}'，用于只搜索特定类型文件",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大返回结果数，默认 100",
                    "default": 100,
                },
                "timeout": {
                    "type": "integer",
                    "description": "搜索超时时间（秒），默认 30",
                    "default": 30,
                },
            },
            "required": ["query", "path"],
        },
    },
    "search_file_with_name": {
        "risk_channel": "read",
        "func": search_file_with_name,
        "description": (
            "根据文件名(或文件名片段)在整个工作区中递归查找文件并返回完整路径。"
            "用于只知道文件名、需要定位文件完整路径的场景(如查找某配置、引用、上传文件的位置)。"
            "root_path 可不传:缺省搜索整个可访问工作区(项目根 + uploads + 后端 + 文件面板授权过的目录),"
            "所以通常无需指定 root_path;只有当你知道目标在某个特定子目录、想缩小范围时才传。"
            "与 search_files 区别:后者按内容找行;本工具按文件名找文件。底层优先用 ripgrep,找不到时回退到 os.walk。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_name": {
                    "type": "string",
                    "description": "要查找的文件名或文件名片段（大小写不敏感），如 'providers.json' 或 'README'",
                },
                "root_path": {
                    "type": "string",
                    "description": "可选。限定查找的子目录根(相对于工作区或绝对路径);不传则搜索整个工作区",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大返回结果数，默认 50",
                    "default": 50,
                },
                "timeout": {
                    "type": "integer",
                    "description": "查找超时时间（秒），默认 30",
                    "default": 30,
                },
            },
            "required": ["file_name"],
        },
    },
}