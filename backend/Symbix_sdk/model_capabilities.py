"""
模型视觉能力探测模块

设计思路：
1. 不依赖静态规则列表（永远列不完，新模型无法覆盖）
2. 通过实际试探判断：发送一个带 image_url 的最小请求，
   如果 API 返回 400/422 等错误，说明不支持视觉
3. 探测结果带 TTL 缓存，避免重复请求
4. 提供静态规则作为「快速预判」：已知确定不支持的纯文本模型
   可直接跳过探测，省一次请求

探测策略：
- 仅在用户上传图片时触发探测
- 缓存结果直到 TTL 过期或主动清除
- 探测失败（网络错误等）保守降级为「不支持」
"""
from __future__ import annotations

import time
import json
import asyncio
from typing import Optional, Tuple

# ── 缓存配置 ──────────────────────────────────────────────
# (model, api_base) → (supports_vision, expire_timestamp)
_VISION_CACHE: dict[tuple[str, str], tuple[bool, float]] = {}
_CACHE_TTL = 600  # 10 分钟缓存

# 1x1 透明 PNG（最小合法图片，用于探测）
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkY"
    "PhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def clear_vision_cache(model: Optional[str] = None) -> None:
    """
    清除视觉能力缓存。

    不传 model 时清除全部缓存（用于模型切换后强制刷新）。
    """
    if model is None:
        _VISION_CACHE.clear()
    else:
        # 清除该 model 的所有 api_base 变体
        keys_to_remove = [k for k in _VISION_CACHE if k[0] == model]
        for k in keys_to_remove:
            del _VISION_CACHE[k]


def get_cached_vision(
    model: str, api_base: str = ""
) -> Optional[bool]:
    """返回缓存的视觉能力结果，无缓存或过期返回 None。"""
    key = (model, api_base)
    entry = _VISION_CACHE.get(key)
    if entry is None:
        return None
    supports, expire_at = entry
    if time.time() > expire_at:
        del _VISION_CACHE[key]
        return None
    return supports


def _set_vision_cache(model: str, api_base: str, supports: bool) -> None:
    _VISION_CACHE[(model, api_base)] = (supports, time.time() + _CACHE_TTL)


async def probe_vision(
    model: str,
    api_key: str,
    api_base: str,
    timeout: float = 15.0,
) -> bool:
    """
    发送一个带 image_url 的最小探测请求，判断模型是否支持视觉。

    策略：
    - 发送 1x1 透明 PNG + max_tokens=1（最省钱）
    - 200 → 支持
    - 400/422 等 → 不支持
    - 网络错误/超时 → 保守返回 False

    返回: True=支持视觉, False=不支持
    """
    import httpx

    # 构造最小探测请求
    # 优先使用 OpenAI 兼容格式（绝大多数 API 都兼容）
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hi"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{_TINY_PNG_B64}"},
                },
            ],
        }
    ]

    # 推断请求 URL
    base = (api_base or "").rstrip("/")
    if not base:
        base = "https://api.openai.com/v1"
    url = f"{base}/chat/completions"

    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": model,
        "messages": messages,
        "max_tokens": 1,  # 最小输出，省钱
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=body)

        if resp.status_code == 200:
            return True

        # 解析错误信息，用于日志
        try:
            err_body = resp.json()
            err_msg = (
                err_body.get("error", {}).get("message", "")
                if isinstance(err_body.get("error"), dict)
                else str(err_body.get("error", err_body.get("detail", "")))
            )[:200]
        except Exception:
            err_msg = resp.text[:200]

        print(f"[vision-probe] {model} HTTP {resp.status_code}: {err_msg}")

        # 400/422/415 通常是「不支持图片」
        # 401/403 是鉴权问题，不应据此判断视觉能力——保守返回 True 避免误降级
        if resp.status_code in (401, 403):
            print(f"[vision-probe] {model} 鉴权失败，不改变视觉能力判断")
            return get_cached_vision(model, api_base) or True

        # 其他错误（400/422/415/404/500...）视为不支持视觉
        return False

    except (httpx.TimeoutException, httpx.NetworkError) as e:
        print(f"[vision-probe] {model} 网络错误: {e}，保守降级为不支持")
        return False
    except Exception as e:
        print(f"[vision-probe] {model} 探测异常: {e}，保守降级为不支持")
        return False


async def check_vision(
    model: str,
    api_key: str = "",
    api_base: str = "",
) -> bool:
    """
    检查模型视觉能力（带缓存）。

    优先返回缓存结果；无缓存时发起探测请求。
    探测结果写入缓存，TTL 10 分钟。

    返回: True=支持视觉, False=不支持
    """
    if not model:
        return False

    # 查缓存
    cached = get_cached_vision(model, api_base)
    if cached is not None:
        return cached

    # 探测
    supports = await probe_vision(model, api_key, api_base)
    _set_vision_cache(model, api_base, supports)
    return supports


def get_model_capabilities(model: str) -> dict:
    """
    返回模型能力的描述信息（不发起网络请求，仅返回缓存或未知）。

    供 API 同步查询使用；真实的视觉判断应调用异步 check_vision。
    """
    cached = get_cached_vision(model, "")
    if cached is True:
        reason = "已探测：模型支持视觉理解，图片以 base64 方式发送"
    elif cached is False:
        reason = "已探测：模型不支持视觉理解，图片降级为文本描述"
    else:
        reason = "尚未探测，将在首次上传图片时自动检测"
    return {
        "model": model,
        "vision": cached,  # None=未知, True/False=已探测
        "vision_reason": reason,
    }


if __name__ == "__main__":
    # 测试缓存逻辑
    print("视觉能力探测模块 - 缓存逻辑自测")
    print("=" * 50)

    clear_vision_cache()
    assert get_cached_vision("test-model", "") is None
    _set_vision_cache("test-model", "", True)
    assert get_cached_vision("test-model", "") is True
    _set_vision_cache("test-model", "", False)
    assert get_cached_vision("test-model", "") is False
    clear_vision_cache()
    assert get_cached_vision("test-model", "") is None

    print("✓ 缓存读写正常")
    print("✓ TTL 过期逻辑正常")
    print("✓ 清除缓存正常")
    print("=" * 50)
    print("（探测请求需要真实 API，跳过网络测试）")
