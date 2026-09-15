from __future__ import annotations
import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Optional
from urllib.parse import parse_qs, urlparse
from urllib.parse import urlencode

if TYPE_CHECKING:
    # 仅供类型检查使用,不影响运行时逻辑
    from mcp.shared.auth import (
        AuthorizationCodeResult,
        OAuthClientMetadata,
        OAuthClientInformationFull,
        OAuthToken,
    )

# mcp SDK(httpx2 生态,与项目内 httpx 完全共存)
try:
    import httpx2
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import (
        AuthorizationCodeResult,
        OAuthClientMetadata,
        OAuthClientInformationFull,
        OAuthToken,
    )
    _MCP_SDK_AVAILABLE = True
except Exception:  # pragma: no cover - 依赖缺失时降级
    httpx2 = None
    OAuthClientProvider = None
    if not TYPE_CHECKING:
        AuthorizationCodeResult = None
        OAuthClientMetadata = None
        OAuthClientInformationFull = None
        OAuthToken = None
    _MCP_SDK_AVAILABLE = False
# 浏览器授权:本地 HTTP 回调 + 系统默认浏览器(webbrowser.open),不依赖 playwright。

DEFAULT_CALLBACK_PORT = 38577
"""本地回调端口(固定端口,保证授权服务注册的 redirect_uri 稳定匹配)。"""

CALLBACK_PATH = "/mcp-oauth/callback"
"""本地回调路径。SDK 注册的 redirect_uri 为 http://127.0.0.1:<port><path>。"""


class TokenStore:
    """OAuth token 持久化文件(JSON)。

    文件结构(不入 git):
    {
      "<server_id>": {
        "tokens":     {...OAuthToken 字段...} | None,
        "client_info": {...OAuthClientInformationFull 字段...} | None,
        "updated_at": 1234567890.0
      }
    }
    """

    def __init__(self, path: str = "mcp_oauth.json"):
        self.path = os.path.abspath(path)
        self._lock = threading.RLock()
        self._data: dict = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
        if not isinstance(self._data, dict):
            self._data = {}

    def _save(self):
        dir_name = os.path.dirname(self.path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, self.path)

    # ---------- 同步访问(供主程序 / connector 使用) ----------
    def get_tokens_sync(self, server_id: str) -> dict | None:
        """返回该 server 的原始 token dict(无则 None)。"""
        with self._lock:
            ns = self._data.get(server_id)
            if not isinstance(ns, dict):
                return None
            tok = ns.get("tokens")
            return tok if isinstance(tok, dict) and tok.get("access_token") else None

    def has_valid_token(self, server_id: str) -> bool:
        """是否有未过期的 access_token(过期但可刷新也算有效,SDK 会自动刷新)。"""
        tok = self.get_tokens_sync(server_id)
        if not tok:
            return False
        # 有 refresh_token 或未设过期时间 -> 视为可自动续期
        if tok.get("refresh_token"):
            return True
        exp = tok.get("expires_at")
        if not exp:
            return True
        return float(exp) > time.time() + 30

    def get_access_token(self, server_id: str) -> str | None:
        """返回可用 access_token(有效或可刷新);否则 None。"""
        tok = self.get_tokens_sync(server_id)
        if not tok:
            return None
        at = tok.get("access_token")
        if not at:
            return None
        if tok.get("refresh_token"):
            return str(at)
        exp = tok.get("expires_at")
        if exp and float(exp) <= time.time() + 30:
            return None
        return str(at)

    def clear(self, server_id: str):
        """清除某 server 的 token(用于登出/删除 server)。"""
        with self._lock:
            if server_id in self._data:
                del self._data[server_id]
                self._save()

    def list_servers(self) -> list[str]:
        with self._lock:
            return [k for k, v in self._data.items() if isinstance(v, dict)]

    # ---------- async storage 工厂(SDK TokenStorage 协议) ----------
    def make_storage(self, server_id: str):
        """生成绑定到 server_id 的 async storage(供 OAuthClientProvider 使用)。"""
        return _AsyncStorage(self, server_id)


class _AsyncStorage:
    """绑定 server_id 的 SDK TokenStorage 协议实现(对象形式)。

    SDK 的 OAuthClientProvider 通过 context.storage.get_tokens() 等属性方法
    读取/写入 token,因此必须返回对象而非 dict。
    """

    def __init__(self, store: "TokenStore", server_id: str):
        self._store = store
        self._sid = server_id

    async def get_tokens(self):
        store, sid = self._store, self._sid
        with store._lock:
            ns = store._data.get(sid)
            if not isinstance(ns, dict) or not ns.get("tokens"):
                return None
            try:
                return OAuthToken.model_validate(ns["tokens"])
            except Exception:
                return None

    async def set_tokens(self, tokens):
        store, sid = self._store, self._sid
        with store._lock:
            ns = store._data.setdefault(sid, {})
            if tokens is None:
                ns["tokens"] = None
            else:
                d = tokens.model_dump(mode="json") if hasattr(tokens, "model_dump") else dict(tokens)
                # SDK 的 OAuthToken 无 expires_at 字段(只有 expires_in),这里补一个绝对时间
                d = dict(d)
                if "expires_in" in d and d.get("expires_in"):
                    d["expires_at"] = time.time() + float(d["expires_in"])
                ns["tokens"] = d
            ns["updated_at"] = time.time()
            store._save()

    async def get_client_info(self):
        store, sid = self._store, self._sid
        with store._lock:
            ns = store._data.get(sid)
            if not isinstance(ns, dict) or not ns.get("client_info"):
                return None
            try:
                return OAuthClientInformationFull.model_validate(ns["client_info"])
            except Exception:
                return None

    async def set_client_info(self, info):
        store, sid = self._store, self._sid
        with store._lock:
            ns = store._data.setdefault(sid, {})
            ns["client_info"] = (
                info.model_dump(mode="json") if hasattr(info, "model_dump") else dict(info)
            )
            ns["updated_at"] = time.time()
            store._save()


class OAuthBrowserHandler:
    """本地回调服务器 + 系统默认浏览器授权:打开用户默认浏览器,本地端口收 code。

    实现 SDK 的两个钩子:
      - redirect_handler(url): 起本地 HTTP 回调服务器 + webbrowser 打开授权 URL。
      - callback_handler():    等待用户完成登录后授权服务 redirect 回本地回调,返回 AuthorizationCodeResult。

    注意:SDK 的 async_auth_flow 是在 asyncio 事件循环里调这两个 async 钩子。
    本项目连接层是同步线程,因此用 run_coroutine_threadsafe 把调用桥接到
    运行 SDK 流程的 asyncio loop;回调服务器在独立线程执行。
    """

    def __init__(
        self,
        callback_port: int = DEFAULT_CALLBACK_PORT,
        headless: bool = False,
        timeout_seconds: int = 120,
        no_browser: bool = False,
    ):
        self.callback_port = callback_port
        self.headless = headless
        self.timeout_seconds = timeout_seconds
        # 启动期连接场景:true 时不弹浏览器、不启回调服务器,
        # 授权直接失败(等用户在面板手动授权),避免无人值守时后端弹窗。
        self.no_browser = no_browser
        self._result: Optional[AuthorizationCodeResult] = None
        self._error: Optional[str] = None
        self._state: Optional[str] = None
        self._done = threading.Event()
        self._httpd: Optional[ThreadingHTTPServer] = None

    # 供主程序查询状态(前端轮询)
    @property
    def status(self) -> str:
        if self._done.is_set():
            return "done" if self._error is None else f"error: {self._error}"
        return "waiting"

    def reset(self):
        self._result = None
        self._error = None
        self._state = None
        self._done = threading.Event()

    # ---------- SDK 钩子 ----------
    async def redirect_handler(self, authorization_url: str):
        """SDK 调用:打开系统默认浏览器导航到授权 URL,并在本地端口起 HTTP 回调服务。"""
        if self.no_browser:
            # 启动期静默降级:不弹浏览器、不开回调服务器,直接标记失败。
            print(f"[MCP OAuth] 启动期跳过浏览器授权(刷新失败需手动): {str(authorization_url)[:120]}")
            self._error = "OAuth 刷新失败,需在面板手动重新授权"
            self._done.set()
            return
        self.reset()
        url_str = str(authorization_url)
        # 记录 state(从 URL query 提取),用于校验回调
        q = parse_qs(urlparse(url_str).query)
        self._state = (q.get("state") or [None])[0]
        print(f"[MCP OAuth] 打开浏览器进行授权: {url_str[:160]}")
        # 回调接收与浏览器启动都在独立线程,避免阻塞 asyncio loop
        threading.Thread(
            target=self._run_callback_server, args=(url_str,), daemon=True
        ).start()

    def _run_callback_server(self, authorization_url: str):
        """启动本地 HTTP 回调服务 + 用系统默认浏览器打开授权页。

        授权服务器最终 redirect 回 http://127.0.0.1:<port>/mcp-oauth/callback?code=..,
        由本地 HTTP 服务接收并解析出 code/state。
        """
        try:
            # 只监听 127.0.0.1,避免暴露到局域网
            self._httpd = ThreadingHTTPServer(
                ("127.0.0.1", self.callback_port), self._make_handler()
            )
        except OSError as e:
            # 端口被占:可能是上次授权残留的服务器没关。尝试换随机端口不可行
            # (redirect_uri 是固定注册的),所以直接报错提示用户关掉占用进程。
            self._error = f"本地回调端口 {self.callback_port} 被占用: {e}\n" \
                          f"请确认没有残留的 MCP OAuth 回调进程占用 127.0.0.1:{self.callback_port}。"
            self._done.set()
            return
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        # 用系统默认浏览器打开授权页(用户已有登录态的浏览器可直接复用会话)
        try:
            webbrowser.open(authorization_url)
        except Exception as e:
            print(f"[MCP OAuth] 打开系统浏览器失败: {e},请手动复制链接到浏览器打开")
            print(f"[MCP OAuth] 授权链接: {authorization_url}")
        # 阻塞直到收到回调(或超时由外层 callback_handler 处理)
        try:
            while not self._done.is_set() and not self._error:
                time.sleep(0.2)
        finally:
            self._stop_server()

    def _make_handler(self):
        owner = self
        callback_path = CALLBACK_PATH

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler 约定)
                if self.path.split("?")[0] != callback_path:
                    self.send_response(404)
                    self.end_headers()
                    return
                # 解析 query 中的 code/state/error
                q = parse_qs(urlparse(self.path).query)
                code = (q.get("code") or [None])[0]
                state = (q.get("state") or [None])[0]
                iss = (q.get("iss") or [None])[0]
                error = (q.get("error") or [None])[0]
                if error:
                    owner._error = f"授权失败: {error}"
                    body = f"授权失败: {error}".encode("utf-8")
                elif not code:
                    owner._error = f"回调 URL 中未找到 code 参数: {self.path[:200]}"
                    body = b"authorization failed: no code"
                else:
                    owner._result = AuthorizationCodeResult(
                        code=code, state=state, iss=iss
                    )
                    body = b"authorization ok, you can close this tab now"
                owner._done.set()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass  # 静默默认访问日志

        return CallbackHandler

    def _stop_server(self):
        httpd = self._httpd
        self._httpd = None
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass

    async def callback_handler(self):
        """SDK 调用:等待用户完成授权并返回 code。"""
        # 等待浏览器线程完成(带超时)
        deadline = time.time() + self.timeout_seconds + 30
        while not self._done.is_set() and time.time() < deadline:
            await asyncio_sleep(0.2)
        if not self._done.is_set():
            # 超时:通知服务器线程退出并释放回调端口
            self._error = "等待授权回调超时,请在浏览器中完成登录后重试"
            self._done.set()
            self._stop_server()
        if self._error:
            from mcp.client.auth.exceptions import OAuthFlowError

            raise OAuthFlowError(self._error)
        if not self._result:
            from mcp.client.auth.exceptions import OAuthFlowError

            raise OAuthFlowError("浏览器授权超时或未完成")
        return self._result


def asyncio_sleep(seconds: float):
    import asyncio

    return asyncio.sleep(seconds)


def ensure_oauth_token(
    server_id: str,
    url: str,
    token_store: TokenStore,
    callback_port: int = DEFAULT_CALLBACK_PORT,
    on_status: Optional[callable] = None,
    timeout_seconds: int = 120,
    no_browser: bool = False,
) -> str | None:
    """确保该 server 有可用 OAuth access_token(必要时触发浏览器授权)。

    流程:用 httpx2 Client(挂 OAuthClientProvider)请求一次 URL,SDK 自动:
      - 已有有效 token -> 直接带上返回
      - token 过期且有 refresh -> 自动刷新
      - 无 token -> 触发浏览器授权(redirect/callback 钩子)后换 token

    返回 access_token 字符串;失败返回 None(错误信息在返回值外的异常或日志)。

    no_browser:启动期传 True,刷新失败时不弹浏览器(无人值守场景),
     直接失败,等用户在面板手动授权。
    """
    if not _MCP_SDK_AVAILABLE:
        print("[MCP OAuth] mcp SDK 未安装,无法执行 OAuth")
        return None
    if on_status:
        on_status("starting")
    handler = OAuthBrowserHandler(
        callback_port=callback_port, timeout_seconds=timeout_seconds, no_browser=no_browser
    )

    storage = token_store.make_storage(server_id)

    import asyncio

    def _run():
        async def _inner():
            meta = OAuthClientMetadata(
                redirect_uris=[f"http://127.0.0.1:{callback_port}{CALLBACK_PATH}"],
                client_name="Symbix",
            )
            provider = OAuthClientProvider(
                server_url=url,
                client_metadata=meta,
                storage=storage,
                redirect_handler=handler.redirect_handler,
                callback_handler=handler.callback_handler,
            )
            if on_status:
                on_status("connecting")
            async with httpx2.AsyncClient(
                auth=provider,
                follow_redirects=True,
                timeout=httpx2.Timeout(timeout_seconds, connect=15.0),
            ) as client:
                if on_status:
                    on_status("authorizing")
                resp = await client.get(url)
                # 若最终仍 401,说明授权未让服务放行(可能 scope 不足等)
                if resp.status_code == 401:
                    raise RuntimeError(
                        f"OAuth 授权后服务仍返回 401: {resp.text[:200]}"
                    )
                # 读回 token(provider 内部已 set 到 storage)
                tok = token_store.get_tokens_sync(server_id)
                if tok:
                    return tok.get("access_token")
                return None

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(_inner())
        finally:
            try:
                loop.close()
            except Exception:
                pass

    return _run()
