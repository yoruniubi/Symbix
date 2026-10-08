import subprocess
import json
import threading
import queue
import uuid
import os
import shutil
from typing import Optional, Dict, List, Any

import httpx

_RUNNER_FALLBACKS = [
    {
        "names": ("npx", "npx.cmd", "npx.exe"),
        "bin": "Symbix_sdk/bun.exe",
        "prefix": ["x"],
        "strip": ["-y"],
        "check": "npx",
    },
    {
        # uvx 语义 = `uv tool run`:未装 uvx 时用 SDK 内置 uv.exe 模拟
        "names": ("uvx", "uvx.cmd", "uvx.exe"),
        "bin": "Symbix_sdk/uv.exe",
        "prefix": ["tool", "run"],
        "strip": [],
        "check": "uvx",
    },
]


def _resolve_sdk_exe(rel_path: str) -> Optional[str]:
    """定位 SDK 内置可执行文件(不在 PATH,用 resource 解析绝对路径)。"""
    try:
        from Symbix_sdk.resource_path import resource
        p = resource(rel_path)
    except Exception:
        return None
    if os.path.exists(str(p)):
        return str(p)
    return None


def resolve_stdio_runner(command: str, args: Optional[List[str]] = None) -> tuple[str, List[str]]:
    """解析 stdio MCP 的启动命令(统一运行时降级)。

    - `npx`(含 .cmd/.exe 变体):系统无 npx 时降级 SDK 内置
      bun.exe 的 bunx 语义(`bun x <pkg>`,并剥掉 npx 专属 -y);
    - `uvx`(含变体):系统无 uvx 时降级 SDK 内置 uv.exe 的
      `uv tool run <pkg>`(uvx 等价命令);
    - 其它命令或系统已有对应 CLI:原样返回,绝不误改。

    返回 (command, args)。
    """
    base = os.path.basename((command or "").strip()).lower()
    args = list(args or [])
    for spec in _RUNNER_FALLBACKS:
        if base not in spec["names"]:
            continue
        if shutil.which(spec["check"]):
            return command, args
        exe = _resolve_sdk_exe(spec["bin"])
        if exe:
            cleaned = [a for a in args if a not in spec["strip"]]
            return exe, spec["prefix"] + cleaned
        return command, args  # SDK 也没有 → 保留原命令,让报错自然暴露
    return command, args


class McpServerClient:
    """通过 stdio 与 MCP server 通信的客户端"""

    transport = "stdio"

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
        self.last_error: Optional[str] = None

    def start(self):
        """启动 MCP server 进程"""
        import sys
        # npx fallback → SDK 内置 bun.exe x(系统没 node 但捆绑了 bun 时生效)
        resolved_cmd, resolved_args = resolve_stdio_runner(self.command, self.args)
        effective = resolved_cmd or self.command
        eff_args = resolved_args if resolved_cmd != self.command else self.args
        if effective != self.command:
            print(f"[MCP] '{self.server_id}': 未检测到 npx,使用 '{effective}' 替代")
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
                # Windows shlex.quote 不可靠,手动给含空格的参数加双引号
                cmd_str = effective + " " + " ".join(
                    f'"{a}"' if " " in a else a for a in eff_args
                )
                self.process = subprocess.Popen(cmd_str, shell=True, **popen_kwargs)
            else:
                self.process = subprocess.Popen(
                    [effective] + eff_args, **popen_kwargs
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
            self.last_error = str(e)
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
        # 兼容上游传入字符串（模型有时把 arguments 当字符串下）。
        # @modelcontextprotocol/sdk 用 zod 校验时"expected record received string"。
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                return f"[Error] Invalid JSON arguments for tool '{tool_name}': {arguments!r}"
        if arguments is None:
            arguments = {}
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
                except Exception:
                    pass


class McpRemoteClient:
    """通过 HTTP / SSE URL 与远程 MCP server 通信的客户端。

    兼容两类远程服务:
    1. 直接 JSON-RPC HTTP POST(url 接收 initialize / tools/*)
    2. SSE 传输:先 GET 建立 SSE,从 event: endpoint 拿到 POST 地址

    OAuth:当 allow_oauth=True 时,若服务返回 401 且无有效 Bearer,
    会尝试 OAuth 浏览器授权(playwright Edge)获取 token 后重试。
    注意:OAuth 需要用户操作浏览器,是阻塞等待,调用方应确保在后台线程执行。
    """

    transport = "remote"

    def __init__(
        self,
        server_id: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        transport: str = "sse",
        allow_oauth: bool = False,
        oauth_store=None,
        oauth_status_cb: Optional[callable] = None,
        oauth_no_browser: bool = False,
    ):
        self.server_id = server_id
        self.url = (url or "").rstrip("/")
        self.headers = dict(headers or {})
        self.transport_hint = (transport or "sse").lower().replace("_", "-")
        self.allow_oauth = allow_oauth
        self.oauth_store = oauth_store
        self.oauth_status_cb = oauth_status_cb
        self.oauth_no_browser = oauth_no_browser
        self._tools_cache: Optional[List[dict]] = None
        self._message_url: Optional[str] = None
        self._session_id: Optional[str] = None
        self._stop_event = threading.Event()
        self._sse_thread: Optional[threading.Thread] = None
        self._client: Optional[httpx.Client] = None
        self.last_error: Optional[str] = None
        self.oauth_triggered = False

    def start(self) -> bool:
        if not self.url:
            self.last_error = "远程 MCP URL 为空"
            return False
        try:
            self._client = httpx.Client(timeout=30.0, follow_redirects=True)
            if self.transport_hint in ("http", "streamable-http", "jsonrpc"):
                ok = self._initialize_http()
            else:
                ok = self._initialize_sse() or self._initialize_http()
            # OAuth:若连接失败且是鉴权问题,尝试浏览器授权后重连
            if not ok and self.allow_oauth and self._looks_like_auth_error():
                token = self._try_oauth()
                if token:
                    # 带上 token 重试
                    self.headers.setdefault("Authorization", f"Bearer {token}")
                    print(f"[MCP] OAuth 授权成功,重试连接 '{self.server_id}'")
                    try:
                        self._client.close()
                    except Exception:
                        pass
                    self._client = httpx.Client(timeout=30.0, follow_redirects=True)
                    if self.transport_hint in ("http", "streamable-http", "jsonrpc"):
                        ok = self._initialize_http()
                    else:
                        ok = self._initialize_sse() or self._initialize_http()
            if ok:
                print(f"[MCP] Remote server '{self.server_id}' connected: {self.url}")
            return ok
        except Exception as e:
            self.last_error = str(e)
            print(f"[MCP] Failed to connect remote server '{self.server_id}': {e}")
            self.stop()
            return False

    def _looks_like_auth_error(self) -> bool:
        """判断 last_error 是否属于需要 OAuth 的鉴权类错误。"""
        msg = (self.last_error or "").lower()
        return (
            "401" in msg
            or "unauthorized" in msg
            or "403" in msg
            or "authentication" in msg
            or "oauth" in msg
        )

    def _try_oauth(self) -> Optional[str]:
        """触发 OAuth 浏览器授权,返回 access_token(失败 None)。"""
        if self.oauth_status_cb:
            self.oauth_status_cb("authorizing")
        try:
            from Symbix_sdk.mcp.oauth import ensure_oauth_token, TokenStore

            store = self.oauth_store
            if store is None:
                # 默认存储位置
                import os

                base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                store = TokenStore(os.path.join(base, "config", "mcp_oauth.json"))
                self.oauth_store = store
            token = ensure_oauth_token(
                server_id=self.server_id,
                url=self.url,
                token_store=store,
                on_status=self.oauth_status_cb,
                no_browser=getattr(self, "oauth_no_browser", False),
            )
            if token:
                self.oauth_triggered = True
            return token
        except Exception as e:
            self.last_error = f"OAuth 授权失败: {e}"
            print(f"[MCP] OAuth failed for '{self.server_id}': {e}")
            if self.oauth_status_cb:
                self.oauth_status_cb("error")
            return None

    def _build_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        headers.update(self.headers)
        if extra:
            headers.update(extra)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _initialize_payload(self) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}},
                "clientInfo": {"name": "symbix-client", "version": "1.0.0"},
            },
        }

    def _initialize_http(self) -> bool:
        """直接向 URL POST JSON-RPC。"""
        assert self._client is not None
        self._message_url = self.url
        resp = self._client.post(
            self._message_url,
            headers=self._build_headers(),
            json=self._initialize_payload(),
        )
        if resp.status_code >= 400:
            self.last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            return False
        self._session_id = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
        # 某些服务可能返回 SSE 风格正文，这里尽量解析
        try:
            data = resp.json()
            if isinstance(data, dict) and data.get("error"):
                self.last_error = str(data["error"])
                return False
        except Exception:
            pass
        # 通知已初始化（可忽略失败）
        try:
            self._client.post(
                self._message_url,
                headers=self._build_headers(),
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
        except Exception:
            pass
        return True

    def _initialize_sse(self) -> bool:
        """尝试 SSE 握手：GET url，读取 endpoint 事件。"""
        assert self._client is not None
        try:
            with self._client.stream(
                "GET",
                self.url,
                headers=self._build_headers({"Accept": "text/event-stream"}),
                timeout=20.0,
            ) as resp:
                if resp.status_code >= 400:
                    self.last_error = f"SSE HTTP {resp.status_code}"
                    return False
                event_name = "message"
                data_lines: List[str] = []
                for raw in resp.iter_lines():
                    if raw is None:
                        continue
                    line = raw.strip("\r")
                    if line.startswith(":"):
                        continue
                    if not line:
                        if data_lines:
                            payload = "\n".join(data_lines)
                            data_lines = []
                            if event_name == "endpoint" or payload.startswith("/"):
                                endpoint = payload.strip()
                                if endpoint.startswith("http"):
                                    self._message_url = endpoint
                                else:
                                    # 相对路径
                                    base = self.url
                                    if endpoint.startswith("/"):
                                        # 取 origin
                                        from urllib.parse import urlparse
                                        p = urlparse(self.url)
                                        self._message_url = f"{p.scheme}://{p.netloc}{endpoint}"
                                    else:
                                        self._message_url = f"{base.rstrip('/')}/{endpoint}"
                                break
                            if event_name == "message":
                                try:
                                    msg = json.loads(payload)
                                    if msg.get("result") is not None or msg.get("error"):
                                        # 某些实现会直接推送
                                        pass
                                except Exception:
                                    pass
                        event_name = "message"
                        continue
                    if line.startswith("event:"):
                        event_name = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                    # 限时：拿到 endpoint 就结束读取循环
                    if self._message_url:
                        break
        except Exception as e:
            self.last_error = f"SSE connect failed: {e}"
            return False

        if not self._message_url:
            # 没有 endpoint 事件时，退回直接 POST 原 URL
            self._message_url = self.url

        # 初始化
        try:
            resp = self._client.post(
                self._message_url,
                headers=self._build_headers(),
                json=self._initialize_payload(),
            )
            if resp.status_code >= 400:
                self.last_error = f"Init HTTP {resp.status_code}: {resp.text[:300]}"
                return False
            self._session_id = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
            try:
                self._client.post(
                    self._message_url,
                    headers=self._build_headers(),
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                )
            except Exception:
                pass
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def _send_request(self, request: dict) -> dict:
        if not self._client or not self._message_url:
            return {"error": {"code": -32603, "message": "Remote client not connected"}}
        try:
            resp = self._client.post(
                self._message_url,
                headers=self._build_headers(),
                json=request,
                timeout=60.0,
            )
            if resp.status_code >= 400:
                return {
                    "error": {
                        "code": -32603,
                        "message": f"HTTP {resp.status_code}: {resp.text[:300]}",
                    }
                }
            # 可能是纯 JSON 或 SSE 包裹
            text = resp.text.strip()
            if text.startswith("event:") or "\ndata:" in text:
                for block in text.split("\n\n"):
                    for line in block.splitlines():
                        if line.startswith("data:"):
                            payload = line[5:].strip()
                            if payload:
                                try:
                                    return json.loads(payload)
                                except Exception:
                                    continue
            return resp.json()
        except Exception as e:
            return {"error": {"code": -32603, "message": str(e)}}

    def list_tools(self) -> List[dict]:
        if self._tools_cache is not None:
            return self._tools_cache
        try:
            response = self._send_request({
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/list",
            })
            if "error" in response:
                print(f"[MCP] Remote list tools error: {response['error']}")
                self.last_error = str(response["error"])
                return []
            tools = response.get("result", {}).get("tools", [])
            self._tools_cache = tools
            return tools
        except Exception as e:
            self.last_error = str(e)
            print(f"[MCP] Remote list tools exception: {e}")
            return []

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        # 与 stdio 客户端一样：上游仍可能传 string，给 MCP server 之前先转 dict。
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                return f"[Error] Invalid JSON arguments for tool '{tool_name}': {arguments!r}"
        if arguments is None:
            arguments = {}
        try:
            response = self._send_request({
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments or {}},
            })
            if "error" in response:
                return f"[Error] {response['error'].get('message', response['error'])}"
            result = response.get("result", {})
            content = result.get("content", [])
            output_parts = []
            for item in content:
                if isinstance(item, dict):
                    if "text" in item:
                        output_parts.append(item["text"])
                    elif item.get("type") == "image":
                        output_parts.append(f"[Image: {str(item.get('data', ''))[:50]}...]")
                    else:
                        output_parts.append(json.dumps(item, ensure_ascii=False))
                else:
                    output_parts.append(str(item))
            return "\n".join(output_parts) if output_parts else json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return f"[Error] Exception calling remote tool: {e}"

    def stop(self):
        self._stop_event.set()
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None


class McpServerManager:
    """管理多个 MCP server 客户端(stdio + remote)"""

    def __init__(self):
        self.servers: Dict[str, Any] = {}
        self._initialized = False
        # 最近一次 add_* 失败的原因(供上层判断是否需 OAuth 等)
        self.last_error: Optional[str] = None

    def add_server(self, server_id: str, command: str, args: List[str]) -> bool:
        """添加并启动本地 stdio MCP server"""
        if server_id in self.servers:
            print(f"[MCP] Server '{server_id}' already exists, replacing")
            self.remove_server(server_id)

        client = McpServerClient(server_id, command, args)
        ok = client.start()
        self.last_error = getattr(client, "last_error", None)
        if ok:
            self.servers[server_id] = client
        return ok

    def add_remote_server(
        self,
        server_id: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        transport: str = "sse",
        allow_oauth: bool = False,
        oauth_store=None,
        oauth_status_cb: Optional[callable] = None,
        oauth_no_browser: bool = False,
    ) -> bool:
        """添加并连接远程 MCP server"""
        if server_id in self.servers:
            print(f"[MCP] Server '{server_id}' already exists, replacing")
            self.remove_server(server_id)

        client = McpRemoteClient(
            server_id,
            url,
            headers=headers,
            transport=transport,
            allow_oauth=allow_oauth,
            oauth_store=oauth_store,
            oauth_status_cb=oauth_status_cb,
            oauth_no_browser=oauth_no_browser,
        )
        ok = client.start()
        self.last_error = getattr(client, "last_error", None)
        if ok:
            self.servers[server_id] = client
        return ok

    def add_from_config(self, server_id: str, config: dict) -> bool:
        """根据配置自动选择 stdio / remote"""
        if not isinstance(config, dict):
            return False
        url = config.get("url") or config.get("serverUrl")
        if url:
            headers = dict(config.get("headers") or {})
            transport = config.get("transport") or config.get("type") or "sse"
            # 兼容两种 api_key 来源:
            # 1) config 内直接带 api_key 字段(raw JSON 粘贴模式)
            # 2) 顶层 mcp_api_key 集中存放(调用方在 config 里塞入 api_key 字段)
            api_key = config.get("api_key") or config.get("mcp_api_key")
            if api_key and not headers.get("Authorization"):
                headers["Authorization"] = f"Bearer {api_key}"
            allow_oauth = bool(config.get("oauth") or config.get("allow_oauth"))
            oauth_store = config.get("oauth_store")
            oauth_status_cb = config.get("oauth_status_cb")
            oauth_no_browser = bool(config.get("oauth_no_browser_on_start"))
            return self.add_remote_server(
                server_id,
                url,
                headers=headers,
                transport=str(transport),
                allow_oauth=allow_oauth,
                oauth_store=oauth_store,
                oauth_status_cb=oauth_status_cb,
                oauth_no_browser=oauth_no_browser,
            )
        command = config.get("command")
        args = config.get("args") or []
        if command:
            return self.add_server(server_id, command, args)
        return False

    def remove_server(self, server_id: str):
        """移除 MCP server"""
        if server_id in self.servers:
            self.servers[server_id].stop()
            del self.servers[server_id]
    
    def list_tools_as_openai_format(self) -> List[dict]:
        """获取所有服务器的工具并转换为 OpenAI 格式

        对 MCP server 返回的 inputSchema 做清洗,确保符合 OpenAI 的工具 schema 要求:
        - 必须是 {"type": "object", ...}
        - 过滤掉 OpenAI 不识别的 JSON Schema 元字段($schema, $defs, $ref 等)

        扩展字段(供风险分级使用,不传给模型):
        - `_mcp_server_id`: 来源 server(风险分级用复合 key)
        - `_mcp_annotations`: MCP 原始 annotations(仅 trusted server 采信,见 risk_classifier)
        """
        openai_tools = []

        for server_id, client in self.servers.items():
            tools = client.list_tools()
            for tool in tools:
                name = tool.get("name", "")
                if not name:
                    continue
                schema = self._sanitize_schema(tool.get("inputSchema"))
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.get("description", ""),
                        "parameters": schema,
                    },
                    # 扩展:风险分级元数据(不进入 OpenAI 参数)
                    "_mcp_server_id": server_id,
                    "_mcp_annotations": tool.get("annotations") or {},
                })

        return openai_tools

    @staticmethod
    def _sanitize_schema(raw) -> dict:
        """清洗 MCP inputSchema，保证符合 OpenAI function calling 要求"""
        if not isinstance(raw, dict):
            return {"type": "object", "properties": {}}

        # 顶层必须是 object；否则退化成空 object schema
        if raw.get("type") != "object":
            return {"type": "object", "properties": {}}

        cleaned = {"type": "object"}
        properties = raw.get("properties")
        if isinstance(properties, dict) and properties:
            cleaned_props = {}
            for prop_name, prop_schema in properties.items():
                if not isinstance(prop_schema, dict):
                    continue
                # 过滤掉 OpenAI 不识别的 $ 开头元字段
                clean_prop = {
                    k: v for k, v in prop_schema.items()
                    if not k.startswith("$")
                }
                if "type" in clean_prop or "anyOf" in clean_prop or "oneOf" in clean_prop:
                    cleaned_props[prop_name] = clean_prop
                else:
                    # 至少给个 type 兜底
                    cleaned_props[prop_name] = {"type": "string", **clean_prop}
            cleaned["properties"] = cleaned_props
        else:
            cleaned["properties"] = {}

        required = raw.get("required")
        if isinstance(required, list):
            cleaned["required"] = [r for r in required if isinstance(r, str)]

        return cleaned
    
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