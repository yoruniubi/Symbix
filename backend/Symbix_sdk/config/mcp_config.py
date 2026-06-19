import json
import os

class McpCofing:
    def __init__(self, path: str = "mcp_config.json"):
        self.path = path
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
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def update(self, **kwargs):
        self.data.update(kwargs)
        self.save()
    
