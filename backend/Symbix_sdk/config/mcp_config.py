import json
import os


class McpConfig:
    def __init__(self, path: str = "mcp_config.json"):
        self.path = os.path.abspath(path)
        self.data = {"mcpServers": {}, "mcp_api_key": {}}
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
        # 兼容旧文件:确保顶层结构完整
        if not isinstance(self.data.get("mcpServers"), dict):
            self.data["mcpServers"] = {}
        self._ensure_api_keys()

    def save(self):
        # 先写到临时文件再 atomic rename，避免写一半崩溃退出后配置损坏。
        # 同时 fsync 保证磁盘落地，避免 Windows 下文件锁/延迟写出不一致。
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, self.path)

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
        """删除 MCP server 配置项并写回磁盘。

        注意:*保存*可能因 Windows 文件锁失败。失败时 raise,调用者 REM BER 会返回错误给前端,
        让用户知道删除未生效(避免内存变了、磁盘还在的灵异)。同时**内存里的 self.data 也还原**,
        以免 /mcp/config 接口返回与磁盘不一致的状态。
        """
        servers = self.data.get("mcpServers", {})
        if server_id not in servers:
            return  # 不存在视为已删除、走在幂等
        # 先快照、便于失败还原
        snapshot = dict(servers)
        keys_snapshot = dict(self.get_api_keys())
        del servers[server_id]
        # 级联删除对应 API Key(避免残留密钥)
        self.remove_api_key(server_id)
        try:
            self.save()
        except Exception:
            # 写磁盘失败:把内存状态还原,避免内存删除成功磁盘还是旧版
            self.data["mcpServers"] = snapshot
            self.data["mcp_api_key"] = keys_snapshot
            raise

    # ===== mcp_api_key:远程服务 API Key 集中存放(顶层独立字段)=====
    # 结构: {"mcpServers": {...}, "mcp_api_key": {"<server_id>": "sk-xxx"}}
    # 密钥与 server 配置分开存储,便于集中管理/导出时选择性忽略。

    def _ensure_api_keys(self):
        if not isinstance(self.data.get("mcp_api_key"), dict):
            self.data["mcp_api_key"] = {}

    def get_api_keys(self) -> dict:
        """获取全部 MCP API Key(server_id -> key)映射。"""
        self._ensure_api_keys()
        return self.data["mcp_api_key"]

    def get_api_key(self, server_id: str) -> str | None:
        """获取指定 server 的 API Key(不存在返回 None)。"""
        keys = self.get_api_keys()
        return keys.get(server_id)

    def set_api_key(self, server_id: str, api_key: str | None):
        """设置/更新指定 server 的 API Key。传空串/None 视为清除。

        返回 True 表示本次写入后磁盘上有该 server 的 key,False 表示无 key。
        """
        keys = self.get_api_keys()
        api_key = (api_key or "").strip()
        if api_key:
            keys[server_id] = api_key
        else:
            keys.pop(server_id, None)
        self.save()
        return bool(keys.get(server_id))

    def remove_api_key(self, server_id: str):
        """删除指定 server 的 API Key(不触发保存;仅供 remove_server 级联时调用)。"""
        keys = self.get_api_keys()
        if server_id in keys:
            del keys[server_id]

    def api_key_to_headers(self, server_id: str) -> dict:
        """把已存的 API Key 转成请求头(Authorization: Bearer <key>)。

        返回空 dict 表示该 server 未配置 key。
        """
        key = self.get_api_key(server_id)
        if not key:
            return {}
        return {"Authorization": f"Bearer {key}"}

    def update(self, **kwargs):
        """保留兼容旧格式的更新方法（但已废弃）"""
        # 新格式不再支持直接更新 host/port 等字段
        # 如果传入的是 mcpServers，则合并更新
        if "mcpServers" in kwargs:
            if "mcpServers" not in self.data:
                self.data["mcpServers"] = {}
            self.data["mcpServers"].update(kwargs["mcpServers"])
            self.save()