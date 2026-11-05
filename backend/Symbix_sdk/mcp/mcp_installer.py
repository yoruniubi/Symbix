import subprocess
import shutil
import json
import os
from typing import Dict, List

class McpInstaller:
    """负责安装 MCP server 包并注册到配置"""

    # npx 缺失时降级为 SDK 内置 bun.exe(bunx 语义 = `bun x <pkg>`)
    def _resolve_pkg_runner(self) -> tuple[str | None, str]:
        """选择拉起 npm 包的 CLI。

        返回 (command, mode):
        - 系统有 npx      → ("npx", "npx"),args 带 -y
        - SDK 内置 bun.exe → (bun_exe 绝对路径, "bunx"),args 不带 -y
        - 都没有           → (None, "")
        """
        if shutil.which("npx"):
            return "npx", "npx"
        try:
            from Symbix_sdk.resource_path import sdk_binary
            bun_exe = sdk_binary("Symbix_sdk/bun")
        except Exception:
            bun_exe = None
        if bun_exe and os.path.exists(str(bun_exe)):
            return str(bun_exe), "bunx"
        return None, ""

    def __init__(self, config_path: str):
        self.config_path = config_path

    def _check_runtime(self, runtime: str) -> bool:
        """检查 npm/npx 或 python/pip 是否在用户系统上可用"""
        return shutil.which(runtime) is not None

    def install_npm_server(self, package_name: str, server_id: str, args: List[str] = None) -> Dict:
        """
        安装一个 npm 包形式的 MCP server
        例如: @playwright/mcp@latest
        """
        runner, mode = self._resolve_pkg_runner()
        if not runner:
            return {"status": "error", "message": "未检测到 Node.js/npx,且 SDK 内未捆绑 bun,请先安装 Node.js 或 bun"}

        # 用 npx -y / bun x 直接跑,自动处理首次下载
        # 这里只做"预热"验证包能正常拉取,不需要真的 npm install 到全局
        try:
            # Windows 下 npx 是 .cmd 脚本,subprocess 默认 shell=False 找不到,
            # 必须用 shell=True(或显式 .cmd 路径)才能跑到 npm 家装见的命令。
            import sys
            use_shell = sys.platform == "win32"
            if mode == "npx":
                cmd_tokens = ["npx", "-y", package_name, "--help"]
            else:
                cmd_tokens = [runner, "x", package_name, "--help"]
            result = subprocess.run(
                cmd_tokens if not use_shell else " ".join(cmd_tokens),
                capture_output=True, text=True, timeout=60,
                shell=use_shell,
            )
            # 即使 help 失败(有些 MCP server 没有 --help),也继续尝试注册
        except Exception as e:
            print(f"[MCP Installer] Warning: Package validation failed: {e}")
            # 继续尝试注册,可能是包结构问题

        # 写入配置(新格式):npx 模式带 -y;bun 模式用 `bun x <pkg>`(bunx 语义)
        if mode == "npx":
            cmd_args = ["-y", package_name] + (args or [])
        else:
            cmd_args = ["x", package_name] + (args or [])
        self._register_server(server_id, {
            "command": runner,
            "args": cmd_args,
        })
        message = "" if mode == "npx" else "使用 SDK 内置 bun 作为运行时"
        return {"status": "ok", "server_id": server_id, "runner": runner, "message": message}

    def install_pip_server(self, package_name: str, server_id: str, module_name: str, args: List[str] = None) -> Dict:
        """
        安装一个 pip 包形式的 MCP server
        例如: mcp-server-sqlite
        """
        if not self._check_runtime("pip"):
            return {"status": "error", "message": "未检测到 pip"}

        try:
            result = subprocess.run(
                ["pip", "install", package_name, "--quiet"],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                return {"status": "error", "message": f"安装失败: {result.stderr}"}
        except Exception as e:
            return {"status": "error", "message": f"安装异常: {e}"}

        # 写入配置(新格式)
        self._register_server(server_id, {
            "command": "python",
            "args": ["-m", module_name] + (args or []),
        })
        return {"status": "ok", "server_id": server_id}

    def install_uvx_server(self, package_name: str, server_id: str, args: List[str] = None) -> Dict:
        """
        安装一个 uvx 形式的 MCP server
        例如: uvx mcp-server-sqlite
        """
        runner, mode = self._resolve_uvx_runner()
        if not runner:
            return {"status": "error", "message": "未检测到 uvx,且 SDK 内未捆绑 uv,请先安装 uv 或补齐 SDK"}

        # 预热验证包能否拉取(uvx 语义 = uv tool run <pkg>)
        try:
            import sys
            use_shell = sys.platform == "win32"
            if mode == "uvx":
                cmd_tokens = ["uvx", package_name, "--help"]
            else:
                cmd_tokens = [runner, "tool", "run", package_name, "--help"]
            result = subprocess.run(
                cmd_tokens if not use_shell else " ".join(cmd_tokens),
                capture_output=True, text=True, timeout=60,
                shell=use_shell,
            )
            # help 失败也继续注册(有些 MCP server 没有 --help)
        except Exception as e:
            print(f"[MCP Installer] Warning: uvx validation failed: {e}")

        if mode == "uvx":
            cmd_args = [package_name] + (args or [])
        else:
            cmd_args = ["tool", "run", package_name] + (args or [])
        self._register_server(server_id, {
            "command": runner,
            "args": cmd_args,
        })
        message = "" if mode == "uvx" else "使用 SDK 内置 uv 作为运行时"
        return {"status": "ok", "server_id": server_id, "runner": runner, "message": message}

    def _resolve_uvx_runner(self) -> tuple[str | None, str]:
        """选择拉起 uvx 型 MCP 的 CLI:
        - 系统有 uvx → ("uvx", "uvx")
        - SDK 内置 uv.exe → (uv_exe 绝对路径, "uv")
        - 都没有 → (None, "")
        """
        if shutil.which("uvx"):
            return "uvx", "uvx"
        try:
            from Symbix_sdk.resource_path import sdk_binary
            uv_exe = sdk_binary("Symbix_sdk/uv")
        except Exception:
            uv_exe = None
        if uv_exe and os.path.exists(str(uv_exe)):
            return str(uv_exe), "uv"
        return None, ""

    def _register_server(self, server_id: str, config: Dict):
        """写入 mcp_config.json（新格式）"""
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"mcpServers": {}}

        # 确保 mcpServers 字段存在
        if "mcpServers" not in data:
            data["mcpServers"] = {}

        data["mcpServers"][server_id] = config

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)