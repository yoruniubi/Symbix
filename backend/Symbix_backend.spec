# -*- mode: python ; coding: utf-8 -*-
"""Symbix 后端打包脚本(PyInstaller onedir)。

用法(在 backend/ 目录下执行):
    pip install pyinstaller
    pyinstaller Symbix_backend.spec --noconfirm --clean
产物:
    dist/SymbixBackend/SymbixBackend.exe
    dist/SymbixBackend/_internal/...      ← 全部资源,内部布局与源码树一致

为什么布局要保持一致:resource_path.resource_root() 在冻结后解析到 sys._MEIPASS
= dist/SymbixBackend/_internal,所以 `resource("Symbix_sdk/bun.exe")` 正好命中
_internal/Symbix_sdk/bun.exe。下面的 dest 目录全部按源码树的相对路径写。

已知待办(本次先不做,打包后按需改):所有「可写」数据(memory.db / jobs.db /
providers.json / uploads / installed_skills 等)目前仍落在 _MEIPASS 里,onedir
下能跑,但装到 Program Files 会写失败。后续应加 resource_path.data_root()。
"""
import os
import sys

# Windows runner 控制台默认 cp1252,spec 里的中文 print 会 UnicodeEncodeError
# (PyInstaller spec 本质是 Python 脚本,同样需要强制 UTF-8)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

BACKEND = os.path.abspath(SPECPATH)          # backend/
SDK = os.path.join(BACKEND, "Symbix_sdk")
SDK_DEST = "Symbix_sdk"

# ---------- 1. 随包携带的读类资源 ----------
datas = []

# 1.1 STT 原生栈:从 multi-platform/ 里按当前平台取一份,拷进发行包的 stt/bin
#     (exe 与同目录 DLL/dylib 的相对位置不能变;平台解析规则见 resource_path.stt_bin_dir)。
#     注意不能 import Symbix_sdk 包本身 —— 它的 __init__ 会拉起整个 SDK,
#     所以这里用 importlib 按文件路径单载 resource_path.py(只依赖标准库)。
import importlib.util as _ilu

_rp_spec = _ilu.spec_from_file_location(
    "_symbix_resource_path", os.path.join(SDK, "resource_path.py"))
_rp_mod = _ilu.module_from_spec(_rp_spec)
_rp_spec.loader.exec_module(_rp_mod)

STT_BIN_SRC = _rp_mod.stt_bin_dir()
if not STT_BIN_SRC.is_dir() or not any(STT_BIN_SRC.glob("sense-voice-stream*")):
    raise SystemExit(
        f"[spec] STT 原生栈缺失/不完整: {STT_BIN_SRC}\n"
        "       multi-platform/<当前平台> 里没找到 sense-voice-stream(旧 stt/bin 也没有)。\n"
        "       补法: 从 SenseVoice fork 的 CI 产物取当前平台那份,\n"
        "       放到 backend/Symbix_sdk/stt/multi-platform/(详见目录内 README.md)")
datas.append((str(STT_BIN_SRC), os.path.join(SDK_DEST, "stt", "bin")))

# 1.2 STT 模型(182MB gguf,平台无关;不入库,CI 发版前先下载)
STT_MODEL_SRC = os.path.join(SDK, "stt", "model")
if not any(fn.endswith(".gguf") for fn in os.listdir(STT_MODEL_SRC)):
    raise SystemExit(
        f"[spec] STT 模型缺失: {STT_MODEL_SRC}\n"
        "       补法: 下载 sense-voice-small-q4_k.gguf 放进该目录(约 182MB,\n"
        "       来源见打包与分发指南.md 的资产清单)")
datas.append((STT_MODEL_SRC, os.path.join(SDK_DEST, "stt", "model")))

# 1.3 内置技能包(frontend-design / pet-forge / skill-creator)。
#     两个原因必须当「数据文件」原样带上,不能只编进 PYZ:
#       ① pet-forge / skill-creator 的 scripts/*.py 是按文件路径 importlib 加载的
#          (见文件末尾附录),PYZ 里的模块在磁盘上没有对应文件;三份 SKILL.md、
#          references/、assets/ 也都是运行时按路径读的。
#       ② 这里是**显式列名字**,不是整目录复制 —— 用户以后通过 UI 装的 skill 也落在
#          这个目录里,整目录复制会把它们一起打进发行包(本机构建尤其危险)。
#          新增内置技能时,记得往这个列表里加名字(漏了会报错,不会静默少带)。
# 1.3 三个内置技能整目录复制,且**全部已入库**(见 .gitignore 的例外规则):
#     pet-forge 本仓库自研;frontend-design / skill-creator 是 Anthropic 官方 skill
#     (https://github.com/anthropics/skills,MIT)的拷贝。入库 = CI checkout 即有,
#     打包输入固定可复现;官方 skill 更新时手动同步一次。缺了说明 checkout 不完整。
BUILTIN_SKILLS = {
    "pet-forge": "本仓库自带(应随 git 一起来,缺了说明 checkout 不完整)",
    "frontend-design": "本仓库自带(Anthropic 官方 skill 拷贝,缺了说明 checkout 不完整)",
    "skill-creator": "本仓库自带(Anthropic 官方 skill 拷贝,缺了说明 checkout 不完整)",
}
for _name, _how in BUILTIN_SKILLS.items():
    _src = os.path.join(SDK, "skill", "installed_skills", _name)
    if not os.path.isfile(os.path.join(_src, "SKILL.md")):
        raise SystemExit(f"[spec] 内置技能缺失: {_src}\n       补法: {_how}")
    datas.append((_src, os.path.join(SDK_DEST, "skill", "installed_skills", _name)))

# 1.4 color_extract.py 不列 datas:它只被 client.py / tools/file_pipeline.py **静态** import,
#     PyInstaller 会收进 PYZ。原先列在这里是因为 pet-forge 的 palette_hint.py 用
#     spec_from_file_location 按路径加载它 —— 该脚本零引用,已删(2026-10-19)。

# 1.5 配置目录。用户要求「能自建就自建、但绝不带隐私」,所以只带这一份模板:
#     providers.json 靠它播种;更重要的是它顺便保证 _MEIPASS/Symbix_sdk/config/
#     这个目录在磁盘上存在 —— DanmakuConfigManager.save() 只 open 不 makedirs,
#     目录不存在时会在 import 阶段直接抛 FileNotFoundError,后端起不来。
#     其余(json 配置、memory/*.db、uploads/、checkpoint_blobs/)全部由代码自建:
#       memory.py:19 / storage.py:39 / blob_store.py:13 / store.py:63 / state.py:21
#       / file_pipeline.py:50 都自带 makedirs。
datas.append((os.path.join(SDK, "config", "providers.json.example"),
              os.path.join(SDK_DEST, "config")))

# 1.6 第三方数据文件(PyInstaller 只搬 .py,这些必须显式认领)
#
# jieba 只认领主词典 dict.txt(5MB),**不能用 collect_data_files("jieba")** —— 那个是把
# 整个包的数据文件全搬,包括 posseg/(15MB 词性标注)、lac_small/(13MB LAC 模型)、
# analyse/idf.txt(6MB),而项目只用 `jieba.lcut`(memory_store.py:185),一共白扔 37MB。
# finalseg 的 prob_*.p 也不用带:非 Java 平台走的是 `from .prob_emit import P`,
# 普通模块会进 PYZ(那三个 .p 是 pickle 兜底,只在 Jython 下走)。
import jieba as _jieba

_JIEBA_DICT = os.path.join(os.path.dirname(_jieba.__file__), "dict.txt")
if not os.path.isfile(_JIEBA_DICT):
    raise SystemExit(f"[spec] 找不到 jieba 词典,构建环境不完整: {_JIEBA_DICT}")
datas.append((_JIEBA_DICT, "jieba"))

# rapidocr(OCR 兑底,实验):模型(3 个 onnx 13MB)+ 各级 config.yaml 必须显式收 ——
# 它们是包目录下的数据文件,PyInstaller 不会自动带;缺了 RapidOCR() 初始化直接报错。
# ocr_fallback 里已做可缺省处理:这份数据缺失只会让 OCR 兑底退回原行为,不影响主链路。
try:
    import rapidocr_onnxruntime as _rapidocr
    _RAPID_ROOT = os.path.dirname(_rapidocr.__file__)
    for _dp, _dn, _fn in os.walk(os.path.join(_RAPID_ROOT, "models")):
        for _f in _fn:
            _src = os.path.join(_dp, _f)
            datas.append((_src, os.path.relpath(_dp, _RAPID_ROOT)))
    datas.append((os.path.join(_RAPID_ROOT, "config.yaml"), "rapidocr_onnxruntime"))
    for _sub in ("ch_ppocr_v2_cls", "ch_ppocr_v3_det", "ch_ppocr_v3_rec"):
        _p = os.path.join(_RAPID_ROOT, _sub, "config.yaml")
        if os.path.isfile(_p):
            datas.append((_p, os.path.join("rapidocr_onnxruntime", _sub)))
    del _rapidocr, _RAPID_ROOT
except ImportError:
    pass  # 打包环境未装 rapidocr = 决定不带 OCR,静默跳过

datas += collect_data_files("magika")     # models/standard_v3_3/*.onnx(4MB,markitdown 基础依赖)

# ---------- 2. 捆绑运行时(用户明确要求带上)----------
# 放 binaries 而不是 datas:它们是独立可执行文件,PyInstaller 会顺手做依赖检查;
# bun 是 Zig 静态链接、uv 是 Rust,都没有外部 DLL 依赖。
# 文件名按平台:Windows 用 bun.exe/uv.exe,macOS/Linux 用 bun/uv(与 sdk_binary() 的
# 命名规则一致)。git 不收它们(.gitignore),CI 发版前从官方 Release 下载放进 Symbix_sdk/。
if sys.platform == "win32":
    _RUNTIMES = [("bun.exe", "~86MB,bunx 语义"), ("uv.exe", "~41MB,uvx 语义")]
else:
    _RUNTIMES = [("bun", "~86MB,bunx 语义"), ("uv", "~41MB,uvx 语义")]

binaries = []
for _fn, _hint in _RUNTIMES:
    _src = os.path.join(SDK, _fn)
    if not os.path.isfile(_src):
        raise SystemExit(
            f"[spec] SDK 内置运行时缺失: {_src} ({_hint})\n"
            "       补法: 从官方 Release 下载当前平台那份放进 Symbix_sdk/ ——\n"
            "         bun: https://github.com/oven-sh/bun/releases (bun-<平台>.zip)\n"
            "         uv : https://github.com/astral-sh/uv/releases (uv-<平台>.zip/tar.gz)")
    binaries.append((_src, SDK_DEST))

# pixeldraw(像素画 MCP,内置 stdio 工具):连接器把裸命令名解析到
# 资源目录 pixeldraw/ 下(见 mcp/connector.py resolve_stdio_runner),
# 所以必须打到 <_internal>/pixeldraw/pixeldraw.exe。缺失不拦构建 ——
# 它是可选能力,没打包时用户仍可手动配置外部路径。
_pd_src = os.path.join(BACKEND, "pixeldraw", "pixeldraw.exe" if sys.platform == "win32" else "pixeldraw")
if os.path.isfile(_pd_src):
    binaries.append((_pd_src, "pixeldraw"))
else:
    print("[spec] 提示: backend/pixeldraw/ 未找到 pixeldraw 可执行文件,跳过(可选 MCP)")

# openssl DLL 强制取 conda Library\bin 那份(与 pack python 实际加载的一致):
# PyInstaller 自动搜到的可能是 Python 目录下的旧裁剪版,冻结后 _ssl.pyd 解析到它就报
# "DLL load failed while importing _ssl"(打包含 opencv/rapidocr 后依赖图变复杂才暴露)。
_conda_bin = os.path.join(os.path.dirname(sys.executable), "Library", "bin")
for _dll in ("libcrypto-3-x64.dll", "libssl-3-x64.dll"):
    _src = os.path.join(_conda_bin, _dll)
    if os.path.isfile(_src):
        binaries.append((_src, "."))

# ---------- 3. 静态分析抓不到的 import ----------
hiddenimports = [
    # uvicorn 全部按字符串装配(uvicorn/config.py 的 HTTP_PROTOCOLS / WS_PROTOCOLS /
    # LIFESPAN / LOOP_FACTORIES 都是 "包.模块:对象" 形式,modulegraph 看不见)
    "loop_proactor",                                        # main.py 的 loop="loop_proactor:force_proactor"
    "uvicorn.logging",
    "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on", "uvicorn.lifespan.off",
    # apscheduler:jobstore / executor / trigger 都是按名字查表实例化的
    "apscheduler.jobstores.sqlalchemy",
    "apscheduler.executors.pool",
    "apscheduler.triggers.cron",
    "apscheduler.triggers.interval",
    "apscheduler.triggers.date",
    # sqlalchemy 方言是运行时 importlib 加载的
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
]

# 函数体内的 import(如 tools/builtin/*.py 里的 markitdown / docx / pptx)PyInstaller
# 的静态分析本来就能扫到,这里只做一层保险,防止某个模块被条件分支挡住。
hiddenimports += [
    "mcp", "ddgs", "PIL", "markitdown", "edge_tts",
    "docx", "pptx", "openpyxl", "pypdf", "fpdf", "markdown_it",
    "mammoth", "pdfplumber", "pdfminer", "lxml",
]

# 按包整体收集子模块:markitdown 的 converters 用了运行时拼名字的 import,
# collect_submodules 一次收全,免得逐个补。
#
# ⚠️ **mcp 千万不能用这招**:mcp/cli/cli.py:15 是
#     try: import typer
#     except ImportError: print(...); sys.exit(1)
#   typer 属 `mcp[cli]` extra,项目只用 mcp 的 OAuth 客户端、不用它的 CLI,
#   所以 requirements.txt 里故意没装 → collect_submodules 一 import 到 mcp.cli 就 SystemExit(1),
#   而 SystemExit 不是 ImportError,不会被吞掉,整个构建进程直接死。
#   (更隐蔽:pkgutil.walk_packages 自己也要 import 子包来拿 __path__,
#    所以「只列表不导入」的写法也救不了 —— mcp 从外部无法安全枚举。
#    实测:walk_packages 比 __import__ 先死。)
#   项目里用到 mcp SDK 的只有 Symbix_sdk/mcp/oauth.py 一处,且是模块级 try: 里的
#   静态 import(静态分析本来就抓得到),只有两个函数体内的 lazy import 需要显式补。
hiddenimports += collect_submodules("markitdown")
hiddenimports += [
    "mcp.client.auth",                # oauth.py:24 模块级 try 内(静态分析也会抓到,双保险)
    "mcp.client.auth.exceptions",     # oauth.py:378/382 函数体内 lazy import
    "mcp.shared.auth",
]

# ---------- 4. 排除用不到的大件 ----------
# 注意:**不要排 numpy** —— rank_bm25 依赖它;也不要排 onnxruntime(magika 要用)。
excludes = [
    "torch", "funasr", "pandas", "matplotlib", "scipy",
    "tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6",
    "IPython", "notebook", "jupyter", "pytest", "sphinx",
    # onnxruntime 的 tools / transformers / quantization 三个子包只在做模型转换时用,
    # 其中 symbolic_shape_infer 要 sympy —— 而 sympy 单独就 71MB!
    # 项目里 magika 只用 `import onnxruntime as rt; rt.InferenceSession(...)`,
    # 这些全用不到。注:onnxruntime/__init__.py 只 import capi._pybind_state,
    # 静态分析本来抓不到它们,但 pyinstaller-hooks-contrib 的 onnxruntime hook
    # 可能 collect_submodules 全收,所以这里显式排掉,打完包用 _internal 体积复核。
    "sympy", "mpmath",
    "onnxruntime.tools", "onnxruntime.transformers", "onnxruntime.quantization",
]

a = Analysis(
    [os.path.join(BACKEND, "main.py")],
    pathex=[BACKEND],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[os.path.join(BACKEND, "pyinstaller_hooks")],
    # 上面那个目录里只放了一个 hook-jieba.py:用来挤掉 _pyinstaller_hooks_contrib
    # 自带的同名字 hook(它一行 collect_data_files("jieba") 会把 posseg/lac_small/
    # analyse 共 27MB 一起搬进来)。hookspath 的优先级是 1000,contrib 是 -1000,
    # 同名时高优先级胜出。改完这个文件要先重启一次构建才会生效。
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SymbixBackend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # bun.exe / uv.exe / *.exe 一律别压:UPX 对自带运行时的
                            # 大二进制既慢又容易压坏,省的那点体积不值
    console=True,           # 后端要留控制台看日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SymbixBackend",
)

# ---------- 附录:哪些路径必须在磁盘上真实存在 ----------
#
# (1) 按文件路径 importlib 加载的模块 —— PYZ 里的模块不落盘,必须靠 datas 给一份副本:
#   application/routers/pet.py:502               → installed_skills/pet-forge/scripts/*.py   [1.3]
#   application/routers/skills.py:144            → skill-creator/scripts/init_skill.py      [1.3]
#   Symbix_sdk/tools/builtin/skill_tools.py:71   → 同上                                     [1.3]
#
# (2) 用 __file__ 上溯推出的路径 —— 不用管:PyInstaller 把 PYZ 模块的 __file__ 设为
#   _MEIPASS/<点号路径>.pyc,层级与源码树一一对应,上溯结果与 resource_root() 同根。
#   涉及 state.py:19/52、files.py:16、pet.py:26、journal.py:10、voice.py:20、
#   danmaku_service.py:10、risk_context.py:172/272、risk_classifier.py:50/395、
#   connector.py:507、skill_tools.py:59、tool_setup.py:38、file_pipeline.py:45。
#   其中只有一处需要 datas 配合:config 目录必须存在(见 1.5)。
#
# 首次打包跑起来时看控制台的 `[runtime] frozen BASE_DIR` 与 `resource_root()` 两行,
# 相等即上述推论成立;不等才需要把这些点改成 resource()。详见文档 §8.55.10。
#
# 改完本文件先跑预飞再构建(1 秒代替 10 分钟):cd backend && python spec_preflight.py
