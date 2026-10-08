from __future__ import annotations
import os.path as osp
import random
from typing import Any
from Symbix_sdk.config.danmaku_config import DanmakuConfigManager
from application.services.pet_action import pet_action

# 弹幕配置单例(与 routers/danmaku.py 共用同一 json)
_DANMAKU_CONFIG_PATH = osp.join(
    osp.dirname(osp.abspath(__file__)),
    "..", "..", "Symbix_sdk", "config", "danmaku_config.json",
)
danmaku_cfg = DanmakuConfigManager(_DANMAKU_CONFIG_PATH)

# ── 模板库(本地零 LLM 成本)───────────────────────────────
_DANMAKU_TEMPLATES: dict[str, list[str]] = {
    # 任务完成
    "complete": [
        "搞定啦~🎉",
        "完成!下一件想做点什么?",
        "任务完成,夸夸我!",
        "搞定,收工~",
        "完成了,轻松拿捏~",
        "叮~任务已送达!",
        "收工!要不要来点奖励?",
        "这也太顺利了吧~",
        "办妥啦,还有别的吗?",
        "完成!接下来交给你决定~",
        "搞定~效率这块我很在行!",
        "任务清零,心情舒畅~",
        "顺利收尾,给你比个心~",
        "又搞定一件,记在心里啦!",
        "完成!要不要歇一会儿?",
        "搞定,成就感+1~",
    ],
    # 出错
    "error": [
        "哎哟,卡了一下…",
        "这里出了点小问题,我调整一下~",
        "不好意思,我重新想想~",
        "唔…这次没走通,换个思路~",
        "小失误,我马上补救!",
        "出了点岔子,别急~",
        "抱歉,让我重新来一次~",
        "这一步不太顺,我绕个道~",
        "卡住了…我深呼吸一下再试~",
        "没成功,但我记住教训了!",
    ],
    # 空闲(长时间没理我)
    "idle": [
        "在想发呆的时候,要找我哦~",
        "我在这儿等你呢~",
        "要不要聊聊天?",
        "你忙你的,我守着你~",
        "安安静静的,也挺好~",
        "有点想你了~",
        "顺手喝口水吧~",
        "我在这儿看着呢,放心~",
        "要休息一下吗?我一直都在~",
        "闲着也是闲着,陪你一会儿~",
        "刚刚在想,你今天过得还好吗?",
        "默默待机中…",
        "偶尔抬头看看窗外吧~",
        "有点无聊,但你来了就不无聊~",
        "肩膀酸不酸?动一动~",
        "我在这儿,随时叫我~",
    ],
    # 早晨
    "morning": [
        "早安~新的一天也要元气满满!",
        "早上好,喝口水再开工~",
        "早呀,今天也会很顺利的~",
        "新的一天,先伸个懒腰~",
        "早上好!今天的你很好看~",
        "早安~早饭记得吃哦",
        "早,阳光正好,慢慢来~",
        "早上好,今天想做点什么?",
        "早呀,今天也要照顾好自己~",
        "早安~给你递一杯热饮~",
    ],
    # 下午
    "afternoon": [
        "下午好~要不要休息一下?",
        "太阳有点大,注意防晒哦~",
        "下午啦,起来动一动~",
        "午后容易犯困,眯一会儿?",
        "下午好,进度别太赶~",
        "来点下午茶怎么样?",
        "这个点最适合发呆了~",
        "下午好~抬头看看远处吧~",
        "慢慢来,下午还长着呢~",
        "下午好,给你揉揉肩~",
    ],
    # 晚上
    "evening": [
        "晚上好,今天辛苦啦~",
        "夜幕降临,适合说点悄悄话~",
        "晚上好~今天过得怎么样?",
        "天黑了,该好好吃一顿~",
        "晚上好,慢下来一点~",
        "夜色不错,适合散步~",
        "今天也谢谢你啦~",
        "晚上好,别把工作带到梦里~",
        "灯亮着,我在呢~",
        "晚上好~要不要聊聊天?",
    ],
    # 深夜
    "night": [
        "夜深了,早点休息~",
        "还在熬夜吗?要照顾好自己哦~",
        "夜猫子模式又开启了~",
        "该睡了,我陪你到这儿~",
        "夜深了,别硬撑哦~",
        "睡前记得放松一下~",
        "这个点还不睡,会被我念的~",
        "夜深人静,有话明天再说~",
        "早点休息,明天才有精神~",
        "困了就去睡,我守着~",
    ],
}

_pools: dict[str, list[str]] = {}
_last_pick: dict[str, str] = {}


def _draw(kind: str) -> str:
    """从该类别轮换池抽一条文案。类别不存在时返回空串。"""
    templates = _DANMAKU_TEMPLATES.get(kind) or []
    if not templates:
        return ""
    pool = _pools.get(kind)
    if not pool:
        pool = list(templates)
        random.shuffle(pool)
        # 新一轮第一次别和上一句撞上(类别文案少时尤其明显)
        last = _last_pick.get(kind)
        if len(pool) > 1 and pool[-1] == last:
            pool[-1], pool[0] = pool[0], pool[-1]
        _pools[kind] = pool
    text = pool.pop()
    _last_pick[kind] = text
    return text


def greeting_kind(hour: int) -> str | None:
    """按本地时刻返回问候类别;非问候时段返回 None。

    纯判断,不消耗文案池(供定时器先判断"该不该问候")。
    """
    if 5 <= hour < 9:
        return "morning"
    if 12 <= hour < 16:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    if 23 <= hour or hour < 4:
        return "night"
    return None


def pick_danmaku(kind: str, *, hour: int | None = None) -> str:
    """按事件类型挑选一条弹幕文案(轮换抽取,避免连续重复)。"""
    return _draw(kind)


def emit_danmaku(kind: str, *, hour: int | None = None, extra: dict | None = None) -> dict[str, Any] | None:
    """发布一条弹幕事件(type=danmaku)到桌宠 SSE 总线。

    全屏弹幕窗口订阅 /pet/events,收到 type=danmaku 即飘字。
    返回推送的事件;文案为空(如未知 kind)或总开关关闭时返回 None。
    """
    if not danmaku_cfg.cfg.enabled:
        return None
    # 空闲/问候弹幕各自独立开关
    if kind == "idle" and not danmaku_cfg.cfg.idle_enabled:
        return None
    if kind in ("morning", "afternoon", "evening", "night") and not danmaku_cfg.cfg.greeting_enabled:
        return None
    text = pick_danmaku(kind, hour=hour)
    if not text:
        return None
    ev: dict[str, Any] = {
        "type": "danmaku",
        "text": text,
        "kind": kind,
        "ts": __import__("time").time(),
    }
    if extra:
        ev["extra"] = extra
    return pet_action.publish(ev)


def emit_idle_danmaku_if_quiet(*, min_interval_s: float | None = None, hour: int | None = None) -> dict | None:
    """空闲弹幕:距上次弹幕超过间隔才发,避免刷屏。

    间隔默认取配置 idle_interval_s,可覆盖。
    """
    import time as _time
    interval = min_interval_s or float(danmaku_cfg.cfg.idle_interval_s or 600)
    now = _time.time()
    last = getattr(emit_idle_danmaku_if_quiet, "_last_ts", 0.0)
    if now - last < interval:
        return None
    emit_idle_danmaku_if_quiet._last_ts = now
    return emit_danmaku("idle", hour=hour)
