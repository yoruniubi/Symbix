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

# 路由抖动(no_route / 无可用渠道)专用退避:亚秒级。
#
# 理由:这类故障是上游负载均衡层的瞬时抖动,毫秒级就会恢复 —— 实测失败后
# 立刻重试几乎都能拿到 200。用上面的秒级退避纯属白等:一次请求撞 3 次
# no_route 就要空等 1.5+3+4.5 ≈ 9s,这就是用户感知到的「响应慢」。
# 而真正限流(429 且带 Retry-After)仍然走完整退避,不会把上游打死。
_ROUTE_FLAP_BACKOFF_BASE = 0.25
_ROUTE_FLAP_BACKOFF_CAP = 1.0


def is_route_flap_body(body: str) -> bool:
    """上游错误体是否表明「路由瞬时抖动」(模型没路由到,但马上会恢复)。

    跟 `is_non_retryable_body` 是互补关系:那些是确定性判定(不值得重试),
    而这里是**值得重试、但不该按秒级退避**的那类。

    Args:
        body: 上游返回的错误正文

    Returns:
        True 表示应当快速重试
    """
    if not body:
        return False
    low = body.lower()
    return any(m in low for m in _ROUTE_FLAP_MARKERS)


def is_retryable_status(status: int) -> bool:
    """HTTP 状态码是否值得重试。"""
    return status in RETRYABLE_STATUS


# 错误体里出现这些标记时,无论状态码是多少都不重试。
# 这些是上游的**业务判定**(内容审核/账号状态/模型不存在),不是临时故障,
# 重试只会让用户多等十几秒然后拿到同样的结果。
_NON_RETRYABLE_MARKERS = (
    "moderation_blocked",     # 内容审核拦截
    "moderation_error",
    "smart moderation blocked",
    "content_policy",
    "content_filter",
    "insufficient_quota",     # 额度耗尽
    "invalid_api_key",        # 密钥无效
    "model_not_found",        # 模型不存在
    "does not exist",         # 模型/资源不存在
    "unauthorized",
)

# 路由层瞬时故障的标记。**注意:这些必须保留重试**,不能归入上面的
# `_NON_RETRYABLE_MARKERS`。
#
# 实测数据(某中转站 deepseek-v4.1-flash,12 组无退避连测):
#   no_route 成阵发出现 —— 爆发时连打十几条,但 12 组里有 11 组
#   首次就成功,且失败后「立刻」重试基本都能拿到 200。
# 说明它是上游负载均衡层的毫秒级抖动,不是确定性结论。
# 归入不重试会直接打死 30%~60% 本来可用的请求。
# 真正需要改的是**退避时长**(见 _BACKOFF_BASE),而不是是否重试。
_ROUTE_FLAP_MARKERS = (
    "no_route",
    "no visible model id",
    "no available channel",
)


# 内容审核拦截专用的子集。跟 _NON_RETRYABLE_MARKERS 分开是有意的:
# 额度耗尽/密钥无效这类重试一万次也没用,而审核拦截是**概率性误判**
# (上游 hashlinear_model 置信度常压着阈值走),值得换一份输入重试。
_MODERATION_MARKERS = (
    "moderation_blocked",
    "moderation_error",
    "smart moderation blocked",
)


def is_moderation_block_body(body: str) -> bool:
    """上游错误体是否表明「被内容审核拦了」。

    这类拦截对同样的输入通常会稳定复现,但换一份输入(比如丢掉摘要、
    只留最近几轮对话)往往就能过 —— 所以调用方应当降级重试,而不是
    像额度耗尽那样直接失败。

    Args:
        body: 上游返回的错误正文

    Returns:
        True 表示这是内容审核拦截
    """
    if not body:
        return False
    low = body.lower()
    return any(m in low for m in _MODERATION_MARKERS)


def is_non_retryable_body(body: str) -> bool:
    """上游错误体是否表明「重试也没用」。

    Args:
        body: 上游返回的错误正文(JSON 或 HTML 均可)

    Returns:
        True 表示这是业务判定错误,应当立刻失败而不是重试
    """
    if not body:
        return False
    low = body.lower()
    # 429 的 HTML 限流页是例外:那是真限流,值得退避重试,
    # 不会命中下面这些标记,所以不需要额外排除。
    return any(m in low for m in _NON_RETRYABLE_MARKERS)


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


def route_flap_delay(attempt: int) -> float:
    """路由抖动专用的亚秒级退避。attempt 从 0 开始。"""
    delay = min(_ROUTE_FLAP_BACKOFF_BASE * (2 ** max(0, attempt)), _ROUTE_FLAP_BACKOFF_CAP)
    return round(delay * (1 + random.uniform(0, _BACKOFF_JITTER)), 3)


def retry_delay(attempt: int, retry_after: str | None = None,
                body: str | None = None) -> float:
    """下一次重试前等多久。

    优先级:上游 Retry-After > 路由抖动的亚秒级退避 > 常规指数退避。

    Args:
        attempt: 已尝试次数(从 0 开始)
        retry_after: 上游 `Retry-After` 响应头
        body: 上游错误正文。命中路由抖动时改用亚秒级退避

    Returns:
        需要等待的秒数
    """
    parsed = retry_after_seconds(retry_after)
    if parsed is not None:
        return parsed
    if body and is_route_flap_body(body):
        return route_flap_delay(attempt)
    return backoff_seconds(attempt)


def reset_reason(exc: BaseException | None = None, status: int | None = None) -> str:
    """给前端/日志看的一行短原因(别把上游几百字错误体塞进来)。"""
    if status is not None:
        return f"HTTP {status}"
    if exc is not None:
        return f"{type(exc).__name__}: {exc}"
    return "未知原因"
