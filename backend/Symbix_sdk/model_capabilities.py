from __future__ import annotations
import asyncio
import time
from typing import Optional
from Symbix_sdk.retry_policy import is_retryable_exc, is_retryable_status, retry_delay

# (model, api_base) → (supports_vision, expire_timestamp)
_VISION_CACHE: dict[tuple[str, str], tuple[bool, float]] = {}
# (model, api_base) → (失败原因, expire_timestamp),仅用于向用户解释「为什么没探测出结果」
_VISION_REASON: dict[tuple[str, str], tuple[str, float]] = {}
_CACHE_TTL = 600
# 探测走的是普通对话接口,上游限流/5xx 很常见;失败重试几次再下结论
_PROBE_ATTEMPTS = 3

# 1x1 透明 PNG(最小合法图片,用于探测)
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkY"
    "PhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def clear_vision_cache(model: Optional[str] = None) -> None:
    """清除视觉能力缓存(不传 model 时清全部,用于切换模型后强制刷新)。"""
    if model is None:
        _VISION_CACHE.clear()
        _VISION_REASON.clear()
        return
    for store in (_VISION_CACHE, _VISION_REASON):
        for key in [k for k in store if k[0] == model]:
            del store[key]


def get_cached_vision(model: str, api_base: str = "") -> Optional[bool]:
    """返回缓存的视觉能力结果,无缓存或过期返回 None。"""
    key = (model, api_base)
    entry = _VISION_CACHE.get(key)
    if entry is None:
        return None
    supports, expire_at = entry
    if time.time() > expire_at:
        del _VISION_CACHE[key]
        return None
    return supports


def get_vision_note(model: str) -> Optional[str]:
    """返回该模型最近一次探测失败的原因(没有失败记录返回 None)。"""
    for (m, _), (reason, expire_at) in _VISION_REASON.items():
        if m == model and time.time() <= expire_at:
            return reason
    return None


def _set_vision_cache(model: str, api_base: str, supports: bool) -> None:
    _VISION_CACHE[(model, api_base)] = (supports, time.time() + _CACHE_TTL)


def _note_failure(model: str, api_base: str, reason: str) -> None:
    _VISION_REASON[(model, api_base)] = (reason, time.time() + _CACHE_TTL)


async def probe_vision(
    model: str,
    api_key: str = "",
    api_base: str = "",
    timeout: float = 15.0,
    max_attempts: int = _PROBE_ATTEMPTS,
) -> Optional[bool]:
    """
    发一个带 image_url 的最小请求,判断模型是否支持视觉。

    返回 True=支持 / False=明确不支持 / None=无法判定。

    区分「不支持」与「探测失败」很重要:上游限流(429)、5xx、网络抖动、鉴权失败
    都**不能**说明模型没有视觉能力。以前这些一律返回 False 并缓存 10 分钟,结果
    是图片没传进模型,模型只好自己去翻文件/开浏览器找图(甚至开 file:// 撞墙)。
    现在这些情况返回 None(不写缓存),下次上传图片会重新探测。
    """
    import httpx

    # 优先用 OpenAI 兼容格式(绝大多数 API 都兼容)
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

    # URL 必须与 client._resolve_endpoint 的 base 处理一致:api_base 不以 /v1 结尾
    # 时自动补 /v1,否则会打到中转站前端页面(SPA 对任意路径返回 200 HTML)。
    base = (api_base or "").rstrip("/")
    if not base:
        base = "https://api.openai.com/v1"
    if not base.endswith("/v1"):
        base = base + "/v1"
    url = f"{base}/chat/completions"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": model,
        "messages": messages,
        "max_tokens": 1,  # 最小输出,省钱
        "stream": False,
    }

    last_note = "未知错误"
    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=body)
        except Exception as e:
            if attempt < max_attempts and is_retryable_exc(e):
                delay = retry_delay(attempt)
                print(f"[vision-probe] {model} 网络错误({type(e).__name__}),{delay:.1f}s 后重试 {attempt}/{max_attempts}")
                await asyncio.sleep(delay)
                continue
            last_note = f"网络错误:{type(e).__name__}"
            break

        if resp.status_code == 200:
            # 校验响应体是真实 OpenAI JSON,不能只看状态码:中转站 SPA fallback
            # 会对任意路径返回 200 HTML,按 200 判支持会把无视觉模型误判成支持。
            ctype = (resp.headers.get("content-type") or "").lower()
            if "json" not in ctype:
                print(f"[vision-probe] {model} 200 但 content-type={ctype or '?'} 非 JSON,按不支持处理")
                return False
            try:
                j = resp.json()
            except Exception:
                print(f"[vision-probe] {model} 200 但响应体解析失败,按不支持处理")
                return False
            if not isinstance(j, dict) or ("choices" not in j and "object" not in j):
                print(f"[vision-probe] {model} 200 但响应体不是 OpenAI 格式,按不支持处理")
                return False
            if isinstance(j.get("error"), dict):
                print(f"[vision-probe] {model} 200 但响应带 error 字段,按不支持处理")
                return False
            return True

        last_note = f"HTTP {resp.status_code}"
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

        # 400/413/415/422 = 上游明确拒绝图片载荷,可以断言「不支持视觉」
        if resp.status_code in (400, 413, 415, 422):
            return False

        if attempt < max_attempts and is_retryable_status(resp.status_code):
            delay = retry_delay(attempt, resp.headers.get("retry-after"))
            print(f"[vision-probe] {model} HTTP {resp.status_code},{delay:.1f}s 后重试 {attempt}/{max_attempts}")
            await asyncio.sleep(delay)
            continue
        break

    print(f"[vision-probe] {model} {last_note},无法判定视觉能力(不缓存,下次重新探测)")
    _note_failure(model, api_base, last_note)
    return None


async def resolve_vision(
    model: str,
    api_key: str = "",
    api_base: str = "",
) -> Optional[bool]:
    """探测并缓存视觉能力,返回 True/False/None(无法判定,不写缓存)。"""
    cached = get_cached_vision(model, api_base)
    if cached is not None:
        return cached
    supports = await probe_vision(model, api_key, api_base)
    if supports is not None:
        _set_vision_cache(model, api_base, supports)
    return supports


async def check_vision(
    model: str,
    api_key: str = "",
    api_base: str = "",
) -> bool:
    """
    检查模型视觉能力(带缓存),只回 bool 供调用方决定是否传图。

    探测失败(限流/网络)时本次保守按「不支持」处理,但不写缓存,
    下次上传图片会重新探测——避免一次 429 把模型「判瞎」10 分钟。
    """
    if not model:
        return False
    return (await resolve_vision(model, api_key, api_base)) is True


def get_model_capabilities(model: str) -> dict:
    """
    返回模型能力描述(不发网络请求),供前端查询。

    缓存里可能存的是别的 api_base 下的判定结果,所以按 model 扫一遍,
    避免「后端其实已探测过、前端却显示未探测」。
    """
    cached = None
    for (m, _), (supports, expire_at) in _VISION_CACHE.items():
        if m == model and time.time() <= expire_at:
            cached = supports
            break

    if cached is True:
        reason = "已探测:模型支持视觉理解,图片以 base64 方式发送"
    elif cached is False:
        reason = "已探测:模型不支持视觉理解,图片降级为文字描述"
    else:
        note = get_vision_note(model)
        reason = (
            f"上次探测未得出结论({note}),下次上传图片时自动重试"
            if note
            else "尚未探测,将在首次上传图片时自动检测"
        )
    return {"model": model, "vision": cached, "vision_reason": reason}


if __name__ == "__main__":
    print("视觉能力探测模块 - 缓存逻辑自测")
    clear_vision_cache()
    assert get_cached_vision("test-model", "") is None
    _set_vision_cache("test-model", "", True)
    assert get_cached_vision("test-model", "") is True
    assert get_model_capabilities("test-model")["vision"] is True
    _set_vision_cache("test-model", "https://x", False)
    assert get_model_capabilities("test-model")["vision"] is False
    clear_vision_cache()
    assert get_cached_vision("test-model", "") is None
    _note_failure("test-model", "", "HTTP 429")
    assert "429" in get_model_capabilities("test-model")["vision_reason"]
    clear_vision_cache()
    assert get_model_capabilities("test-model")["vision"] is None
    print("✓ 缓存读写 / 跨 api_base 查询 / 失败原因 / 清除 均正常")
