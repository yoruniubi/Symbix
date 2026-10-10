import logging
import os
import re
from typing import Dict, Optional
from urllib.parse import urlparse, unquote

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None

try:
    import httpx
except ImportError:
    httpx = None

logger = logging.getLogger(__name__)

# 下载默认最大尺寸(与上传一致:10 MB,文献 PDF 基本够用)
DEFAULT_MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024


def search_online(query: str, max_results: int = 5, timeout: int = 10) -> Dict:
    """
    使用 DuckDuckGo 搜索引擎进行在线搜索。
    返回搜索结果列表，每个结果包含标题、链接、摘要。
    """
    if DDGS is None:
        return {"error": "ddgs 库未安装，请运行 pip install ddgs"}

    if not query or not query.strip():
        return {"error": "查询字符串不能为空"}

    if max_results < 1:
        max_results = 1
    if max_results > 20:
        max_results = 20  # 限制最大结果数

    try:
        ddgs = DDGS(timeout=timeout)
        results = ddgs.text(query, max_results=max_results)
    except Exception as e:
        logger.exception("DuckDuckGo 搜索失败")
        return {"error": f"搜索失败: {str(e)}"}

    # 转换结果格式，确保每个结果有标准字段
    formatted_results = []
    for item in results:
        # ddgs 返回的字段可能是 body, href, title 等
        formatted_results.append({
            "title": item.get("title", ""),
            "link": item.get("href", item.get("url", "")),
            "snippet": item.get("body", item.get("snippet", "")),
        })

    return {
        "query": query,
        "total": len(formatted_results),
        "results": formatted_results,
    }


def fetch_webpage(url: str, timeout: int = 10, user_agent: Optional[str] = None) -> Dict:
    """
    获取指定 URL 的网页内容（HTML 文本）。
    适用于获取页面原始内容供 AI 分析。
    """
    if httpx is None:
        return {"error": "httpx 库未安装，请运行 pip install httpx"}

    if not url or not url.strip():
        return {"error": "URL 不能为空"}

    # 简单校验 URL 格式
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return {"error": f"无效的 URL: {url}"}

    try:
        headers = {"User-Agent": user_agent or "Symbix-Agent/1.0"}
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            # 只接受文本类内容，避免下载大二进制文件
            if "text/html" not in content_type and "text/plain" not in content_type:
                return {"error": f"不支持的内容类型: {content_type}"}

            # 返回前 10000 字符（可配置）
            content = resp.text[:10000]
            return {
                "url": url,
                "status_code": resp.status_code,
                "content_type": content_type,
                "content_preview": content,
                "full_length": len(resp.text),
                "truncated": len(resp.text) > 10000,
            }
    except httpx.TimeoutException:
        logger.warning("获取网页超时: %s", url)
        return {"error": f"请求超时（{timeout}秒）"}
    except httpx.HTTPStatusError as e:
        logger.warning("HTTP 错误 %s: %s", e.response.status_code, url)
        return {"error": f"HTTP {e.response.status_code}: {e.response.reason_phrase}"}
    except Exception as e:
        logger.exception("获取网页失败: %s", url)
        return {"error": f"获取失败: {str(e)}"}


def _safe_download_filename(url: str, headers) -> str:
    """从 URL / Content-Disposition 提取安全文件名,避免路径穿越。"""
    name = ""
    cd = (headers or {}).get("content-disposition", "") if isinstance(headers, dict) else ""
    m = re.search(r'filename\*?\s*=\s*(?:UTF-8\'\')?"?([^"\r\n;]+)"?', cd, re.I)
    if m:
        name = unquote(m.group(1).strip())
    if not name:
        path = urlparse(url).path
        name = os.path.basename(path) if path else ""
        name = unquote(name)
    if not name or name in (".", ".."):
        name = "download.bin"
    # 去除路径分隔符与危险字符,只留安全段
    name = re.sub(r"[\\/\r\n\x00]", "_", name)
    name = name.strip(". ") or "download.bin"
    return name[:160]


def download_file(url: str, filename: Optional[str] = None, timeout: int = 30,
                  max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES) -> Dict:
    """通用文件下载:把任意 URL 的响应体保存到 uploads/{session_id}/downloads/ 下。

    适用:下载 PDF / 图片 / 压缩包 / 数据集等二进制文件,之后再交给
    parse_file / doc_to_markdown 解析。不限制 Content-Type(这是下载工具
    区别于 fetch_webpage 的意义)。路径固定在会话级 downloads 沙箱内,
    文件名自动从 Content-Disposition / URL 提取,可用 filename 覆盖。
    会话 id 从 checkpoint 当前上下文读取;非对话环境回退 uploads/downloads/(共享目录)。
    """
    if httpx is None:
        return {"error": "httpx 库未安装,请运行 pip install httpx"}
    if not url or not url.strip():
        return {"error": "URL 不能为空"}
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc or parsed.scheme not in ("http", "https"):
        return {"error": f"无效的 URL(必须为 http/https): {url}"}

    try:
        from Symbix_sdk.tools.file_pipeline import get_uploads_root, is_allowed_extension, assert_path_allowed
    except Exception as e:
        return {"error": f"下载失败: 沙箱路径模块不可用: {e}"}

    headers = {"User-Agent": "Symbix-Agent/1.0"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            with client.stream("GET", url, headers=headers) as resp:
                resp.raise_for_status()
                length = int(resp.headers.get("content-length") or 0)
                if length > max_bytes:
                    return {"error": f"文件过大: {length} bytes > {max_bytes} bytes"}
                data = b""
                for chunk in resp.iter_bytes(chunk_size=64 * 1024):
                    data += chunk
                    if len(data) > max_bytes:
                        return {"error": f"文件过大(下载中止): > {max_bytes} bytes"}
                content_type = resp.headers.get("content-type", "") or "application/octet-stream"
                cd_headers = dict(resp.headers)
    except httpx.TimeoutException:
        return {"error": f"下载超时(>{timeout}秒)"}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.reason_phrase}"}
    except Exception as e:
        logger.exception("下载失败: %s", url)
        return {"error": f"下载失败: {str(e)}"}

    if not data:
        return {"error": "下载内容为空"}

    # 文件名:优先用户指定,其次 Content-Disposition,再 URL 尾部
    name = (filename or "").strip()
    if not name:
        name = _safe_download_filename(url, cd_headers)
    name = re.sub(r"[\\/\r\n\x00]", "_", name).strip(". ") or "download.bin"
    name = name[:160]

    # 扩展名不合法时兜底 octet-stream(避免 save_upload 拒绝未知扩展名)
    if not is_allowed_extension(name):
        ext = os.path.splitext(name)[1].lower()
        if not ext:
            mime_ext = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg",
                        "image/webp": ".webp", "image/gif": ".gif", "text/csv": ".csv"}
            name += mime_ext.get(content_type.split(";")[0].strip(), "")

    import uuid
    safe = re.sub(r"[^\w.\-]", "_", os.path.basename(name))[:120] or "download.bin"
    unique = f"{uuid.uuid4().hex[:10]}_{safe}"
    # 会话级目录:优先从 checkpoint 当前上下文取 session_id,
    # 使文件归属发起下载的对话,删除对话时可级联清理。
    sid = ""
    try:
        from Symbix_sdk.checkpoint import get_current
        sid = (get_current() or ("",))[0] or ""
    except Exception:
        sid = ""
    if sid:
        san = re.sub(r"[^\w\-]+", "_", sid)[:80] or "default"
        dest_dir = os.path.join(get_uploads_root(), san, "downloads")
    else:
        dest_dir = os.path.join(get_uploads_root(), "downloads")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, unique)

    try:
        resolved = assert_path_allowed(dest)
    except Exception as e:
        return {"error": f"下载失败: 路径不再沙箱内: {e}"}

    try:
        with open(resolved, "wb") as f:
            f.write(data)
    except Exception as e:
        logger.exception("写入下载文件失败: %s", url)
        return {"error": f"写入失败: {str(e)}"}

    return {
        "status": "ok",
        "path": resolved,
        "filename": os.path.basename(resolved),
        "size": len(data),
        "content_type": content_type,
        "url": url,
        "message": f"已下载: {os.path.basename(resolved)} -> {resolved} ({len(data)} bytes)",
    }



# 工具注册 Schema
WEB_TOOLS_SCHEMAS = {
    "search_online": {
        "risk_channel": "read",
        "func": search_online,
        "description": (
            "使用 DuckDuckGo 搜索引擎进行在线搜索。"
            "返回搜索结果的标题、链接和摘要。"
            "适用于需要获取最新信息或参考资料的场景。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要搜索的查询字符串。",
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回的最大搜索结果数量，默认 5，最大 20。",
                    "default": 5,
                },
                "timeout": {
                    "type": "integer",
                    "description": "请求超时时间（秒），默认 10。",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    "fetch_webpage": {
        "risk_channel": "read",
        "func": fetch_webpage,
        "description": (
            "获取指定 URL 的网页 HTML 内容（纯文本）。"
            "返回页面内容预览（最多 10000 字符），可用于分析页面结构或提取信息。"
            "读网页/查资料时的**首选**工具(比 browser_* 快且省 token);"
            "仅支持 http/https,本地文件请用 read_file 或 parse_file。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要获取的网页 URL（必须包含协议，如 http:// 或 https://）。",
                },
                "timeout": {
                    "type": "integer",
                    "description": "请求超时时间（秒），默认 10。",
                    "default": 10,
                },
                "user_agent": {
                    "type": "string",
                    "description": "自定义 User-Agent 头，默认为 Symbix-Agent/1.0。",
                },
            },
            "required": ["url"],
        },
    },
    "download_file": {
        "risk_channel": "write",
        "func": download_file,
        "description": (
            "通用文件下载:把任意 URL(http/https)的响应体保存到本地 uploads/<会话id>/downloads/ 目录。"
            "(未处于对话上下文时回退共享 uploads/downloads/。)"
            "适用于下载 PDF / 图片 / 压缩包 / 数据集等二进制文件,下载后再用 parse_file 或 doc_to_markdown 解析。"
            "不限制 Content-Type,文件名自动从 Content-Disposition 或 URL 提取,可用 filename 参数覆盖。"
            "路径固定在该会话 downloads 沙箱内,随对话删除级联清理。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要下载的 URL(必须为 http:// 或 https://)。",
                },
                "filename": {
                    "type": "string",
                    "description": "可选:保存的文件名(含扩展名)。不传时自动从 Content-Disposition / URL 提取。",
                },
                "timeout": {
                    "type": "integer",
                    "description": "请求超时时间(秒),默认 30。",
                    "default": 30,
                },
            },
            "required": ["url"],
        },
    },
}