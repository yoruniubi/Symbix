from __future__ import annotations

import base64
import csv
import io
import json
import mimetypes
import os
import re
import uuid
from pathlib import Path
from typing import Any, Optional

# ── 配置 ──────────────────────────────────────────────
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_MAX_TEXT_CHARS = 50_000
DEFAULT_MAX_IMAGE_BYTES = 4 * 1024 * 1024  # 4 MB 内嵌 vision

TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".json", ".jsonl", ".csv", ".tsv",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".html", ".css",
    ".yaml", ".yml", ".toml", ".xml", ".log", ".ini", ".cfg",
    ".sh", ".bat", ".ps1", ".sql", ".r", ".go", ".rs", ".java",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
PDF_EXTS = {".pdf"}
DOCX_EXTS = {".docx"}
OFFICE_EXTS = {".docx", ".xlsx", ".pptx"}  # 二进制办公文档:以 Markdown 为读写媒介

ALLOWED_EXTS = TEXT_EXTS | IMAGE_EXTS | PDF_EXTS | DOCX_EXTS | OFFICE_EXTS | {".doc", ".xls", ".ppt"}

MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def _backend_dir() -> str:
    # tools/ -> Symbix_sdk/ -> backend/
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_uploads_root() -> str:
    root = os.path.join(_backend_dir(), "uploads")
    os.makedirs(root, exist_ok=True)
    return os.path.abspath(root)


def get_project_root() -> str:
    # backend/ 的上一级 = Symbix 仓库根
    return os.path.abspath(os.path.join(_backend_dir(), ".."))

def _resize_image_bytes(
    data: bytes,
    *,
    max_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
    max_side: int = 2048,
    quality: int = 82,
) -> bytes:
    """把超大图片压缩到 ≤ max_bytes 以便内嵌 vision。

    - 先限最长边到 max_side,防像素爆炸。
    - 统一编码为 JPEG(动图取首帧、透明通道铺白底)后,质量从 quality
      递减重存直到体积达标;仍超则半尺寸重试一次。
    - PIL 不可用/解码失败时原样返回(由调用方继续走“过大跳过”分支)。
    """
    try:
        from PIL import Image
    except Exception:
        return data
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        fmt = (img.format or "PNG").upper()
        w, h = img.size
    except Exception:
        return data
    try:
        if fmt == "GIF":
            # 动图只取第一帧,后续统一走静态 JPEG 路径
            img.seek(0)
        img = img.convert("RGBA")

        def _side_limit(im, side):
            ww, hh = im.size
            longest = max(ww, hh)
            if longest > side:
                ratio = side / longest
                return im.resize((max(1, int(ww * ratio)), max(1, int(hh * ratio))),
                                 Image.LANCZOS)
            return im

        img = _side_limit(img, max_side)

        def _save_jpeg(im, q):
            # 透明铺白底(视觉内嵌不追求透明背景)
            bg = Image.new("RGB", im.size, (255, 255, 255))
            if im.mode == "RGBA":
                bg.paste(im, mask=im.split()[-1])
            else:
                bg.paste(im)
            buf = io.BytesIO()
            bg.save(buf, "JPEG", quality=q)
            return buf.getvalue()

        # 质量递降:82 → 60 → 40,仍不达标再降一半尺寸重试一轮
        for half in (False, True):
            cur = img
            if half:
                cur = _side_limit(cur, max(max_side // 2, 64))
            for q in (quality, max(quality - 20, 45), max(quality - 40, 30)):
                out = _save_jpeg(cur, q)
                if len(out) <= max_bytes:
                    return out
        # 极端情况:极小质量 + 半尺寸仍超 → 返回最后一次结果(尽力而为)
        return out
    except Exception:
        return data



# 会话内累积的“用户授权目录”(FilePanel 浏览过的项目外目录)。
# 进程内可变;重启后端即清空(不落盘,避免悄悄扩大授权面)。
_workspace_roots: set[str] = set()


def add_workspace_root(path: str) -> str:
    """把用户显式浏览过/授权的目录加入 Agent 可读区。返回规范化的绝对路径。"""
    p = os.path.abspath(os.path.expanduser(str(path or "").strip()))
    if not os.path.isdir(p):
        raise ValueError(f"目录不存在: {p}")
    _workspace_roots.add(p)
    return p


def remove_workspace_root(path: str) -> None:
    p = os.path.abspath(os.path.expanduser(str(path or "").strip()))
    _workspace_roots.discard(p)


def clear_workspace_roots() -> None:
    _workspace_roots.clear()


def workspace_roots() -> list[str]:
    return sorted(_workspace_roots)


# 硬性禁止区:无论是否在授权目录/项目内,命中即拒。
# 目的:防 Agent 误读/改系统关键文件(模型幻觉或 prompt 注入都挡不住时,这里是最后防线)。
_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    os.environ.get("SystemRoot", "C:\\Windows"),  # C:\Windows 及其下
    os.environ.get("ProgramFiles", "C:\\Program Files"),
    os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
)
_FORBIDDEN_SUFFIXES: tuple[str, ...] = (  # 绝对路径直接命中这些即拒
    ".ssh",
    ".gnupg",
)
_FORBIDDEN_NAMES: tuple[str, ...] = (  # 任何目录层级下出现即拒(相对路径场景)
    "C:\\Windows",
    "\\Windows\\",
    "Program Files",
    "$Recycle.Bin",
    "System Volume Information",
    "Recovery",
    "AppData\\Local\\Temp",
)


def _in_forbidden(path_abs: str) -> bool:
    """判断绝对路径是否命中硬禁止区(系统关键路径/密钥目录)。"""
    try:
        path_abs = os.path.abspath(path_abs)
    except Exception:
        return True
    # 盘符不同则肯定不在 Windows 禁止前缀下(如 D:\Windows 允许)
    for pref in _FORBIDDEN_PREFIXES:
        try:
            if os.path.commonpath([path_abs, pref]) == pref:
                return True
        except ValueError:
            continue
    upper = path_abs.upper()
    for name in _FORBIDDEN_NAMES:
        if name.upper() in upper:
            return True
    for suffix in _FORBIDDEN_SUFFIXES:
        parts = path_abs.split(os.sep)
        if any(p.lower() == suffix.lower() for p in parts):
            return True
    return False


def forbidden_roots() -> list[str]:
    return [p for p in _FORBIDDEN_PREFIXES if p] + list(_FORBIDDEN_NAMES)


def safe_filename(name: str) -> str:
    """去掉路径成分，仅保留安全文件名。"""
    base = os.path.basename(name or "file")
    base = re.sub(r"[^\w.\u4e00-\u9fff\-]+", "_", base, flags=re.UNICODE)
    base = base.strip("._") or "file"
    return base[:180]


def is_allowed_extension(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTS


def resolve_under_root(path: str, roots: list[str]) -> Optional[str]:
    """
    将 path 解析为绝对路径,并要求其落在任一 root 之下(防 .. 穿越)。
    命中硬禁止区(Windows 目录等)一律拒绝。
    成功返回 abspath,否则 None。

    相对路径的处理顺序:
      1) 优先把相对路径拼到每个 root 下,落在 sandbox 任一 root 内即用(避免进程 cwd 依赖
         ——后端 cwd 常是 backend/,单纯的 cwd 相对解析会把 'backend/xxx' 拼成 backend/backend/xxx)
      2) 否则回退到相对进程 cwd 解析,仍要求落在 sandbox 内
    绝对路径直接判定 sandbox。
    """
    if not path or not str(path).strip():
        return None

    norm = path.strip()
    roots_abs = [os.path.abspath(r) for r in roots]

    # 绝对路径:直接判 sandbox
    if os.path.isabs(norm):
        try:
            abs_path = os.path.abspath(os.path.expanduser(norm))
        except Exception:
            return None
        if _in_forbidden(abs_path):
            return None
        for root_abs in roots_abs:
            try:
                if os.path.commonpath([abs_path, root_abs]) == root_abs:
                    return abs_path
            except ValueError:
                continue
        return None

    # 相对路径:先尝试拼到每个 root 下。
    # 优先级:父目录存在的优先(read_file/list_files/edit_file 语义一致;
    # edit_file 写新文件从项目根开始试,backend/Symbix_sdk/x 正确落到 backend 下)。
    candidates: list[str] = []
    for root_abs in roots_abs:
        # 单独 '.' 的特殊语义:直接对应 root 本身
        if norm == ".":
            return root_abs if not _in_forbidden(root_abs) else None
        candidate = os.path.abspath(os.path.join(root_abs, norm))
        try:
            if os.path.commonpath([candidate, root_abs]) == root_abs:
                candidates.append(candidate)
        except ValueError:
            continue
    # 过滤硬禁止区
    candidates = [c for c in candidates if not _in_forbidden(c)]
    # 1) 优先选路径本身存在的( 目录或文件,读根据不歧义)
    for c in candidates:
        if os.path.exists(c):
            return c
    # 2) 次之选父目录存在的(edit_file 写新文件场景)
    for c in candidates:
        if os.path.isdir(os.path.dirname(c)):
            return c
    # 3) 都不存在:回退到 cwd 相对解析若仍 sandbox 内
    try:
        cwd_abs = os.path.abspath(os.path.expanduser(norm))
    except Exception:
        cwd_abs = None
    if cwd_abs is not None and not _in_forbidden(cwd_abs):
        for root_abs in roots_abs:
            try:
                if os.path.commonpath([cwd_abs, root_abs]) == root_abs:
                    return cwd_abs
            except ValueError:
                continue
    # 4) 最后凑合:选第一个 sandbox 内候选(允许新文件可解析)
    return candidates[0] if candidates else None


def sandbox_roots() -> list[str]:
    """native 文件工具允许访问的根目录 = 项目根 + uploads + 会话内授权目录。"""
    return [
        get_project_root(),
        get_uploads_root(),
        _backend_dir(),
        *workspace_roots(),
    ]


def check_path_in_sandbox(path: str) -> tuple[bool, str]:
    """返回 (ok, abs_path_or_error)。"""
    resolved = resolve_under_root(path, sandbox_roots())
    if not resolved:
        return False, (
            f"[Error] 路径不在允许的工作区内或命中系统保护目录: {path}。"
            f"允许: 项目目录 / uploads / 文件面板中授权过的目录。"
            f"系统目录(Windows/Program Files 等)与密钥目录不可访问。"
        )
    return True, resolved


def assert_path_allowed(path: str) -> str:
    """校验路径在沙箱内；成功返回绝对路径，失败抛出 PermissionError。"""
    ok, resolved = check_path_in_sandbox(path)
    if not ok:
        raise PermissionError(resolved)
    return resolved


def resolve_under_allowed(path: str) -> Optional[str]:
    """解析路径到沙箱内绝对路径，失败返回 None（不抛异常）。"""
    return resolve_under_root(path, sandbox_roots())


def session_upload_dir(session_id: str) -> str:
    sid = re.sub(r"[^\w\-]+", "_", (session_id or "default"))[:80] or "default"
    d = os.path.join(get_uploads_root(), sid)
    os.makedirs(d, exist_ok=True)
    return d


def save_upload(
    *,
    session_id: str,
    filename: str,
    data: bytes,
    max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> dict[str, Any]:
    """
    保存上传文件。返回:
    {status, path, filename, size, ext, mime, message}
    """
    if not data:
        return {"status": "error", "message": "空文件"}
    if len(data) > max_bytes:
        return {
            "status": "error",
            "message": f"文件过大: {len(data)} > {max_bytes} bytes",
        }
    if not is_allowed_extension(filename):
        return {
            "status": "error",
            "message": (
                f"不支持的文件类型: {Path(filename).suffix or '(无扩展名)'}。"
                f"允许: {', '.join(sorted(ALLOWED_EXTS))}"
            ),
        }

    safe = safe_filename(filename)
    ext = Path(safe).suffix.lower()
    unique = f"{uuid.uuid4().hex[:10]}_{safe}"
    dest_dir = session_upload_dir(session_id)
    dest = os.path.join(dest_dir, unique)

    # 二次确认落在 uploads 下
    ok, resolved = check_path_in_sandbox(dest)
    if not ok or not resolved.startswith(get_uploads_root()):
        # 强制只写 uploads
        dest = os.path.join(dest_dir, unique)
        resolved = os.path.abspath(dest)

    with open(resolved, "wb") as f:
        f.write(data)

    mime = MIME_BY_EXT.get(ext) or mimetypes.guess_type(safe)[0] or "application/octet-stream"
    return {
        "status": "ok",
        "path": resolved,
        "filename": safe,
        "stored_name": os.path.basename(resolved),
        "size": len(data),
        "ext": ext,
        "mime": mime,
        "session_id": session_id,
        "message": f"已上传: {safe} -> {resolved}",
    }


def _read_text_bytes(data: bytes, max_chars: int = DEFAULT_MAX_TEXT_CHARS) -> str:
    for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True
    if truncated:
        text += f"\n\n… [已截断，仅保留前 {max_chars} 字符]"
    return text


def parse_file_path(
    file_path: str,
    *,
    max_chars: int = DEFAULT_MAX_TEXT_CHARS,
    include_image_base64: bool = True,
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
) -> dict[str, Any]:
    """
    解析本地文件。返回结构化结果:
    {
      status, path, filename, ext, kind,
      text?, image_base64?, mime?, truncated?, message?
    }
    """
    ok, resolved = check_path_in_sandbox(file_path)
    if not ok:
        return {"status": "error", "message": resolved, "path": file_path}

    if not os.path.isfile(resolved):
        return {"status": "error", "message": f"文件不存在: {resolved}", "path": resolved}

    ext = Path(resolved).suffix.lower()
    filename = os.path.basename(resolved)
    size = os.path.getsize(resolved)

    result: dict[str, Any] = {
        "status": "ok",
        "path": resolved,
        "filename": filename,
        "ext": ext,
        "size": size,
        "kind": "unknown",
    }

    try:
        with open(resolved, "rb") as f:
            data = f.read()
    except Exception as e:
        return {"status": "error", "message": f"读取失败: {e}", "path": resolved}

    if ext in TEXT_EXTS or ext == "":
        result["kind"] = "text"
        if ext == ".csv":
            result["kind"] = "csv"
            result["text"] = _parse_csv_bytes(data, max_chars)
        elif ext == ".json":
            result["kind"] = "json"
            result["text"] = _parse_json_bytes(data, max_chars)
        else:
            result["text"] = _read_text_bytes(data, max_chars)
        return result

    if ext in IMAGE_EXTS:
        result["kind"] = "image"
        mime = MIME_BY_EXT.get(ext, "image/png")
        result["mime"] = mime
        if include_image_base64:
            if size > max_image_bytes:
                # 大图先压缩到阈值内再内嵌,保证支持视觉的模型能直接看到图,
                # 而不是让模型去调 parse_file/read_file 读(文本工具对图片无视觉价值)。
                resized = _resize_image_bytes(data, max_bytes=max_image_bytes)
                if len(resized) < len(data):
                    # 压缩成功:按实际编码格式回填 mime(可能 PNG→JPEG)
                    try:
                        from PIL import Image as _PILImage
                        probe = _PILImage.open(io.BytesIO(resized))
                        out_fmt = (probe.format or "PNG").upper()
                        probe.close()
                        mime = {"JPEG": "image/jpeg", "PNG": "image/png",
                                "WEBP": "image/webp"}.get(out_fmt, mime)
                    except Exception:
                        pass
                    data = resized
                    size = len(data)
                    result["size"] = size
                else:
                    result["mime"] = mime
            if size <= max_image_bytes:
                result["image_base64"] = base64.b64encode(data).decode("ascii")
                result["mime"] = mime
                result["text"] = (
                    f"[图片附件: {filename}, 已自动压缩至 {size} bytes, {mime}。"
                    "图片已作为视觉内容直接提供,无需调用 parse_file/read_file 读取。]"
                )
            else:
                result["text"] = (
                    f"[图片附件无法内嵌: {filename}, {size} bytes(即使压缩后仍超限)。"
                    f"路径: {resolved}]"
                )
        else:
            # parse_file 等纯文本工具路径:不给 base64,也不给“过大”这类误导性提示,
            # 明确告知模型图片内容应来自已提供的视觉输入。
            result["text"] = (
                f"[图片文件: {filename}, {size} bytes, {mime}。"
                f"路径: {resolved}]\n"
                "(图片内容无法通过文本工具读取;若需理解图片请直接基于用户本轮已提供的视觉输入,"
                "不要用 parse_file/read_file 反复读图片。)"
            )
        return result

    if ext in PDF_EXTS:
        result["kind"] = "pdf"
        result["text"] = _parse_doc_with_markitdown(
            resolved, data, ext, filename, max_chars
        ) or _parse_pdf_bytes(data, max_chars)
        return result

    if ext in DOCX_EXTS or ext in OFFICE_EXTS:
        result["kind"] = "docx" if ext == ".docx" else "office"
        markdown_text = _parse_doc_with_markitdown(
            resolved, data, ext, filename, max_chars
        )
        if markdown_text:
            result["text"] = markdown_text
        elif ext == ".docx":
            result["text"] = _parse_docx_bytes(data, max_chars)
        elif ext == ".xlsx":
            # openpyxl 直读(不依赖 markitdown[xlsx] extra)
            result["text"] = _parse_xlsx_bytes_native(resolved, max_chars)
        else:
            result["text"] = (
                f"[Office 文档 {ext} 需要安装 markitdown 才能解析:"
                f"pip install 'markitdown[{ext[1:]}]'。路径: {resolved}]"
            )
        return result

    if ext == ".doc":
        result["kind"] = "doc"
        result["text"] = (
            f"[.doc 旧格式暂不支持解析，请转换为 .docx 或 .txt。路径: {resolved}]"
        )
        return result

    # 兜底：尝试文本
    result["kind"] = "binary"
    result["text"] = (
        f"[二进制文件无法作为文本解析: {filename}, {size} bytes, ext={ext}。"
        f"路径: {resolved}]"
    )
    return result


def _parse_doc_with_markitdown(
    resolved_path: str,
    data: bytes,
    ext: str,
    filename: str,
    max_chars: int,
) -> str:
    """用 markitdown 把办公文档(docx/pptx/xlsx/pdf)转 Markdown 文本。

    优先尝试 markitdown(微软,支持表格/版式/嵌入内容,输出 md 媒介);
    库缺失或解析失败时返回空串,由调用方回退到原生解析器。
    """
    try:
        from markitdown import MarkItDown
    except Exception:
        return ""
    try:
        md = MarkItDown()
        # markitdown 支持从字节流读取(避免临时落盘),优先 convert_stream;
        # 旧版本 API 不同,兼容回退到按路径转换。
        try:
            result = md.convert_stream(io.BytesIO(data), file_extension=ext)
        except (TypeError, AttributeError):
            try:
                result = md.convert(io.BytesIO(data))
            except Exception:
                # 按路径转(某些文档类型需要真实扩展名/路径上下文)
                result = md.convert(resolved_path)
        text = (result.text_content or "").strip()
        if not text:
            return ""
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [内容截断 {max_chars} chars]"
        return text
    except Exception:
        return ""


def _parse_csv_bytes(data: bytes, max_chars: int) -> str:
    text = _read_text_bytes(data, max_chars * 2)
    try:
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return "(empty csv)"
        # 限制行数
        max_rows = 200
        shown = rows[:max_rows]
        lines = [" | ".join(c.replace("\n", " ") for c in row) for row in shown]
        out = f"CSV 共 {len(rows)} 行 x {len(rows[0]) if rows else 0} 列(展示前 {len(shown)} 行):\n"
        out += "\n".join(lines)
        if len(out) > max_chars:
            out = out[:max_chars] + f"\n... [截断 {max_chars} chars]"
        return out
    except Exception as e:
        return _read_text_bytes(data, max_chars) + f"\n[csv parse note: {e}]"


def _parse_json_bytes(data: bytes, max_chars: int) -> str:
    raw = _read_text_bytes(data, max_chars * 2)
    try:
        obj = json.loads(raw[: max_chars * 2])
        pretty = json.dumps(obj, ensure_ascii=False, indent=2)
        if len(pretty) > max_chars:
            return pretty[:max_chars] + f"\n… [JSON 截断 {max_chars} chars]"
        return pretty
    except Exception:
        return _read_text_bytes(data, max_chars)


def _parse_pdf_bytes(data: bytes, max_chars: int) -> str:
    # 优先 pypdf / PyPDF2
    for mod_name in ("pypdf", "PyPDF2"):
        try:
            mod = __import__(mod_name)
            reader_cls = getattr(mod, "PdfReader", None)
            if reader_cls is None:
                continue
            reader = reader_cls(io.BytesIO(data))
            parts = []
            for i, page in enumerate(reader.pages):
                try:
                    t = page.extract_text() or ""
                except Exception:
                    t = ""
                if t.strip():
                    parts.append(f"--- page {i + 1} ---\n{t}")
                if sum(len(p) for p in parts) > max_chars:
                    break
            text = "\n\n".join(parts).strip()
            if not text:
                return "[PDF 无可提取文本（可能是扫描件）]"
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n… [PDF 截断 {max_chars} chars]"
            return text
        except ImportError:
            continue
        except Exception as e:
            return f"[PDF 解析失败: {e}]"
    return (
        "[PDF 解析需要安装 pypdf: pip install pypdf。"
        "当前仅保存了文件路径，可用 read_file 无法读二进制 PDF。]"
    )


def _unescape_xml(s: str) -> str:
    # 使用字符码避免编辑器转义破坏字面量
    return (
        s.replace("&" + "lt;", chr(60))
        .replace("&" + "gt;", chr(62))
        .replace("&" + "amp;", chr(38))
        .replace("&" + "quot;", chr(34))
        .replace("&" + "apos;", chr(39))
    )



def _parse_docx_bytes(data: bytes, max_chars: int) -> str:
    try:
        import zipfile
        # 轻量：不强制 python-docx，直接读 word/document.xml
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
        # 用段落分隔近似
        paras = re.split(r"</w:p>", xml)
        lines = []
        for p in paras:
            ts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", p)
            if ts:
                lines.append(_unescape_xml("".join(ts)))
        text = "\n".join(lines).strip()
        if not text:
            texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml)
            text = _unescape_xml("".join(texts)).strip()
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n… [DOCX 截断 {max_chars} chars]"
        return text or "[DOCX 无文本内容]"
    except Exception as e:
        return f"[DOCX 解析失败: {e}]"



def _parse_xlsx_bytes_native(xlsx_path: str, max_chars: int) -> str:
    """openpyxl 直读 xlsx(多个 sheet → md 表格),不依赖 markitdown[xlsx] extra。"""
    try:
        from openpyxl import load_workbook
    except Exception:
        return (
            "[Office 文档 .xlsx 需要安装 openpyxl 才能解析:"
            "pip install openpyxl。路径: " + xlsx_path + "]"
        )
    try:
        wb = load_workbook(xlsx_path, read_only=True, data_only=True)
        parts = []
        total = 0
        for ws in wb.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=True):
                vals = ["" if v is None else str(v).replace("\n", " ") for v in row]
                if any(vals):
                    rows.append(vals)
            if not rows:
                continue
            parts.append(f"## Sheet: {ws.title}")
            parts.append("| " + " | ".join(rows[0]) + " |")
            parts.append("|" + "|".join("---" for _ in rows[0]) + "|")
            for r in rows[1:]:
                r = (r + [""] * len(rows[0]))[: len(rows[0])]
                parts.append("| " + " | ".join(r) + " |")
            total += sum(len(str(c)) for row in rows for c in row)
            if total > max_chars:
                parts.append(f"\n... [内容截断 {max_chars} chars]")
                break
        wb.close()
        text = "\n".join(parts).strip()
        if not text:
            return "[xlsx 无内容]"
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [截断 {max_chars} chars]"
        return text
    except Exception as e:
        return f"[xlsx 解析失败: {e}]"


def format_attachment_block(parsed: dict[str, Any]) -> str:
    """把解析结果格式化为可拼进 prompt 的文本块。"""
    if parsed.get("status") != "ok":
        return f"[附件解析失败: {parsed.get('message', 'unknown')}]"
    name = parsed.get("filename") or "file"
    path = parsed.get("path") or ""
    kind = parsed.get("kind") or "file"
    body = parsed.get("text") or ""
    return (
        f"----- 附件: {name} ({kind}) -----\n"
        f"路径: {path}\n"
        f"{body}\n"
        f"----- 附件结束: {name} -----"
    )


def inject_attachments_into_message(
    message: str,
    attachments: list[dict[str, Any]] | None,
    *,
    max_chars: int = DEFAULT_MAX_TEXT_CHARS,
) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
    """
    根据 attachments 元数据解析文件并注入用户消息。

    attachments 项支持:
      - path: 服务端绝对路径（推荐，upload 后返回）
      - name / filename
      - content: 可选，前端直接给的文本（跳过读盘）
      - type / mime

    返回:
      (enriched_text_message, parsed_list, image_parts)
      image_parts: [{"mime": "...", "base64": "...", "filename": "..."}]
    """
    if not attachments:
        return message, [], []

    blocks: list[str] = []
    parsed_list: list[dict[str, Any]] = []
    image_parts: list[dict[str, str]] = []

    for att in attachments:
        if not isinstance(att, dict):
            continue
        name = att.get("filename") or att.get("name") or "file"
        path = att.get("path") or att.get("file_path") or ""
        inline = att.get("content")

        if inline is not None and str(inline).strip() != "":
            text = str(inline)
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n… [截断 {max_chars}]"
            parsed = {
                "status": "ok",
                "filename": name,
                "path": path or "(inline)",
                "kind": "text",
                "text": text,
            }
        elif path:
            parsed = parse_file_path(path, max_chars=max_chars)
        else:
            parsed = {"status": "error", "message": f"附件缺少 path/content: {name}"}

        parsed_list.append(parsed)
        blocks.append(format_attachment_block(parsed))

        if parsed.get("kind") == "image" and parsed.get("image_base64"):
            image_parts.append(
                {
                    "mime": parsed.get("mime") or "image/png",
                    "base64": parsed["image_base64"],
                    "filename": parsed.get("filename") or name,
                    "path": parsed.get("path") or path,
                }
            )

    if not blocks:
        return message, parsed_list, image_parts

    prefix = "\n\n".join(blocks)
    hint = (
        "\n\n[系统提示] 以上是用户上传附件的解析内容。"
        "请基于附件内容回答；若需再次读取可用 read_file/parse_file，路径已给出。"
    )
    base = (message or "").strip()
    if base:
        enriched = f"{base}\n\n{prefix}{hint}"
    else:
        enriched = f"请分析以下附件：\n\n{prefix}{hint}"
    return enriched, parsed_list, image_parts


def build_user_content_for_llm(
    text: str,
    image_parts: list[dict[str, str]] | None = None,
) -> str | list[dict[str, Any]]:
    """
    构建 OpenAI 兼容的 user content。
    有图片时返回 multipart content list，否则返回纯字符串。
    """
    if not image_parts:
        return text
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for img in image_parts:
        b64 = img.get("base64") or ""
        mime = img.get("mime") or "image/png"
        if not b64:
            continue
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        )
    # 若没有成功附加任何图片，退回文本
    if len(parts) == 1:
        return text
    return parts
