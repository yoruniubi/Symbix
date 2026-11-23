"""验证文件搜索工具在会话作用域下不会跨会话命中。

跑法:
    /mnt/e/Anaconda/envs/Symbix/python.exe tests/test_search_isolation.py

这是用户报的原始现象的直接复现:
「upload 里有很多 md,Agent 直接搜文件夹,读到了其他会话的 md,造成上下文污染」

前面的 test_upload_isolation.py 锁的是沙箱白名单;这里再往上走一层,
直接调 `search_files` / `find_files_by_name` 这类**真正会被模型调用**的工具,
确认它们不会把别的会话的文件列出来。
"""
from __future__ import annotations

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


def main() -> int:
    from Symbix_sdk.tools.file_pipeline import (
        reset_active_session,
        session_upload_dir,
        set_active_session,
    )
    from Symbix_sdk.tools.builtin.file_tools import (
        search_file_with_name,
        search_files,
    )

    print('搜索工具不跨会话命中')

    SID_A = 'iso-test-sess-a'
    SID_B = 'iso-test-sess-b'
    dir_a = Path(session_upload_dir(SID_A))
    dir_b = Path(session_upload_dir(SID_B))

    # 摆两份同名文件:属于两个不同会话
    marker = 'isolation_probe_9f3a'
    f_a = dir_a / f'{marker}_mine.md'
    f_b = dir_b / f'{marker}_other.md'
    f_a.write_text('# 这是 A 会话自己的文件\n内容 AAA\n', encoding='utf-8')
    f_b.write_text('# 这是 B 会话的文件\n内容 BBB\n', encoding='utf-8')

    try:
        tok = set_active_session(SID_A)
        try:
            # ── 按文件名找 ────────────────────────────────────
            res = search_file_with_name(f'{marker}_other.md')
            blob = repr(res)
            check(
                '按名找别的会话文件 → 找不到',
                f'_other.md' not in blob or 'success": False' in blob or res.get('results') == [],
                f'竟然找到: {blob[:200]}',
            )

            res_mine = search_file_with_name(f'{marker}_mine.md')
            check(
                '按名找自己的文件 → 能找到',
                marker + '_mine.md' in repr(res_mine),
                repr(res_mine)[:200],
            )

            # ── 按内容全文搜 ──────────────────────────────────
            sr = search_files('内容 BBB', str(Path(session_upload_dir(SID_A)).parent))
            sblob = repr(sr)
            check(
                '按内容搜别的会话文件 → 搜不到',
                '内容 BBB' not in sblob,
                f'竟然搜到: {sblob[:200]}',
            )
        finally:
            reset_active_session(tok)

        # ── 无会话上下文时（后台链路）保持旧行为 ──────────────
        res_plain = search_file_with_name(f'{marker}_other.md')
        check(
            '后台链路（无 sid）仍能搜到 uploads 下文件',
            marker + '_other.md' in repr(res_plain),
            '收窄过头会让定时任务/记忆提取找不到产物',
        )
    finally:
        for f in (f_a, f_b):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        for d in (dir_a, dir_b):
            try:
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            except Exception:
                pass

    print()
    if failed:
        print(f'{failed} 项失败')
        return 1
    print('全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
