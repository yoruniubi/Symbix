import subprocess
import json
import sys
import threading
import queue
import time
import uuid
import os
import shutil
from pathlib import Path
from collections import deque
from typing import Optional, Dict, List, Any

import httpx

from Symbix_sdk.resource_path import resource

# MCP 图片内容落盘目录(Symbix_sdk/mcp/previews/)。
# 和 memory.db 一样跟着 SDK 目录走:源码态在 backend/ 下,冻结态在
# _internal/Symbix_sdk/mcp/ 下,都可写。
_PREVIEW_DIR = Path(__file__).resolve().parent / "previews"
_PREVIEW_KEEP = 50                    # 最多留多少张,超出按 mtime 清最旧
_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}


def _save_image_preview(data_b64: str, mime: str) -> Optional[str]:
    """把 MCP 返回的 image content(base64)落盘,返回绝对路径;失败返回 None。

    MCP 的图片内容原来被截成 `[Image: <50字符>...]` —— 模型看不到图、
    前端也没法渲染。落盘后:
    - 模型拿到路径,可以在回复里告诉用户「预览已存到 xxx」;
    - 前端从工具输出里抽出路径,经 /api/files/raw 渲染成真图。
    """
    import base64
    import time as _time
    try:
        raw = base64.b64decode(str(data_b64 or ""), validate=False)
        if not raw:
            return None
        _PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        ext = _MIME_EXT.get(str(mime or "image/png").lower(), ".png")
        path = _PREVIEW_DIR / f"mcpimg_{int(_time.time() * 1000)}_{uuid.uuid4().hex[:6]}{ext}"
        path.write_bytes(raw)
        # 只留最近 _PREVIEW_KEEP 张,防无限增长
        try:
            olds = sorted(_PREVIEW_DIR.glob("mcpimg_*"), key=lambda p: p.stat().st_mtime)
            for old in olds[:-_PREVIEW_KEEP]:
                old.unlink(missing_ok=True)
        except OSError:
            pass
        return str(path)
    except Exception:
        return None


_RUNNER_FALLBACKS = [
    {
        "names": ("npx", "npx.cmd", "npx.exe"),
        "bin": "Symbix_sdk/bun",      # 平台后缀由 sdk_binary() 处理
        "prefix": ["x"],
        "strip": ["-y"],
        "check": "npx",
    },
    {
        # uvx 语义 = `uv tool run`:未装 uvx 时用 SDK 内置 uv.exe 模拟
        "names": ("uvx", "uvx.cmd", "uvx.exe"),
        "bin": "Symbix_sdk/uv",       # 同上
        "prefix": ["tool", "run"],
        "strip": [],
        "check": "uvx",
    },
]


def _resolve_sdk_exe(rel_path: str) -> Optional[str]:
    """定位 SDK 内置可执行文件(不在 PATH,用 resource 解析绝对路径)。

    rel_path 不带 .exe 后缀(Windows 由 sdk_binary 补,见 resource_path.sdk_binary)。
    """
    try:
        from Symbix_sdk.resource_path import resource, sdk_binary
        p = sdk_binary(rel_path)
    except Exception:
        return None
    if os.path.exists(str(p)):
        return str(p)
    return None


def resolve_stdio_runner(command: str, args: Optional[List[str]] = None) -> tuple[str, List[str]]:
    """解析 stdio MCP 的启动命令(统一运行时降级)。

    - 相对路径可执行文件(如 `pixeldraw.exe`):依次在系统 PATH、
      资源目录 `pixeldraw/`(内置 MCP 工具的约定位置)里找,找到则
      替换为绝对路径 —— 子进程 cwd 不一定是资源目录,裸命令名会找不到;
    - `npx`(含 .cmd/.exe 变体):系统无 npx 时降级 SDK 内置
      bun.exe 的 bunx 语义(`bun x <pkg>`,并剥掉 npx 专属 -y);
    - `uvx`(含变体):系统无 uvx 时降级 SDK 内置 uv.exe 的
      `uv tool run <pkg>`(uvx 等价命令);
    - 其它命令或系统已有对应 CLI:原样返回,绝不误改。

    返回 (command, args)。
    """
    base = os.path.basename((command or "").strip()).lower()
    args = list(args or [])
    # 内置相对路径可执行文件 → 解析为绝对路径(优先 PATH,再资源目录)
    raw = (command or "").strip()
    if base.endswith(".exe") and not os.path.isabs(raw) and os.sep not in raw and "/" not in raw:
        if not shutil.which(raw):
            bundled = resource("pixeldraw") / base
            if bundled.exists():
                return str(bundled), args
        # PATH 没有且资源目录也没有 → 原样返回,让报错自然暴露
        return command, args
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


# 首次启动可能要下载包的 runner:握手超时得放宽,否则「第一次连不上、点重连才好」。
# 实测 `npx @playwright/mcp@latest` 冷启动(要解析并下载新版本)会超过 30 秒。
_SLOW_START_COMMANDS = {
    "npx", "npx.cmd", "npx.exe", "npm", "npm.cmd",
    "uvx", "uvx.cmd", "uvx.exe",
    "bun", "bun.exe", "bunx", "bunx.exe",
}


class McpServerClient:
    """通过 stdio 与 MCP server 通信的客户端"""

    transport = "stdio"

    #: 单次请求等待上限(秒)
    timeout: float = 30
    #: 握手(initialize)等待上限:runner 冷启动要下载包,start() 里会按命令名放宽到 120s
    _start_timeout: float = 30.0
    #: stderr 最多打印多少行,避免下载日志刷屏(超出部分仍留在尾部供诊断)
    _stderr_print_limit = 50
    #: list_tools 失败后的冷却时间(秒),期内不重试
    _fail_cooldown = 60

    def __init__(self, server_id: str, command: str, args: List[str]):
        self.server_id = server_id
        self.command = command
        self.args = args
        self.process: Optional[subprocess.Popen] = None
        self.request_queue = queue.Queue()
        self.response_map: Dict[str, queue.Queue] = {}
        self._stop_event = threading.Event()
        self._reader_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        #: stderr 末尾若干行,超时/异常时拼进错误信息便于定位
        self._stderr_tail: deque = deque(maxlen=20)
        self._stderr_printed = 0
        self._fail_until = 0.0
        #: stdout 读线程若异常退出,后续请求要立刻报错而不是干等超时
        self._reader_error: Optional[str] = None
        self._tools_cache: Optional[List[dict]] = None
        self.last_error: Optional[str] = None

    def start(self):
        """启动 MCP server 进程"""
        # npx fallback → SDK 内置 bun.exe x(系统没 node 但捆绑了 bun 时生效)
        resolved_cmd, resolved_args = resolve_stdio_runner(self.command, self.args)
        effective = resolved_cmd or self.command
        eff_args = resolved_args if resolved_cmd != self.command else self.args
        if effective != self.command and not effective.endswith(".exe"):
            print(f"[MCP] '{self.server_id}': 未检测到 npx,使用 '{effective}' 替代")
        if os.path.basename(str(effective).lower()) in _SLOW_START_COMMANDS:
            # npx/uvx/bun x 首次要拉包:30 秒不够,放宽到 120 秒
            self._start_timeout = 120.0
        try:
            # Windows 下 npx/npm 等是 .cmd 脚本，需要 shell=True 才能找到
            use_shell = sys.platform == "win32"
            popen_kwargs = dict(
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # MCP 协议固定 UTF-8。不显式指定的话 Windows 会用 locale
                # 编码(GBK)解码,只要 server 回包里有一个非 ASCII 字符就会
                # UnicodeDecodeError → 读线程挂掉 → 响应没人收 → tools/list 超时。
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=0,
            )
            if use_shell:
                # 用 list2cmdline 按 Windows 规则转义。手写"含空格就加引号"会被
                # 参数内部的引号/反斜杠搞坏(例如 python -c "<json>" 这种)。
                cmd_str = subprocess.list2cmdline([effective] + eff_args)
                self.process = subprocess.Popen(cmd_str, shell=True, **popen_kwargs)
            else:
                self.process = subprocess.Popen(
                    [effective] + eff_args, **popen_kwargs
                )

            # 启动读取线程。stderr 必须一并读走:管道缓冲区有限,npx/uvx/node
            # 的日志写满后子进程会阻塞在 write 上,再也无法响应 JSON-RPC。
            self._reader_thread = threading.Thread(
                target=self._read_output,
                daemon=True
            )
            self._reader_thread.start()
            self._stderr_thread = threading.Thread(
                target=self._read_stderr,
                daemon=True
            )
            self._stderr_thread.start()

            # 初始化握手
            resp = self._send_request({
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
            }, timeout=self._start_timeout)
            if "error" in resp:
                # 握手失败就别登记成"启动成功",否则用户看到添加成功、
                # 列表却一直超时。
                self.last_error = str(resp["error"])
                if "timeout" in str(resp["error"]).lower() and self._start_timeout > self.timeout:
                    self.last_error += (
                        f"(握手等待超过 {int(self._start_timeout)} 秒。首次启动要下载包,"
                        "网络慢时可稍后点重连)"
                    )
                print(f"[MCP] Server '{self.server_id}' 初始化失败: {self.last_error}")
                self.stop()
                return False

            # MCP 规范要求:收到 initialize 响应后必须补发 initialized 通知。
            # 基于官方 Python SDK 的 server 在收到它之前会拒绝 tools/list。
            self._notify_initialized()

            print(f"[MCP] Server '{self.server_id}' started successfully")
            return True

        except Exception as e:
            self.last_error = str(e)
            print(f"[MCP] Failed to start server '{self.server_id}': {e}")
            self.stop()
            return False

    def _read_stderr(self):
        """持续读走 stderr(保留末尾若干行用于报错诊断)。

        不读的话子进程日志会写满管道缓冲区并被阻塞,这是 stdio MCP
        "添加后 list tools 超时"的直接原因。
        """
        try:
            for line in iter(self.process.stderr.readline, ""):
                if self._stop_event.is_set():
                    break
                line = line.rstrip()
                if not line:
                    continue
                self._stderr_tail.append(line)
                self._stderr_printed += 1
                if self._stderr_printed <= self._stderr_print_limit:
                    print(f"[MCP:{self.server_id}] {line}")
                elif self._stderr_printed == self._stderr_print_limit + 1:
                    print(f"[MCP:{self.server_id}] ...(stderr 输出过多已省略,报错时会附末尾几行)")
        except Exception:
            pass

    def _stderr_hint(self) -> str:
        """把 stderr 末尾拼进错误信息,便于判断是代理、包名还是权限问题。"""
        tail = [ln for ln in list(self._stderr_tail)[-5:] if ln]
        if not tail:
            return ""
        return " | stderr: " + " / ".join(tail)

    def _notify_initialized(self):
        """补发 notifications/initialized(MCP 握手第三步,无 id 不等待响应)。"""
        try:
            message = json.dumps({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }) + "\n"
            self.process.stdin.write(message)
            self.process.stdin.flush()
        except Exception as e:
            print(f"[MCP] '{self.server_id}': 发送 initialized 通知失败: {e}")

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
                # 记录下来:读线程死了的话后面所有请求都会"凭空"超时,
                # 必须让调用方看到真实原因。
                self._reader_error = str(e)
                if not self._stop_event.is_set():
                    print(f"[MCP] Error reading output: {e}")
                break

    def _send_request(self, request: dict, timeout: Optional[float] = None) -> dict:
        """发送请求并等待响应(timeout 缺省用 self.timeout)"""
        request_id = request["id"]
        response_queue = queue.Queue()
        self.response_map[request_id] = response_queue

        try:
            # 发送请求
            message = json.dumps(request) + "\n"
            self.process.stdin.write(message)
            self.process.stdin.flush()

            # 分片轮询:既能等响应,又能在子进程已死时立刻失败,
            # 而不是干等满超时(否则一次失败要卡 30 秒)。
            deadline = time.time() + (timeout if timeout else self.timeout)
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return {"error": {
                        "code": -32603,
                        "message": "Request timeout" + self._stderr_hint(),
                    }}
                try:
                    return response_queue.get(timeout=min(0.2, remaining))
                except queue.Empty:
                    if self._reader_error:
                        return {"error": {
                            "code": -32603,
                            "message": "Response reader died: " + self._reader_error,
                        }}
                    code = self.process.poll()
                    if code is not None:
                        return {"error": {
                            "code": -32603,
                            "message": f"Server exited (code {code})"
                                       + self._stderr_hint(),
                        }}

        finally:
            # 清理响应映射
            self.response_map.pop(request_id, None)

    def list_tools(self) -> List[dict]:
        """获取工具列表(失败后冷却期内不重试)"""
        if self._tools_cache is not None:
            return self._tools_cache

        # 刚失败过就直接返回空:否则每一轮对话(都要列工具)都会再等一整个超时
        if time.time() < self._fail_until:
            return []

        try:
            response = self._send_request({
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/list"
            })

            if "error" in response:
                print(f"[MCP] Error listing tools: {response['error']}")
                self._fail_until = time.time() + self._fail_cooldown
                return []

            tools = response.get("result", {}).get("tools", [])
            self._tools_cache = tools
            return tools

        except Exception as e:
            print(f"[MCP] Exception listing tools: {e}")
            self._fail_until = time.time() + self._fail_cooldown
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
                        saved = _save_image_preview(item.get("data", ""), item.get("mimeType", ""))
                        output_parts.append(f"[Image saved: {saved}]" if saved else "[Image: <保存失败>]")
                else:
                    output_parts.append(str(item))

            return "\n".join(output_parts)

        except Exception as e:
            return f"[Error] Exception calling tool: {e}"

    def stop(self):
        """停止 MCP server(Windows 下连子进程树一起结束)"""
        self._stop_event.set()
        proc = self.process
        if not proc:
            return
        try:
            if sys.platform == "win32":
                # shell=True 时 pid 是 cmd.exe,真正的 node/npx 是它的子进程;
                # 只 terminate 外层会留下孤儿进程(表现为后端退不干净)。
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=5,
                )
            else:
                proc.terminate()
                proc.wait(timeout=5)
        except Exception as e:
            print(f"[MCP] Error stopping server: {e}")
            try:
                proc.kill()
            except Exception:
                pass
        finally:
            self.process = None
            # 关掉管道,让阻塞在 readline 上的读取线程退出
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream:
                        stream.close()
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
                        saved = _save_image_preview(item.get("data", ""), item.get("mimeType", ""))
                        output_parts.append(f"[Image saved: {saved}]" if saved else "[Image: <保存失败>]")
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


# browser_* 工具的参数里可能是本地路径(模型想把上传的图片「打开看看」),
# playwright 会直接拦掉 file:// 并返回一句英文报错,模型往往又试一次。
# 这里提前挡掉并给出正确做法,省一轮审批 + 一轮无效重试。
_LOCAL_REF_KEYS = ("url", "path", "file", "filepath", "filename")
_BROWSER_LOCAL_HINT = (
    "[Error] browser_* 工具只能访问 http/https 网页,不支持 file:// 或本地文件路径。"
    "本地文件请用 read_file / parse_file;图片内容无法用文本工具读取,"
    "请基于本轮已提供的视觉输入,或请用户用文字描述(不要反复尝试打开本地图片)。"
)


def _is_local_reference(value: str) -> bool:
    v = value.strip()
    if v.lower().startswith("file:"):
        return True
    if len(v) > 2 and v[1] == ":" and v[0].isalpha() and v[2] in "\\/":
        return True  # F:\... / F:/...
    return v.startswith("/") and not v.startswith("//")


def _guard_local_path_call(tool_name: str, arguments) -> Optional[str]:
    """拦住 browser_* 的本地路径调用,返回给模型的提示;不该拦则返回 None。"""
    if not tool_name.startswith("browser_") or not isinstance(arguments, dict):
        return None
    for key in _LOCAL_REF_KEYS:
        val = arguments.get(key)
        if isinstance(val, str) and _is_local_reference(val):
            print(f"[mcp] 拦截 {tool_name} 的本地路径参数 {key}={val[:120]!r}")
            return _BROWSER_LOCAL_HINT
    return None


def _tool_desc_hint(name: str) -> str:
    """给 MCP 工具描述补一句边界说明(描述由上游 server 提供,不能直接改)。"""
    if name == "browser_navigate":
        return (
            " 仅支持 http/https 网页;不要传本地路径或 file:// 地址(浏览器策略会拦掉),"
            "本地文件请用 read_file/parse_file;抓取静态网页正文优先用 fetch_webpage。"
        )
    if name.startswith("browser_"):
        return " 仅用于真实网站(http/https),不能读写本地文件;静态内容优先用 fetch_webpage。"
    return ""


class McpServerManager:
    """管理多个 MCP server 客户端(stdio + remote)"""

    def __init__(self):
        self.servers: Dict[str, Any] = {}
        self._initialized = False
        # 最近一次 add_* 失败的原因(供上层判断是否需 OAuth 等)
        self.last_error: Optional[str] = None
        # 启动失败的 server → 失败原因。列表接口要把原因透给前端,
        # 否则面板只显示「未连接」,用户完全不知道是超时、缺 npx 还是端口占用。
        self.failed: Dict[str, str] = {}
        # 正在握手的 server:面板据此显示「连接中」而不是「未连接」
        self.starting: set = set()

    def add_server(self, server_id: str, command: str, args: List[str]) -> bool:
        """添加并启动本地 stdio MCP server"""
        if server_id in self.servers:
            print(f"[MCP] Server '{server_id}' already exists, replacing")
            self.remove_server(server_id)

        client = McpServerClient(server_id, command, args)
        self.starting.add(server_id)
        try:
            ok = client.start()
        finally:
            self.starting.discard(server_id)
        self.last_error = getattr(client, "last_error", None)
        if ok:
            self.servers[server_id] = client
            self.failed.pop(server_id, None)
        else:
            self.failed[server_id] = str(self.last_error or "启动失败")
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
        self.starting.add(server_id)
        try:
            ok = client.start()
        finally:
            self.starting.discard(server_id)
        self.last_error = getattr(client, "last_error", None)
        if ok:
            self.servers[server_id] = client
            self.failed.pop(server_id, None)
        else:
            self.failed[server_id] = str(self.last_error or "启动失败")
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
        """移除 MCP server(顺手清掉它的失败记录,免得面板一直挂着旧原因)"""
        self.failed.pop(server_id, None)
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

        for server_id, client in list(self.servers.items()):
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
                        "description": tool.get("description", "") + _tool_desc_hint(name),
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
        blocked = _guard_local_path_call(tool_name, arguments)
        if blocked:
            return blocked
        # 遍历所有服务器查找工具(快照迭代:面板可能并发增删)
        for server_id, client in list(self.servers.items()):
            tools = client.list_tools()
            for tool in tools:
                if tool.get("name") == tool_name:
                    return client.call_tool(tool_name, arguments)

        return f"[Error] Tool '{tool_name}' not found in any MCP server"

    def stop_all(self):
        """停止所有服务器"""
        for client in list(self.servers.values()):
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