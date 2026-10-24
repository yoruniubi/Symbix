from __future__ import annotations
import os
import sys
import types

BACKEND = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(BACKEND, "Symbix_backend.spec")

class _Stub:
    """占位对象:a.pure / a.scripts / a.binaries / a.datas 全部返回自己"""

    def __init__(self, *args, **kwargs) -> None:
        self.kwargs = kwargs

    def __getattr__(self, name: str) -> "_Stub":
        return self


def _fake_hooks() -> types.ModuleType:
    """替掉 collect_data_files / collect_submodules,返回有限的假清单

    注意:这是**装不到 PyInstaller 时的降级**;装了的话走真 hooks。
    """
    mod = types.ModuleType("PyInstaller.utils.hooks")

    def collect_data_files(pkg: str, **kwargs) -> list[tuple[str, str]]:
        import importlib.util

        spec = importlib.util.find_spec(pkg)
        if spec is None or not spec.origin:
            return []
        base = os.path.dirname(spec.origin)
        return [
            (os.path.join(dp, f), os.path.relpath(dp, base))
            for dp, _, files in os.walk(base)
            for f in files
            if not f.endswith((".py", ".pyc", ".pyd", ".so"))
        ]

    mod.collect_data_files = collect_data_files
    mod.collect_submodules = lambda *a, **kw: []
    return mod


def load_spec() -> dict:
    """执行 spec,返回它定义出来的名字空间

    hooks 优先用真的:collect_submodules() 会真的去 import 子包,
    这正是最容易在构建中途才爆的一步(例如 mcp/cli 没有 typer 就 sys.exit(1)),
    预飞必须把它跑出来,不能桩掉。
    """
    hooks = None
    try:
        import PyInstaller.utils.hooks as hooks  # noqa: F401
    except Exception:
        hooks = None

    if hooks is None:
        for name in ("PyInstaller", "PyInstaller.utils"):
            sys.modules[name] = types.ModuleType(name)
        sys.modules["PyInstaller.utils.hooks"] = _fake_hooks()
        print("(未装 PyInstaller,collect_data_files 用降级实现)")

    namespace = {"SPECPATH": BACKEND, "SPEC": SPEC}
    with open(SPEC, encoding="utf-8") as f:
        source = f.read()
    builtins_ = {"__builtins__": __builtins__}
    builtins_.update({n: _Stub for n in ("Analysis", "PYZ", "EXE", "COLLECT")})
    exec(compile(source, SPEC, "exec"), builtins_, namespace)
    return namespace


def measure(path: str) -> tuple[int, int]:
    """返回 (字节数, 文件数)"""
    if os.path.isdir(path):
        size = 0
        count = 0
        for dp, _, files in os.walk(path):
            for f in files:
                size += os.path.getsize(os.path.join(dp, f))
                count += 1
        return size, count
    return os.path.getsize(path), 1


def shorten(path: str) -> str:
    try:
        return os.path.relpath(path, BACKEND)
    except ValueError:
        return path  # 跨盘符(site-packages 在别的盘)


def main() -> int:
    if not os.path.isfile(SPEC):
        print("找不到 spec:", SPEC)
        return 1

    ns = load_spec()
    datas = ns.get("datas", [])
    binaries = ns.get("binaries", [])
    hidden = ns.get("hiddenimports", [])
    excludes = ns.get("excludes", [])

    print("datas %d  binaries %d  hiddenimports %d  excludes %d"
          % (len(datas), len(binaries), len(hidden), len(excludes)))

    missing = [(kind, src) for kind, pairs in (("datas", datas), ("binaries", binaries))
               for src, _ in pairs if not os.path.exists(src)]
    print("缺失源路径:", missing if missing else "无")

    print()
    rows = []
    for src, dest in list(datas) + list(binaries):
        size, count = measure(src)
        rows.append((size, count, src, dest))
    rows.sort(reverse=True)
    for size, count, src, dest in rows:
        print("%8.1f MB  %4d 个文件  %-52s -> %s"
              % (size / 1048576, count, shorten(src), dest))
    print("随包资源合计 %.1f MB" % (sum(r[0] for r in rows) / 1048576))

    if missing:
        print()
        print("有缺失路径,构建前先修 spec。")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())