"""端到端并发验证:两个会话同时跑,作用域不能互相串。

这是最关键的一项 —— 后端是 asyncio 单进程多会话并发,如果用的是全局变量
而不是 ContextVar,两个请求交错执行时 A 会看到 B 的目录。这个测试用
asyncio.gather 制造真实交错,再断言各自只能看到自己的 uploads 子目录。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, r'F:/Symbix/backend')

failed = 0


def check(name: str, cond: bool, detail: str = '') -> None:
    global failed
    if cond:
        print(f'  ok   {name}')
    else:
        print(f'  FAIL {name}' + (f' — {detail}' if detail else ''))
        failed += 1


async def main() -> int:
    from Symbix_sdk.tools.file_pipeline import (
        get_uploads_root,
        reset_active_session,
        sandbox_roots,
        session_upload_dir,
        set_active_session,
    )

    print('并发会话作用域不串')

    SID_A = 'concur-sess-a'
    SID_B = 'concur-sess-b'
    dir_a = session_upload_dir(SID_A)
    dir_b = session_upload_dir(SID_B)
    results: dict[str, list[str]] = {}

    async def worker(sid: str, tag: str, delay: float) -> None:
        tok = set_active_session(sid)
        try:
            # 制造交错:先让出控制权,再读 sandbox_roots。
            # 若用全局变量,B 会在这期间把全局值改成自己,A 醒来就读错了。
            await asyncio.sleep(delay)
            results[tag] = sandbox_roots()
            await asyncio.sleep(delay)
            # 再读一次,确认整个生命周期内都稳定
            results[tag + '_again'] = sandbox_roots()
        finally:
            reset_active_session(tok)

    await asyncio.gather(
        worker(SID_A, 'A', 0.01),
        worker(SID_B, 'B', 0.005),
    )

    for tag, own, other in (
        ('A', dir_a, dir_b),
        ('B', dir_b, dir_a),
    ):
        for phase in ('', '_again'):
            roots = results.get(tag + phase, [])
            check(
                f'会话 {tag}{phase or ""} 只看到自己的目录',
                own in roots and other not in roots,
                f'own={own in roots} other={other in roots}',
            )
            check(
                f'会话 {tag}{phase or ""} 不放行 uploads 根',
                get_uploads_root() not in roots,
            )

    # 全部结束后必须回到无会话状态
    from Symbix_sdk.tools.file_pipeline import active_session
    check('并发结束后作用域已清空', active_session() == '')

    print()
    if failed:
        print(f'{failed} 项失败')
        return 1
    print('全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
