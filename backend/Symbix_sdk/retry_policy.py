"""上游调用重试策略(流式对话 / 子 Agent / 非流式聚合共用)。

上游中转网关不稳时有三类故障,以前只有第一类有重试:

1. 流中途断掉(`RemoteProtocolError` / `ReadError` / `ReadTimeout` / `ConnectError`)—— `client.py` 原有 2 次重试;
2. 直接回 429 / 5xx(限流、网关过载、瞬时 502)—— **以前直接判失败**,子 Agent 一次 429 就整路废;
3. Anthropic / Gemini 两条 SSE 管道 —— **以前完全没有重试**(只有 OpenAI 兼容那条有)。

本模块只放「要不要重试 / 等多久」的纯函数,不做任何 IO,方便单测。
"""

import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import httpx

RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

# 可重试的传输层异常(含超时与连接池耗尽)。
RETRYABLE_EXCEPTIONS = (
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.ProtocolError,
)

# 默认重试次数(总尝试次数 = DEFAULT_MAX_RETRIES + 1)。
# 取 3 而不是 2:实测本项目常用的中转网关单次尝试失败率可达 30%~60%
# (回 429 bad_response_status_code 或直接掐断连接),重试 2 次的整次失败率仍有 ~3%,重试 3 次降到 ~1%。
DEFAULT_MAX_RETRIES = 3

# 退避参数:第 1 次约 1.5s、第 2 次约 3s、第 3 次约 4.5s,加抖动避免并发请求同时回来再撞限流。
_BACKOFF_BASE = 1.5
_BACKOFF_CAP = 10.0
_BACKOFF_JITTER = 0.35
# 上游 Retry-After 给得太离谱(比如 600s)时不干等,超过这个上限就按自己的退避走。
_RETRY_AFTER_CAP = 30.0


def is_retryable_status(status: int) -> bool:
    """HTTP 状态码是否值得重试。"""
    return status in RETRYABLE_STATUS


def is_retryable_exc(exc: BaseException) -> bool:
    """异常是否值得重试(传输层中断/超时)。"""
    return isinstance(exc, RETRYABLE_EXCEPTIONS)


def retry_after_seconds(raw: str | None) -> float | None:
    """解析上游的 `Retry-After` 响应头(秒数或 HTTP 日期),拿不到或超上限返回 None。"""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        try:
            when = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if when is None:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        seconds = (when - datetime.now(timezone.utc)).total_seconds()
    if seconds <= 0:
        return None
    return min(seconds, _RETRY_AFTER_CAP)


def backoff_seconds(attempt: int, base: float = _BACKOFF_BASE, cap: float = _BACKOFF_CAP) -> float:
    """指数退避 + 抖动。attempt 从 0 开始(第 1 次重试前调用)。"""
    delay = min(base * (2 ** max(0, attempt)), cap)
    return round(delay * (1 + random.uniform(0, _BACKOFF_JITTER)), 3)


def retry_delay(attempt: int, retry_after: str | None = None) -> float:
    """下一次重试前等多久:优先听上游的 Retry-After,否则用自己的退避。"""
    parsed = retry_after_seconds(retry_after)
    return parsed if parsed is not None else backoff_seconds(attempt)


def reset_reason(exc: BaseException | None = None, status: int | None = None) -> str:
    """给前端/日志看的一行短原因(别把上游几百字错误体塞进来)。"""
    if status is not None:
        return f"HTTP {status}"
    if exc is not None:
        return f"{type(exc).__name__}: {exc}"
    return "未知原因"
