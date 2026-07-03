import json
import os

class McpConfig:
    def __init__(self, path: str = "mcp_config.json"):
        self.path = os.path.abspath(path)
        self.data = {"mcpServers": {}}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            # 自动初始化生成默认的配置文件
            dir_name = os.path.dirname(self.path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get_servers(self) -> dict:
        """获取所有 MCP server 配置"""
        return self.data.get("mcpServers", {})

    def get_server(self, server_id: str) -> dict | None:
        """获取指定 server 的配置"""
        return self.get_servers().get(server_id)

    def add_server(self, server_id: str, config: dict):
        """添加或更新 MCP server"""
        if "mcpServers" not in self.data:
            self.data["mcpServers"] = {}
        self.data["mcpServers"][server_id] = config
        self.save()

    def remove_server(self, server_id: str):
        """删除 MCP server"""
        if server_id in self.data.get("mcpServers", {}):
            del self.data["mcpServers"][server_id]
            self.save()

    def update(self, **kwargs):
        """保留兼容旧格式的更新方法（但已废弃）"""
        # 新格式不再支持直接更新 host/port 等字段
        # 如果传入的是 mcpServers，则合并更新
        if "mcpServers" in kwargs:
            if "mcpServers" not in self.data:
                self.data["mcpServers"] = {}
            self.data["mcpServers"].update(kwargs["mcpServers"])
            self.save()