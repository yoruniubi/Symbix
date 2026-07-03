import subprocess
import json
import threading
import queue
import uuid
from typing import Optional, Dict, List

class McpServerClient:
    """通过 stdio 与 MCP server 通信的客户端"""
    
    def __init__(self, server_id: str, command: str, args: List[str]):
        self.server_id = server_id
        self.command = command
        self.args = args
        self.process: Optional[subprocess.Popen] = None
        self.request_queue = queue.Queue()
        self.response_map: Dict[str, queue.Queue] = {}
        self._stop_event = threading.Event()
        self._reader_thread: Optional[threading.Thread] = None
        self._tools_cache: Optional[List[dict]] = None
        
    def start(self):
        """启动 MCP server 进程"""
        import sys
        try:
            # Windows 下 npx/npm 等是 .cmd 脚本，需要 shell=True 才能找到
            use_shell = sys.platform == "win32"
            popen_kwargs = dict(
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,
            )
            if use_shell:
                # Windows shlex.quote 不可靠，手动给含空格的参数加双引号
                cmd_str = self.command + " " + " ".join(
                    f'"{a}"' if " " in a else a for a in self.args
                )
                self.process = subprocess.Popen(cmd_str, shell=True, **popen_kwargs)
            else:
                self.process = subprocess.Popen(
                    [self.command] + self.args, **popen_kwargs
                )
            
            # 启动读取线程
            self._reader_thread = threading.Thread(
                target=self._read_output,
                daemon=True
            )
            self._reader_thread.start()
            
            # 发送初始化请求
            self._send_request({
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                        "resources": {}
                    },
                    "clientInfo": {
                        "name": "symbix-client",
                        "version": "1.0.0"
                    }
                }
            })
            
            print(f"[MCP] Server '{self.server_id}' started successfully")
            return True
            
        except Exception as e:
            print(f"[MCP] Failed to start server '{self.server_id}': {e}")
            return False
    
    def _read_output(self):
        """从 stdout 读取 MCP server 的响应"""
        while not self._stop_event.is_set() and self.process:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                    
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    response = json.loads(line)
                    request_id = response.get("id")
                    if request_id and request_id in self.response_map:
                        self.response_map[request_id].put(response)
                except json.JSONDecodeError:
                    print(f"[MCP] Invalid JSON from server: {line}")
                    
            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"[MCP] Error reading output: {e}")
                break
    
    def _send_request(self, request: dict) -> dict:
        """发送请求并等待响应"""
        request_id = request["id"]
        response_queue = queue.Queue()
        self.response_map[request_id] = response_queue
        
        try:
            # 发送请求
            message = json.dumps(request) + "\n"
            self.process.stdin.write(message)
            self.process.stdin.flush()
            
            # 等待响应（超时 30 秒）
            try:
                response = response_queue.get(timeout=30)
                return response
            except queue.Empty:
                return {"error": {"code": -32603, "message": "Request timeout"}}
                
        finally:
            # 清理响应映射
            self.response_map.pop(request_id, None)
    
    def list_tools(self) -> List[dict]:
        """获取工具列表"""
        if self._tools_cache is not None:
            return self._tools_cache
            
        try:
            response = self._send_request({
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/list"
            })
            
            if "error" in response:
                print(f"[MCP] Error listing tools: {response['error']}")
                return []
                
            tools = response.get("result", {}).get("tools", [])
            self._tools_cache = tools
            return tools
            
        except Exception as e:
            print(f"[MCP] Exception listing tools: {e}")
            return []
    
    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """调用工具"""
        try:
            response = self._send_request({
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            })
            
            if "error" in response:
                return f"[Error] {response['error'].get('message', 'Unknown error')}"
                
            result = response.get("result", {})
            content = result.get("content", [])
            
            # 解析内容
            output_parts = []
            for item in content:
                if isinstance(item, dict):
                    if "text" in item:
                        output_parts.append(item["text"])
                    elif "type" in item and item["type"] == "image":
                        output_parts.append(f"[Image: {item.get('data', '')[:50]}...]")
                else:
                    output_parts.append(str(item))
            
            return "\n".join(output_parts)
            
        except Exception as e:
            return f"[Error] Exception calling tool: {e}"
    
    def stop(self):
        """停止 MCP server"""
        self._stop_event.set()
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception as e:
                print(f"[MCP] Error stopping server: {e}")
                try:
                    self.process.kill()
                except:
                    pass


class McpServerManager:
    """管理多个 MCP server 客户端"""
    
    def __init__(self):
        self.servers: Dict[str, McpServerClient] = {}
        self._initialized = False
    
    def add_server(self, server_id: str, command: str, args: List[str]) -> bool:
        """添加并启动 MCP server"""
        if server_id in self.servers:
            print(f"[MCP] Server '{server_id}' already exists")
            return False
            
        client = McpServerClient(server_id, command, args)
        if client.start():
            self.servers[server_id] = client
            return True
        return False
    
    def remove_server(self, server_id: str):
        """移除 MCP server"""
        if server_id in self.servers:
            self.servers[server_id].stop()
            del self.servers[server_id]
    
    def list_tools_as_openai_format(self) -> List[dict]:
        """获取所有服务器的工具并转换为 OpenAI 格式"""
        openai_tools = []
        
        for server_id, client in self.servers.items():
            tools = client.list_tools()
            for tool in tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("inputSchema", {
                            "type": "object",
                            "properties": {}
                        }),
                    },
                })
        
        return openai_tools
    
    def call_tool(self, tool_name: str, arguments) -> str:
        """调用指定工具（自动查找服务器）"""
        # 遍历所有服务器查找工具
        for server_id, client in self.servers.items():
            tools = client.list_tools()
            for tool in tools:
                if tool.get("name") == tool_name:
                    return client.call_tool(tool_name, arguments)
        
        return f"[Error] Tool '{tool_name}' not found in any MCP server"
    
    def stop_all(self):
        """停止所有服务器"""
        for client in self.servers.values():
            client.stop()
        self.servers.clear()


# 保持向后兼容的 Connector 类（已废弃但保留）
class Connector:
    """废弃：使用 McpServerManager 代替"""
    
    def __init__(self, host: str, port: int, username: str, password: str):
        print("[MCP] Warning: Connector class is deprecated. Use McpServerManager instead.")
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.base_url = f"http://{self.host}:{self.port}"
    
    def _request(self, method: str, endpoint: str, **kwargs):
        import requests
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
        print("[MCP] Warning: Using deprecated Connector. Please migrate to McpServerManager.")
        result = self._request("GET", "tools")
        if not result:
            return []
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
        print("[MCP] Warning: Using deprecated Connector. Please migrate to McpServerManager.")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return f"[Error] Invalid JSON arguments: {arguments}"
        result = self._request("POST", f"tools/{tool_name}", json={"arguments": arguments})
        if result is None:
            return f"[Error] Failed to call MCP tool '{tool_name}'"
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            if isinstance(content, list):
                return "\n".join(
                    item.get("text", str(item)) if isinstance(item, dict) else str(item)
                    for item in content
                )
            return str(content)
        return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)