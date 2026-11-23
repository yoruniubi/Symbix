"""
「内容审核拦截导致上游请求被打爆」的回归测试。

运行: F:/nvm/v24.19.0/node.exe 与 python 无关 —— 这是 python 测试，用
`/mnt/e/Anaconda/envs/Symbix/python.exe tests/test_moderation_no_storm.py`

为什么值得单独测:
实测日志里,一次用户提问会在**同一秒内**向网关连打 2~3 次请求:

    [OpenAI] HTTP 500: ...Smart moderation blocked... (confidence: 0.780)
    [OpenAI] HTTP 500: ...Smart moderation blocked... (confidence: 0.780)   ← 同一条,立刻重发
    [stream] 命中内容审核,丢掉摘要降级重试(22 → 20 条消息)
    [OpenAI] HTTP 500: ...Smart moderation blocked... (confidence: 0.816)
    [OpenAI] HTTP 500: ...Smart moderation blocked... (confidence: 0.816)

原因是有三层调用叠在一起,而**后两层完全没有退避**:
  1. `_stream_with_retry` —— 正确:审核是业务判定,不重试;
  2. `chat_stream` 的 moderation 降级 —— 丢掉 system 摘要后**立刻**重发;
  3. `ChatWindow` 对应的主循环 —— 这一轮失败后,下一轮又发一次。

叠起来就把网关的 RPM 打满,回 `all candidate channels are locally rate
limited`,把本来正常的请求也一起拖死。

这个测试锁住三件事:
  · 降级重试必须退避(不能在同一秒连发);
  · 降级最多只做一次(不能反复降级);
  · 主循环识别出审核后必须立刻收尾,不再开新一轮。
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(r'F:/Symbix/backend')
CLIENT = ROOT / 'Symbix_sdk/client.py'
STREAM = ROOT / 'application/routers/chat/stream.py'

failed = 0


def check(name: str, cond: bool, detail: str = '') -> None:
    global failed
    if cond:
        print(f'  ok   {name}')
    else:
        print(f'  FAIL {name}' + (f' — {detail}' if detail else ''))
        failed += 1


def main() -> int:
    src_client = CLIENT.read_text(encoding='utf-8')
    src_stream = STREAM.read_text(encoding='utf-8')

    print('内容审核不再引发请求风暴')

    # ── 1) 两个文件语法必须没问题（改动都是控制流，语法错就白改） ──────
    for path, src in ((CLIENT, src_client), (STREAM, src_stream)):
        try:
            ast.parse(src)
            ok = True
            err = ''
        except SyntaxError as e:  # pragma: no cover
            ok, err = False, f'{e.lineno}: {e.msg}'
        check(f'{path.name} 语法正确', ok, err)

    # ── 2) 降级重试前必须有 sleep ──────────────────────────────────
    # 定位 chat_stream 里那段「命中内容审核…降级重试」
    m = re.search(
        r'命中内容审核,丢掉摘要降级重试.*?(?=\n    # ──)',
        src_client,
        re.S,
    )
    check('找到 moderation 降级重试代码块', m is not None)
    block = m.group(0) if m else ''

    check(
        '降级重试前有退避 sleep',
        'await asyncio.sleep(' in block,
        '没有 sleep 就会在同一秒连发，打满 RPM',
    )
    check(
        '退避用的是 retry_delay（带抖动）而不是硬编码 0',
        'retry_delay(' in block,
    )

    # ── 3) 降级只做一次 ──────────────────────────────────────────
    check(
        '降级只做一次（moderation_retried 标志）',
        'moderation_retried' in src_client,
    )
    # 只允许一个「再开 _open_stream」的降级调用点
    degrade_calls = len(re.findall(r'async for evt2 in self\._open_stream', src_client))
    check('降级重发只有一个调用点', degrade_calls == 1, f'实际 {degrade_calls} 个')

    # ── 4) 主循环识别审核并直接 break ────────────────────────────
    check(
        '有 _is_moderation_round_error 判定函数',
        'def _is_moderation_round_error(' in src_stream,
    )
    check(
        '主循环遇到审核直接 break（不再开新一轮）',
        re.search(
            r'if moderation_blocked:\s*\n\s*print\(.*?内容审核.*?\)\s*\n\s*break',
            src_stream,
        )
        is not None,
    )
    check(
        '首轮命中审核就不进工具循环',
        'moderation_blocked = True' in src_stream
        and '不再进入工具循环' in src_stream,
    )

    # ── 5) 熔断常量仍然分家 ──────────────────────────────────────
    check(
        '审核熔断与 429 熔断分开（MAX_CONSECUTIVE_MODERATION）',
        'MAX_CONSECUTIVE_MODERATION' in src_stream,
    )

    print()
    if failed:
        print(f'{failed} 项失败')
        return 1
    print('全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
