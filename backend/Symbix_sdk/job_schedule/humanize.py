"""定时任务的「人话」时间解析与回显。

目标:让用户(和模型)用自然说法描述时间,不必手写 cron:
    每天 9:00 / 每周一三五 8:30 / 每月 1 号 9 点 / 每 2 小时 / 30 分钟后 / 工作日 9:00

对外三个函数:
    parse_schedule(text)      → {"trigger_type", "trigger_config"}  (失败抛 ValueError,带可读提示)
    describe_trigger(tt,cfg)  → "每天 09:00" 这样的中文回显(面板/工具返回值共用)
    next_run_times(tt,cfg,n)  → 接下来 n 次触发时间(ISO 串),给面板做「下次运行」预览

注意 weekday 编号:APScheduler 的 cron 里 0=周一 … 6=周日(与系统 crontab 的 0=周日不同),
本模块统一按 APScheduler 口径,并额外接受 mon/tue/… 与 一/二/…/日 写法。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

# ── 词表 ──────────────────────────────────────────────────────────────
_WEEKDAY_CN = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6, "七": 6}
_WEEKDAY_EN = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_WEEKDAY_LABEL = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "两": 2, "二": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

_UNIT_ALIASES = [
    (("秒钟", "秒"), "seconds"),
    (("分钟", "分"), "minutes"),
    (("小时", "钟头", "个小时"), "hours"),
    (("天", "日"), "days"),
    (("周", "星期", "个礼拜"), "weeks"),
]
_UNIT_LABEL = {"seconds": "秒", "minutes": "分钟", "hours": "小时", "days": "天", "weeks": "周"}
_EN_UNITS = {"second": "seconds", "seconds": "seconds", "minute": "minutes", "minutes": "minutes",
             "hour": "hours", "hours": "hours", "day": "days", "days": "days",
             "week": "weeks", "weeks": "weeks"}

# 「只跑一次」的相对说法:30分钟后 / 2小时后 / in 15 minutes
_REL_DELTA = re.compile(
    r"(?:in\s+)?(\d+)\s*(" + "|".join(_EN_UNITS) + r"|秒钟|秒|分钟|分|小时|钟头|天|日|周|星期)"
    r"\s*(?:后|later|from now)?"
)
# 绝对时间:2026-10-05 09:00 / 10-05 09:00 / 2026/10/05 9:00
_RE_ABS_DATE = re.compile(
    r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?"
)
# 时钟:9:00 / 9点 / 9点30 / 9点30分 / 9 时
_RE_CLOCK = re.compile(r"(\d{1,2})\s*(?:[:：]|点|时)\s*(\d{1,2})?\s*分?")
# 5 段 cron 表达式
_RE_CRON5 = re.compile(r"^[\d*\-,/ ]+$")


def _cn_num(text: str) -> Optional[int]:
    """中文数字 → int(支持 十/十五/二十/三十 这类)。无法解析返回 None。"""
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if "十" in text:
        head, _, tail = text.partition("十")
        tens = _CN_DIGITS.get(head, 1) if head else 1
        ones = _CN_DIGITS.get(tail, 0) if tail else 0
        return tens * 10 + ones
    if len(text) == 1 and text in _CN_DIGITS:
        return _CN_DIGITS[text]
    return None


def _parse_number(text: str) -> Optional[int]:
    """取一个数:阿拉伯数字或中文数字。"""
    m = re.search(r"\d+", text)
    if m:
        return int(m.group())
    m = re.search(r"[零〇一两二三四五六七八九十]+", text)
    if m:
        return _cn_num(m.group())
    return None
def _parse_weekdays(spec: str) -> Optional[str]:
    """星期写法 → cron day_of_week 值('1-5' / '0,2,4')。无法解析返回 None。"""
    spec = (spec or "").strip().lower()
    if not spec:
        return None
    if spec in ("工作日", "weekday", "weekdays", "workday", "workdays"):
        return "1-5"
    if spec in ("周末", "weekend", "weekends"):
        return "5,6"
    if re.fullmatch(r"[0-6](?:-[0-6])?(?:,[0-6](?:-[0-6])?)*", spec):
        return spec
    parts = [p for p in re.split(r"[,\s、]+|[和与及]|and", spec) if p]
    if parts and all(p in _WEEKDAY_EN for p in parts):
        return ",".join(str(d) for d in sorted({_WEEKDAY_EN[p] for p in parts}))
    # 中文写法:「三、周五」「周一和周三」→ 去掉 周/星期/礼拜 与分隔词后逐字取
    body = re.sub(r"(?:周|星期|礼拜)|[和与及、,，\s]|and", "", spec)
    days = sorted({_WEEKDAY_CN[ch] for ch in body if ch in _WEEKDAY_CN})
    if days:
        return ",".join(str(d) for d in days)
    return None


def _weekday_tail(low: str) -> Optional[str]:
    """取「每周/每星期/每礼拜/weekly」后面紧跟的那一段星期写法(空格/钟点前为止)。"""
    m = re.search(r"(?:每(?:个)?周|每星期|每礼拜|weekly)\s*([^\s]+)", low)
    if not m:
        return None
    return m.group(1)


def _parse_clock(text: str) -> Optional[tuple]:
    """从文本里取 (hour, minute)。支持「下午3点」「晚上8点」「中午」「午夜」等修饰。"""
    if "中午" in text and not _RE_CLOCK.search(text):
        return 12, 0
    if "午夜" in text and not _RE_CLOCK.search(text):
        return 0, 0
    m = _RE_CLOCK.search(text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    if minute > 59 or hour > 24:
        return None
    # 下午/晚上/傍晚 后若仍是 12 小时制 → +12;上午/早上/凌晨 保持
    pm = any(k in text for k in ("下午", "晚上", "傍晚", "夜里", "夜间", "pm", "PM"))
    if pm and hour < 12:
        hour += 12
    if hour == 24:
        hour = 0
    return hour, minute


def _cron_cfg(minute: str = "*", hour: str = "*", day: str = "*",
              month: str = "*", day_of_week: str = "*") -> dict:
    """补齐 5 段(面板与校验都按整段处理,缺省即 '*')。"""
    return {"minute": minute, "hour": hour, "day": day,
            "month": month, "day_of_week": day_of_week}


def _hhmm(hour: int, minute: int) -> tuple:
    return f"{hour:d}", f"{minute:d}"


def parse_schedule(text: str) -> dict:
    """把「人话时间」解析成 trigger。失败抛 ValueError(中文可读原因)。

    支持(大小写/中英混写均可):
      - 间隔: 每 30 分钟 / 每2小时 / 每半小时 / 每天 / every 3 hours
      - 每天: 每天 9:00 / 每天早上8点30 / 每日 21:00
      - 每周: 每周一 8:30 / 每周一三五 9:00 / 工作日 9:00 / 周末 10点 / weekly mon,wed 08:30
      - 每月: 每月1号 9:00 / 每月15日 12:00 / 每月最后一天 9:00 / monthly 1 09:00
      - 一次: 2026-10-05 09:00 / 明天 9:00 / 30分钟后 / in 2 hours
      - cron: 0 9 * * 1-5 或 cron: 0 9 * * 1-5
    """
    raw = (text or "").strip()
    if not raw:
        raise ValueError("时间不能为空,例如:每天 9:00 / 每 2 小时 / 每周一 8:30")
    t = raw.replace("：", ":").replace("，", ",").replace("、", ",").replace("　", " ")
    t = re.sub(r"\s+", " ", t)
    low = t.lower()

    # 1) 显式 cron
    if low.startswith("cron:"):
        return {"trigger_type": "cron", "trigger_config": _parse_raw_cron(t.split(":", 1)[1])}
    if low.startswith("cron "):
        return {"trigger_type": "cron", "trigger_config": _parse_raw_cron(t[4:])}

    # 2) 裸 5 段 cron 表达式(只含数字与 * , - / 且正好 5 段)
    if _RE_CRON5.match(t) and len(t.split()) == 5:
        return {"trigger_type": "cron", "trigger_config": _parse_raw_cron(t)}

    # 3) 相对延时 → 只跑一次:30分钟后 / in 2 hours(「每 30 分钟」不在此列)
    if not re.match(r"^(每|每隔|every)", low):
        rel = _REL_DELTA.search(low)
        if rel and any(k in low for k in ("后", "later", "from now", "in ")):
            delta = _delta_from_unit(int(rel.group(1)), rel.group(2))
            when = datetime.now() + delta
            return {"trigger_type": "date", "trigger_config": {"run_date": when.isoformat(timespec="seconds")}}

    # 4) 绝对日期 → 只跑一次
    m = _RE_ABS_DATE.search(t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        clock = (int(m.group(4)), int(m.group(5))) if m.group(4) else _parse_clock(t) or (9, 0)
        try:
            when = datetime(y, mo, d, clock[0], clock[1])
        except ValueError as e:
            raise ValueError(f"日期不合法: {m.group(0)} ({e})")
        return {"trigger_type": "date", "trigger_config": {"run_date": when.isoformat(timespec="seconds")}}

    # 5) 明天/后天/今天 [+ 时间] → 只跑一次
    day_offset = None
    for kw, off in (("后天", 2), ("明天", 1), ("tomorrow", 1), ("today", 0), ("今天", 0)):
        if kw in low:
            day_offset = off
            break
    if day_offset is not None:
        clock = _parse_clock(t) or (9, 0)
        base = datetime.now() + timedelta(days=day_offset)
        when = base.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
        if when <= datetime.now():
            when += timedelta(days=1)
        return {"trigger_type": "date", "trigger_config": {"run_date": when.isoformat(timespec="seconds")}}

    clock = _parse_clock(t)
    # 6) 每月
    m = re.search(r"(?:每(?:个)?月|每月|monthly)", low)
    if m:
        day_spec = "*"
        if "最后一天" in low or "月末" in low or "last" in low:
            day_spec = "last"
        else:
            day = re.search(r"(\d{1,2}|[零〇一两二三四五六七八九十]+)\s*(?:号|日)", t)
            if day:
                day_spec = str(_parse_number(day.group(1)))
            elif "monthly" in low:
                num = re.search(r"(\d{1,2})", low.split("monthly", 1)[1])
                if num:
                    day_spec = num.group(1)
        hour, minute = _hhmm(*clock) if clock else ("9", "0")
        return {"trigger_type": "cron", "trigger_config": _cron_cfg(minute, hour, day_spec)}

    # 7) 每周 / 工作日 / 周末
    if re.search(r"(每(?:个)?周|每星期|每礼拜|weekly|weekday|workday|weekend|周末|工作日)", low):
        dow = None
        tail = _weekday_tail(low)
        if tail:
            dow = _parse_weekdays(tail)
        if not dow and ("工作日" in low or "weekday" in low or "workday" in low):
            dow = "1-5"
        if not dow and ("周末" in low or "weekend" in low):
            dow = "5,6"
        if not dow:
            # 整句里扫一遍「周X/星期X」出现过的星期字(如「每周的周一和周三」)
            runs = re.findall(r"(?:周|星期|礼拜)([一二三四五六日天七]+)", t)
            if runs:
                dow = _parse_weekdays("".join(runs))
        if dow:
            hour, minute = _hhmm(*clock) if clock else ("9", "0")
            return {"trigger_type": "cron", "trigger_config": _cron_cfg(minute, hour, "*", "*", dow)}
        # 「每星期」这种没说具体哪天、也没给钟点的 → 按 7 天间隔
        if not clock:
            return {"trigger_type": "interval", "trigger_config": {"weeks": 1}}
        raise ValueError("每周没看懂是哪天,试试:每周一 8:30 / 每周一三五 9:00 / 工作日 9:00")

    # 8) 每天(有钟点 → 每天定时;无钟点 → 24 小时间隔)
    if re.search(r"(每天|每日|天天|daily|every day)", low):
        if clock:
            hour, minute = _hhmm(*clock)
            return {"trigger_type": "cron", "trigger_config": _cron_cfg(minute, hour)}
        return {"trigger_type": "interval", "trigger_config": {"days": 1}}

    # 9) 间隔:「每 N 单位」/「每半小时」/「每 30 分钟」/「every 2 hours」
    interval = _parse_interval(low)
    if interval:
        return {"trigger_type": "interval", "trigger_config": interval}

    # 10) 只有钟点(如「9:00」)→ 每天
    if clock:
        hour, minute = _hhmm(*clock)
        return {"trigger_type": "cron", "trigger_config": _cron_cfg(minute, hour)}

    raise ValueError(
        "没看懂这个时间,可用的写法:每天 9:00 / 每天早上8点 / 每周一三五 8:30 / "
        "工作日 9:00 / 每月1号 9:00 / 每 30 分钟 / 每 2 小时 / 30分钟后 / "
        "2026-10-05 09:00 / cron: 0 9 * * 1-5"
    )


def _parse_raw_cron(text: str) -> dict:
    """解析 5 段 cron;支持 min hour day month dow。"""
    parts = (text or "").strip().split()
    if len(parts) == 6:  # 容忍带秒的写法(丢掉秒那一段)
        parts = parts[1:]
    if len(parts) != 5:
        raise ValueError("cron 需要 5 段:分 时 日 月 星期,例如 0 9 * * 1-5")
    minute, hour, day, month, dow = parts
    from .schema import validate_trigger
    cfg = _cron_cfg(minute, hour, day, month, dow)
    try:
        validate_trigger("cron", cfg)
    except ValueError as e:
        raise ValueError(f"cron 不合法: {e}")
    return cfg


def _delta_from_unit(num: int, unit_word: str) -> timedelta:
    unit_word = unit_word.lower()
    if unit_word in _EN_UNITS:
        key = _EN_UNITS[unit_word]
    else:
        key = next((k for aliases, k in _UNIT_ALIASES if unit_word in aliases), "minutes")
    return timedelta(**{key: num})


def _parse_interval(low: str) -> Optional[dict]:
    """「每 N 单位」「每半小时」「every N units」→ interval config。"""
    if "半小时" in low or "half an hour" in low or "half hour" in low:
        return {"minutes": 30}
    if "一刻钟" in low:
        return {"minutes": 15}
    m = re.search(r"每\s*(?:隔\s*)?(\d+|[零〇一两二三四五六七八九十]+)\s*"
                  r"(秒钟|秒|分钟|分|小时|钟头|天|日|周|星期|个礼拜)", low)
    if m:
        num = _parse_number(m.group(1))
        unit = next((k for aliases, k in _UNIT_ALIASES if m.group(2) in aliases), "minutes")
        if num and num > 0:
            return {unit: num}
    m = re.search(r"every\s+(\d+)?\s*(" + "|".join(_EN_UNITS) + r")", low)
    if m:
        num = int(m.group(1)) if m.group(1) else 1
        return {_EN_UNITS[m.group(2)]: num}
    # 每单位(无数字):每小时 / 每天 / 每周 / 每分钟
    m = re.search(r"每\s*(秒钟|秒|分钟|分|小时|钟头|天|日|周|星期)", low)
    if m:
        unit = next((k for aliases, k in _UNIT_ALIASES if m.group(1) in aliases), "hours")
        return {unit: 1}
    if re.fullmatch(r"\s*every\s+(minute|hour|day|week|second)\s*", low):
        return {_EN_UNITS[low.strip().split()[-1]]: 1}
    return None


# ── 回显 ──────────────────────────────────────────────────────────────

def _two(value) -> str:
    try:
        return f"{int(value):02d}"
    except (TypeError, ValueError):
        return str(value)


def _dow_label(dow: str) -> str:
    """cron day_of_week → 「周一、三、五」/「工作日」/「周末」。"""
    s = (dow or "*").strip().lower()
    if s in ("1-5",):
        return "工作日"
    if s in ("5,6", "6,5"):
        return "周末"
    label_map = {"mon": "周一", "tue": "周二", "wed": "周三", "thu": "周四",
                 "fri": "周五", "sat": "周六", "sun": "周日"}
    out = []
    for part in re.split(r"[,\s]+", s):
        if not part:
            continue
        if part in label_map:
            out.append(label_map[part])
        elif re.fullmatch(r"[0-6]", part):
            idx = int(part)
            out.append(_WEEKDAY_LABEL[idx] if 0 <= idx < 7 else part)
        elif re.fullmatch(r"[0-6]-[0-6]", part):
            a, b = (int(x) for x in part.split("-"))
            out.append("、".join(_WEEKDAY_LABEL[i] for i in range(a, b + 1) if 0 <= i < 7))
        else:
            out.append(part)
    return "、".join(out) if out else "*"


def describe_trigger(trigger_type: str, cfg: dict) -> str:
    """trigger → 中文一句话,如「每天 09:00」「每 2 小时」「每周一、三 08:30」。"""
    cfg = cfg or {}
    if trigger_type == "interval":
        for key in ("seconds", "minutes", "hours", "days", "weeks"):
            if cfg.get(key):
                return f"每 {cfg[key]} {_UNIT_LABEL[key]}"
        return "间隔任务"
    if trigger_type == "date":
        rd = cfg.get("run_date")
        try:
            when = datetime.fromisoformat(str(rd))
            return f"只跑一次:{when:%Y-%m-%d %H:%M}"
        except (TypeError, ValueError):
            return f"只跑一次:{rd}"
    if trigger_type != "cron":
        return f"{trigger_type}: {cfg}"

    minute = cfg.get("minute", "*")
    hour = cfg.get("hour", "*")
    day = cfg.get("day", "*")
    month = cfg.get("month", "*")
    dow = cfg.get("day_of_week", "*")
    clock_known = re.fullmatch(r"\d{1,2}", str(hour)) and re.fullmatch(r"\d{1,2}", str(minute))
    time_part = f"{_two(hour)}:{_two(minute)}" if clock_known else ""

    if dow != "*":
        dow_txt = _dow_label(dow)
        return f"{dow_txt} {time_part}".strip()
    if day != "*":
        day_txt = "每月最后一天" if str(day) == "last" else f"每月 {day} 号"
        return f"{day_txt} {time_part}".strip()
    if month != "*":
        return f"cron: {minute} {hour} {day} {month} {dow}"
    if clock_known:
        return f"每天 {time_part}"
    return f"cron: {minute} {hour} {day} {month} {dow}"


def next_run_times(trigger_type: str, cfg: dict, count: int = 3) -> list[str]:
    """接下来 count 次触发时间(ISO 串)。配置非法时抛 ValueError。"""
    from .scheduler import build_trigger  # 延迟 import,避免与 scheduler 循环依赖

    trigger = build_trigger(trigger_type, cfg)
    out: list[str] = []
    now = datetime.now().astimezone()
    prev = None
    cursor = now
    for _ in range(max(1, min(int(count or 3), 10))):
        nxt = trigger.get_next_fire_time(prev, cursor)
        if nxt is None:
            break
        # DateTrigger 对「已经过去的时刻」仍会返回原值(它不跟 now 比),
        # 这里过滤掉过期时刻,避免面板把过期一次性任务显示成「下次运行」。
        if nxt <= now:
            break
        out.append(nxt.isoformat(timespec="seconds"))
        prev, cursor = nxt, nxt
    return out
