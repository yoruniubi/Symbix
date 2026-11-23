"""对照前端的产物检测规则与后端工具的真实输出契约。

跑法: /mnt/e/Anaconda/envs/Symbix/python.exe tests/test_artifact_contract.py

为什么需要:前端 `msgArtifacts.ts` 靠硬编码的工具名 + 字段名判定「本轮产出了
哪些文件」。工具一改名、字段一改名,产物卡片就会**静默变少**——不报错,只是
用户发现「明明生成了 docx,卡片里却没有」。这个测试把后端的真实契约摊开,
两边一对就能看出漏了谁。
"""
from __future__ import annotations

import inspect
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


# 后端真正会往磁盘写文件的工具 → 它的输出路径出现在哪个字段
WRITERS = {
    'create_file': '入参 file_path + 返回 "File created: <path>"',
    'edit_file': '入参 file_path',
    'search_and_replace': '返回 results[].file',
    'md_to_docx': '入参 out_path + 返回 path',
    'md_to_xlsx': '入参 out_path + 返回 path',
    'md_to_pptx': '入参 out_path + 返回 path',
    'md_to_pdf': '入参 out_path + 返回 path',
    'doc_to_markdown_file': '入参 out_md_path + 返回 md_path',
    'download_file': '返回 path',
}


def main() -> int:
    from Symbix_sdk.tools.tool_setup import ALL_TOOL_SCHEMAS

    print('产物检测契约对照')

    ts = Path('F:/Symbix/Symbix_frontend/src/utils/msgArtifacts.ts').read_text(encoding='utf-8')

    # ── 1) 前端白名单里的工具必须真实存在 ────────────────────────
    import re
    # 抓 WRITE_ARG_TOOLS 的键
    m = re.search(r'const WRITE_ARG_TOOLS[^{]*\{(.*?)\n\}', ts, re.S)
    check('找到 WRITE_ARG_TOOLS', m is not None)
    arg_tools = set(re.findall(r'^\s{2}(\w+):', m.group(1), re.M)) if m else set()

    m2 = re.search(r'const RESULT_SCAN_TOOLS = new Set\(\[(.*?)\]\)', ts, re.S)
    check('找到 RESULT_SCAN_TOOLS', m2 is not None)
    res_tools = set(re.findall(r"'(\w+)'", m2.group(1))) if m2 else set()

    frontend_tools = arg_tools | res_tools
    real = set(ALL_TOOL_SCHEMAS)
    phantom = sorted(frontend_tools - real)
    check(
        '前端没有引用不存在的工具',
        not phantom,
        f'这些工具后端根本没有: {phantom}',
    )

    # ── 2) 后端每个写盘工具都要被前端认到 ────────────────────────
    missing = sorted(set(WRITERS) - frontend_tools)
    check(
        '后端所有写盘工具都被前端覆盖',
        not missing,
        f'漏检（产物会静默不显示）: {missing}',
    )

    # ── 3) 每个写盘工具的输出字段要被识别 ────────────────────────
    m3 = re.search(r'const RESULT_PATH_KEYS = new Set\(\[(.*?)\]\)', ts, re.S)
    check('找到 RESULT_PATH_KEYS', m3 is not None)
    keys = set(re.findall(r"'(\w+)'", m3.group(1))) if m3 else set()

    # doc_to_markdown_file 返回的是 md_path，必须在内
    check(
        'RESULT_PATH_KEYS 覆盖 md_path（doc_to_markdown_file 的输出字段）',
        'md_path' in keys,
        f'当前只有: {sorted(keys)}',
    )

    # ── 4) 后端这些字段真的存在（防止我瞎猜） ────────────────────
    doc_src = Path('F:/Symbix/backend/Symbix_sdk/tools/builtin/doc_tools.py').read_text(encoding='utf-8')
    check('doc_to_markdown_file 确实返回 md_path', '"md_path": out_abs' in doc_src)
    check('md_to_* 确实返回 path', '"path": out_abs' in doc_src)
    web_src = Path('F:/Symbix/backend/Symbix_sdk/tools/builtin/web_tools.py').read_text(encoding='utf-8')
    check('download_file 确实返回 path', '"path": resolved' in web_src)
    ft_src = Path('F:/Symbix/backend/Symbix_sdk/tools/builtin/file_tools.py').read_text(encoding='utf-8')
    check('create_file 确实返回 File created 文案', 'f"File created: {path}"' in ft_src)

    print()
    if failed:
        print(f'{failed} 项失败')
        return 1
    print('全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
