import json
import os

class McpConfig:
    def __init__(self, path: str = "mcp_config.json"):
        # 1. 核心修复：强制将路径转换为绝对路径
        # 这样不管传入的是 "mcp_config.json" 还是带有深层目录的路径，os.path.dirname 都能切出正确的父级文件夹路径
        self.path = os.path.abspath(path)
        
        self.data = {
            "host": "localhost",
            "port": 8000,
            "username": "admin",
            "password": "admin"
        }
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            # 2. 安全获取父目录：比如 "F:\Symbix\backend"
            dir_name = os.path.dirname(self.path)
            if dir_name:  # 增加防御性判断，确保父目录字符串不为空
                os.makedirs(dir_name, exist_ok=True)
                
            # 自动初始化生成默认的配置文件
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def update(self, **kwargs):
        self.data.update(kwargs)
        self.save()