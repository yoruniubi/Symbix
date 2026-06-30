import requests
import json

# 负责连接mcp server，提供基础的请求方法
class Connector:
    def __init__(self, host: str, port: int, username: str, password: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.base_url = f"http://{self.host}:{self.port}"

    # 请求对应的接口、资源
    def _request(self, method: str, endpoint: str, **kwargs):
        url = f"{self.base_url}/{endpoint}"
        auth = (self.username, self.password)
        try:
            response = requests.request(method, url, auth=auth, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Request error: {e}")
            return None

    def list_tools_as_openai_format(self) -> list[dict]:
        """从 MCP server 获取工具列表，转换为 OpenAI function calling 格式"""
        result = self._request("GET", "tools")
        if not result:
            return []
        # 适配不同 MCP server 返回格式
        tools_data = result if isinstance(result, list) else result.get("tools", [])
        openai_tools = []
        for tool in tools_data:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", tool.get("parameters", {
                        "type": "object",
                        "properties": {}
                    })),
                },
            })
        return openai_tools

    def call_tool(self, tool_name: str, arguments) -> str:
        """调用 MCP server 上的工具并返回结果字符串"""
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return f"[Error] Invalid JSON arguments: {arguments}"
        result = self._request("POST", f"tools/{tool_name}", json={"arguments": arguments})
        if result is None:
            return f"[Error] Failed to call MCP tool '{tool_name}'"
        # MCP server 通常返回 {"content": [...]} 或直接返回结果
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            if isinstance(content, list):
                return "\n".join(
                    item.get("text", str(item)) if isinstance(item, dict) else str(item)
                    for item in content
                )
            return str(content)
        return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
