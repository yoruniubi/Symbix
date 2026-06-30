# Symbix_sdk/mcp/installer.py
import subprocess
import shutil
import json
import os

class McpInstaller:
    """负责安装 MCP server 包并注册到配置"""

    def __init__(self, config_path: str):
        self.config_path = config_path

    def _check_runtime(self, runtime: str) -> bool:
        """检查 npm/npx 或 python/pip 是否在用户系统上可用"""
        return shutil.which(runtime) is not None

    def install_npm_server(self, package_name: str, server_id: str, args: list[str] = None):
        """
        安装一个 npm 包形式的 MCP server
        例如: @modelcontextprotocol/server-filesystem
        """
        if not self._check_runtime("npx"):
            raise RuntimeError("未检测到 Node.js/npx，请先安装 Node.js")

        # 用 npx -y 直接跑，npx 会自动处理首次下载
        # 这里只做"预热"验证包能正常拉取，不需要真的 npm install 到全局
        result = subprocess.run(
            ["npx", "-y", package_name, "--help"],
            capture_output=True, text=True, timeout=60
        )

        # 写入配置
        self._register_server(server_id, {
            "command": "npx",
            "args": ["-y", package_name] + (args or []),
        })
        return {"status": "ok", "server_id": server_id}

    def install_pip_server(self, package_name: str, server_id: str, module_name: str, args: list[str] = None):
        """
        安装一个 pip 包形式的 MCP server
        例如: mcp-server-sqlite
        """
        if not self._check_runtime("pip"):
            raise RuntimeError("未检测到 pip")

        result = subprocess.run(
            ["pip", "install", package_name, "--quiet"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            raise RuntimeError(f"安装失败: {result.stderr}")

        self._register_server(server_id, {
            "command": "python",
            "args": ["-m", module_name] + (args or []),
        })
        return {"status": "ok", "server_id": server_id}

    def _register_server(self, server_id: str, config: dict):
        """写入 mcp_config.json"""
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"servers": {}}

        data["servers"][server_id] = config

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)