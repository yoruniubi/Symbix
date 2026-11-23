"""验证 uploads/ 的会话隔离:当前会话看不到别的会话目录。

跑法:
    /mnt/e/Anaconda/envs/Symbix/python.exe tests/test_upload_isolation.py

为什么值得测(用户实测到的问题):
上传件按会话落在 uploads/{sid}/,但沙箱原先放行**整个 uploads/ 根**,
而 system prompt 里既没有 session_id 也没有「本会话上传目录」。于是模型
为了找「刚上传的那个 md」会去 uploads/ 下通搜,把别的会话的文档一起读进
上下文 —— 表现为「Agent 知道了他不该知道的内容」。

这个测试锁住两层防护:
  · 沙箱:有活跃会话时,uploads 可见面只剩该会话子目录;
  · 提示词:system 里出现 session_id 和本会话上传目录,且明确禁止横向扫。
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
        active_session,
        get_uploads_root,
        reset_active_session,
        sandbox_roots,
        session_upload_dir,
        set_active_session,
    )

    print('uploads 会话隔离')

    SID_A = 'sess-aaaa-1111'
    SID_B = 'sess-bbbb-2222'
    dir_a = session_upload_dir(SID_A)
    dir_b = session_upload_dir(SID_B)

    # ── 1) 两个会话目录必须不同 ──────────────────────────────────
    check('不同会话落在不同目录', dir_a != dir_b, f'{dir_a} vs {dir_b}')
    check('会话目录在 uploads 根下', dir_a.startswith(get_uploads_root()))

    # ── 2) 无会话上下文时:向后兼容,放行整个 uploads ─────────────
    roots_plain = sandbox_roots()
    check(
        '无活跃会话时仍放行整个 uploads（后台链路不炸）',
        get_uploads_root() in roots_plain,
    )

    # ── 3) 有会话 A：只能看到 A 的目录 ───────────────────────────
    tok = set_active_session(SID_A)
    try:
        check('active_session() 返回 A', active_session() == SID_A)
        roots_a = sandbox_roots()
        check('A 的目录在可读区', dir_a in roots_a)
        check('A 会话下看不到 B 的目录', dir_b not in roots_a, f'泄露: {dir_b}')
        check(
            'A 会话下 uploads 根本身不再放行',
            get_uploads_root() not in roots_a,
            '根若仍放行，模型就能 ls 出所有会话',
        )
        # 关键:整个 uploads 根不在白名单里 → resolve_under_root 不会把
        # uploads/<B>/x.md 解析进来
        from Symbix_sdk.tools.file_pipeline import resolve_under_root
        probe_b = Path(dir_b) / 'other_session.md'
        got = resolve_under_root(str(probe_b), roots_a)
        check(
            '解析 B 会话里的文件被拒',
            got is None,
            f'竟然解析成功: {got}',
        )
        probe_a = Path(dir_a) / 'mine.md'
        got_a = resolve_under_root(str(probe_a), roots_a)
        check('解析 A 会话里的文件放行', got_a is not None)
    finally:
        reset_active_session(tok)

    # ── 4) 切到 B：作用域跟着换 ─────────────────────────────────
    tok = set_active_session(SID_B)
    try:
        roots_b = sandbox_roots()
        check('切到 B 后只见 B 的目录', dir_b in roots_b and dir_a not in roots_b)
    finally:
        reset_active_session(tok)

    # ── 5) reset 之后回到无会话状态 ─────────────────────────────
    check('reset 后 active_session 为空', active_session() == '')
    check(
        'reset 后 uploads 根重新放行',
        get_uploads_root() in sandbox_roots(),
    )

    # ── 6) system prompt 必须带上 session_id 与上传目录 ──────────
    src = Path(r'F:/Symbix/backend/Symbix_sdk/client.py').read_text(encoding='utf-8')
    check('client.chat_stream 接受 session_id', 'session_id: Optional[str] = None' in src)
    check('_build_messages 接受 session_id', 'session_id: Optional[str] = None' in src)
    check('system 里注入 [当前会话]', '[当前会话]' in src)
    check('system 里给出 session_id 值', 'session_id = ' in src)
    check('system 里给出本会话上传目录', '本会话的上传目录 = ' in src)
    check(
        'system 里明确禁止横向扫其他会话',
        '严禁遍历或读取' in src and 'uploads/' in src,
    )

    # ── 7) 调用点必须真的把 sid 传下去 ──────────────────────────
    for name, path in (
        ('stream.py', r'F:/Symbix/backend/application/routers/chat/stream.py'),
        ('approve.py', r'F:/Symbix/backend/application/routers/chat/approve.py'),
    ):
        s = Path(path).read_text(encoding='utf-8')
        check(f'{name} 设置了会话作用域', 'set_active_session(' in s)
        check(f'{name} 还原了会话作用域', 'reset_active_session(' in s)

    s_stream = Path(r'F:/Symbix/backend/application/routers/chat/stream.py').read_text(encoding='utf-8')
    check(
        'stream.py 把 session_id 传给 chat_stream',
        'session_id=request.session_id,' in s_stream,
    )
    s_appr = Path(r'F:/Symbix/backend/application/routers/chat/approve.py').read_text(encoding='utf-8')
    check(
        'approve.py 把 session_id 传给 _build_messages',
        'session_id=session_id,' in s_appr,
    )

    print()
    if failed:
        print(f'{failed} 项失败')
        return 1
    print('全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
