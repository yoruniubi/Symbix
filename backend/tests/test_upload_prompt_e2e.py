"""端到端:真实 upload 接口 + 真实 system prompt 构建,验证会话隔离。

不联网、不起 GUI:直接调 FastAPI 的 upload 处理函数和 client 的 prompt 构建。
"""
from __future__ import annotations

import asyncio
import io
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
    from starlette.datastructures import UploadFile

    from application.routers.chat.files_api import upload_files
    from Symbix_sdk.client import SymbixClient
    from Symbix_sdk.provider_store import ProviderRegistry
    from Symbix_sdk.tools.file_pipeline import (
        reset_active_session,
        session_upload_dir,
        set_active_session,
    )

    print('上传 → 提示词 端到端')

    SID_A = 'e2e-sess-a'
    SID_B = 'e2e-sess-b'

    def mk_upload(name: str, text: str) -> UploadFile:
        return UploadFile(
            file=io.BytesIO(text.encode('utf-8')),
            filename=name,
        )

    # 两个会话各上传一份 md
    r_a = await upload_files(
        files=[mk_upload('alpha.md', '# 会话A的私人笔记\n机密A\n')],
        session_id=SID_A,
    )
    r_b = await upload_files(
        files=[mk_upload('beta.md', '# 会话B的私人笔记\n机密B\n')],
        session_id=SID_B,
    )
    check('会话A上传成功', r_a.get('status') == 'ok', repr(r_a)[:150])
    check('会话B上传成功', r_b.get('status') == 'ok', repr(r_b)[:150])

    path_a = r_a['uploaded'][0]['path']
    path_b = r_b['uploaded'][0]['path']
    check('A 的落盘路径含 A 的 sid', SID_A in path_a, path_a)
    check('B 的落盘路径含 B 的 sid', SID_B in path_b, path_b)
    check('两者不在同一目录', str(Path(path_a).parent) != str(Path(path_b).parent))

    # 在 A 的作用域下构建 system prompt
    client = SymbixClient(ProviderRegistry(), system_prompt='你是一言。')
    tok = set_active_session(SID_A)
    try:
        msgs_a = client._build_messages(
            history=[], user_input='我上传的 md 说了什么?', session_id=SID_A
        )
    finally:
        reset_active_session(tok)
    sys_a = msgs_a[0]['content']

    check('A 的 system 含 A 的 sid', SID_A in sys_a)
    check('A 的 system 不含 B 的 sid', SID_B not in sys_a, '串到别的会话了')
    check(
        'A 的 system 含自己的上传目录',
        str(Path(path_a).parent) in sys_a,
    )
    check(
        'A 的 system 不含 B 的上传目录',
        str(Path(path_b).parent) not in sys_a,
    )

    # B 同理
    msgs_b = client._build_messages(
        history=[], user_input='我上传的 md 说了什么?', session_id=SID_B
    )
    sys_b = msgs_b[0]['content']
    check('B 的 system 含 B 的 sid', SID_B in sys_b)
    check('B 的 system 不含 A 的 sid', SID_A not in sys_b)
    check('A/B 的 system 前缀确实不同', sys_a != sys_b)

    # 清理
    for p_ in (path_a, path_b):
        try:
            Path(p_).unlink(missing_ok=True)
        except Exception:
            pass
    for sid in (SID_A, SID_B):
        d = Path(session_upload_dir(sid))
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
    sys.exit(asyncio.run(main()))
