#!/usr/bin/env python3
"""把各平台的更新包签名合并成 tauri-plugin-updater 要的 latest.json。

前端/插件只认一个静态清单:
  https://github.com/<repo>/releases/latest/download/latest.json

各平台 CI 各跑各的 job,签名文件分散在不同 artifact 里,所以发版 job 先把它们
归到 dist/,再用本脚本拼出 platforms 映射。没签名的平台(如 linux deb,updater
不支持)直接缺席 —— 插件在该平台 check() 会报错,前端自己退回「打开发布页」。

用法:
  python .github/scripts/make_latest_json.py --dist dist --version 0.1.1 \
      --repo yoruniubi/Symbix --tag v0.1.1 [--notes "..."]

输入: dist/ 下的 symbix_<ver>_<plat>.<ext>.sig(Collect bundles 已统一命名,内容为 minisign 签名串)
      <ext> 可能是 exe(Windows NSIS 安装器即更新包)/ app.tar.gz(macOS)/ nsis.zip(v1 兼容模式)
输出: dist/latest.json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import datetime, timezone

# 平台标签(Collect bundles 归一化后的文件名里带有) -> 清单里的 platform 键(tauri 的 os-arch 命名)
PLATFORM_KEYS: dict[str, str] = {
    "windows-x64": "windows-x86_64",
    "windows-arm64": "windows-aarch64",
    "macos-arm64": "darwin-aarch64",
    "macos-x64": "darwin-x86_64",
    "linux-x64": "linux-x86_64",
}

# 更新包后缀(长后缀在前,避免 .sig / .tar.gz 被截错)。
# v2 updater 里 Windows NSIS 的更新包就是安装器 .exe 本体,所以 .exe 也算更新包。
UPDATER_SUFFIXES: tuple[str, ...] = (
    ".appimage.tar.gz",
    ".nsis.zip",
    ".app.tar.gz",
    ".appimage",
    ".msi",
    ".deb",
    ".exe",
)


def classify(filename: str) -> str | None:
    """按 symbix_<ver>_<plat>.<ext> 命名判断 platform;不认识返回 None。"""
    lowered = filename.lower()
    for suffix in UPDATER_SUFFIXES:
        if lowered.endswith(suffix):
            stem = lowered[: -len(suffix)]
            for tag, platform in PLATFORM_KEYS.items():
                if stem.endswith("_" + tag):
                    return platform
            return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default="dist", help="存放安装包与 .sig 的目录")
    ap.add_argument("--version", required=True, help="语义版本,如 0.1.1")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--tag", required=True, help="Release tag,如 v0.1.1")
    ap.add_argument("--notes", default="", help="清单里的更新说明(可空)")
    ap.add_argument("--out", default="", help="输出路径,默认 <dist>/latest.json")
    ap.add_argument("--require", default="", help="必须存在的 platform 键(逗号分隔),缺失即失败")
    args = ap.parse_args()

    if not os.path.isdir(args.dist):
        print(
            f"[latest.json] 目录不存在: {args.dist}\n"
            "  这个目录应该由 actions/download-artifact 填满(各平台 out/* 合并而来)。\n"
            "  建议检查:产物是否上传成功、checkout 是否放在了 download-artifact 之前(默认会 clean 工作区)",
            file=sys.stderr,
        )
        return 1

    print(f"[latest.json] {args.dist} 内容: {', '.join(sorted(os.listdir(args.dist)))}")

    sigs = sorted(f for f in os.listdir(args.dist) if f.endswith(".sig"))
    if not sigs:
        print("[latest.json] 没找到任何 .sig,无法生成清单", file=sys.stderr)
        return 1

    platforms: dict[str, dict[str, str]] = {}
    for sig_name in sigs:
        asset = sig_name[: -len(".sig")]
        platform = classify(asset)
        if not platform:
            print(f"[latest.json] 跳过(无法归类): {asset}")
            continue
        asset_path = os.path.join(args.dist, asset)
        if not os.path.exists(asset_path):
            print(f"[latest.json] 跳过(缺少安装包本体): {asset}")
            continue
        signature = io.open(os.path.join(args.dist, sig_name), encoding="utf-8").read().strip()
        if not signature:
            print(f"[latest.json] 跳过(签名为空): {sig_name}")
            continue
        url = f"https://github.com/{args.repo}/releases/download/{args.tag}/{asset}"
        platforms[platform] = {"signature": signature, "url": url}
        print(f"[latest.json] {platform:16} <- {asset}")

    missing = [p for p in (s.strip() for s in args.require.split(",")) if p and p not in platforms]
    if missing:
        print(
            f"[latest.json] 缺少必需的平台: {', '.join(missing)}（该平台的更新包或 .sig 没生成/没上传）",
            file=sys.stderr,
        )
        return 1

    if not platforms:
        print("[latest.json] 一份可用的更新包都没有,无法生成清单", file=sys.stderr)
        return 1

    manifest = {
        "version": args.version,
        "notes": args.notes or f"Symbix {args.version}",
        "pub_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": platforms,
    }
    out = args.out or os.path.join(args.dist, "latest.json")
    with io.open(out, "w", encoding="utf-8", newline="\n") as fp:
        json.dump(manifest, fp, ensure_ascii=False, indent=2, sort_keys=True)
        fp.write("\n")
    print(f"[latest.json] 已写出 {out} ({len(platforms)} 个平台)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
