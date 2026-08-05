"""
Web 工具：搜索、抓取网页等
"""

import logging
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None

try:
    import httpx
except ImportError:
    httpx = None

logger = logging.getLogger(__name__)


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


# 工具注册 Schema
WEB_TOOLS_SCHEMAS = {
    "search_online": {
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
        "func": fetch_webpage,
        "description": (
            "获取指定 URL 的网页 HTML 内容（纯文本）。"
            "返回页面内容预览（最多 10000 字符），可用于分析页面结构或提取信息。"
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
}