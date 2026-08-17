# Symbix_sdk/mcp/installer.py
import subprocess
import shutil
import json
import os
from typing import Dict, List

class McpInstaller:
    """负责安装 MCP server 包并注册到配置"""

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
        if not self._check_runtime("npx"):
            return {"status": "error", "message": "未检测到 Node.js/npx，请先安装 Node.js"}

        # 用 npx -y 直接跑，npx 会自动处理首次下载
        # 这里只做"预热"验证包能正常拉取，不需要真的 npm install 到全局
        try:
            # Windows 下 npx 是 .cmd 脚本，subprocess 默认 shell=False 找不到，
            # 必须用 shell=True（或显式 .cmd 路径）才能跑到 npm 家装见的命令。
            import sys
            use_shell = sys.platform == "win32"
            cmd = ["npx", "-y", package_name, "--help"]
            result = subprocess.run(
                cmd if not use_shell else " ".join(cmd),
                capture_output=True, text=True, timeout=60,
                shell=use_shell,
            )
            # 即使 help 失败（有些 MCP server 没有 --help），也继续尝试注册
        except Exception as e:
            print(f"[MCP Installer] Warning: Package validation failed: {e}")
            # 继续尝试注册，可能是包结构问题

        # 写入配置（新格式）
        self._register_server(server_id, {
            "command": "npx",
            "args": ["-y", package_name] + (args or []),
        })
        return {"status": "ok", "server_id": server_id}

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

        # 写入配置（新格式）
        self._register_server(server_id, {
            "command": "python",
            "args": ["-m", module_name] + (args or []),
        })
        return {"status": "ok", "server_id": server_id}

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