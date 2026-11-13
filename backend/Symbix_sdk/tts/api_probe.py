from __future__ import annotations
import json
import re
import shlex
from typing import Any
from urllib.parse import urlsplit
import httpx

# OpenAPI 文档的常见落点(FastAPI / SpringDoc / Swagger / 各家自建)
_SPEC_PATHS = ("/openapi.json", "/swagger.json", "/v3/api-docs", "/api-docs")

# 音色/模型列表的常见落点。fish 把 /model 挂在域名根而不是 /v1 下,所以
# 除了按用户填的 base 拼,还要按 origin 拼一遍。
_VOICE_PATHS_ORIGIN = ("/model", "/v1/models", "/models", "/v1/voices", "/voices", "/v1/audio/voices")
_VOICE_PATHS_BASE = ("/audio/voices", "/voices", "/models", "/model")

_SPEC_MAX_BYTES = 16 * 1024 * 1024   # fish 的 openapi.json 约 500 KB,留足余量
_VOICE_MAX_BYTES = 8 * 1024 * 1024

# 本机/内网地址:这些不能走系统代理(否则 Clash 之类会把 127.0.0.1 拦成 502)
_LOCAL_HOST_RE = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0$|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|\[?::1\]?$)",
    re.I,
)

# 只保留和语音相关的端点,免得把整份 spec 铺给用户
_KEEP_RE = re.compile(r"tts|speech|synth|voice|audio|transcri|asr", re.I)

# 音色条目里各类服务用的 id / 名字字段
_ID_KEYS = ("_id", "id", "voice_id", "voiceId", "uuid", "model", "model_id")
_NAME_KEYS = ("title", "name", "display_name", "displayName", "label", "model_name")


def _origin(base: str) -> str:
    """从用户填的地址里取出 scheme://host:port。"""
    sp = urlsplit(base)
    if not sp.scheme or not sp.netloc:
        return base
    return f"{sp.scheme}://{sp.netloc}"


def _spec_candidates(base: str, origin: str) -> list[str]:
    out: list[str] = []
    for p in _SPEC_PATHS:
        out.append(origin + p)
    # base 自己可能就是 API 根(如 https://host/api/v1),再按它拼一遍
    for p in _SPEC_PATHS[:2]:
        out.append(base + p)
    seen: set[str] = set()
    return [u for u in out if not (u in seen or seen.add(u))]


def _voice_candidates(base: str, origin: str) -> list[str]:
    out: list[str] = [origin + p for p in _VOICE_PATHS_ORIGIN]
    out += [base + p for p in _VOICE_PATHS_BASE]
    seen: set[str] = set()
    return [u for u in out if not (u in seen or seen.add(u))]


async def _get_json(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], max_bytes: int
) -> tuple[int, Any, str]:
    """GET 一个 URL 并解析 JSON。返回 (HTTP 状态码, 数据, 备注)。失败时状态码为 0。"""
    try:
        r = await client.get(url, headers=headers)
    except Exception as e:  # 连接失败/超时/证书问题
        return 0, None, f"{type(e).__name__}: {str(e)[:120]}"
    if r.status_code != 200:
        return r.status_code, None, (r.text or "")[:120]
    if len(r.content) > max_bytes:
        return r.status_code, None, f"响应过大({len(r.content)} B)"
    try:
        return r.status_code, r.json(), ""
    except Exception:
        return r.status_code, None, "不是合法 JSON(可能是 HTML/YAML)"


def _deref(schema: Any, comps: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """解开 $ref 与 allOf/oneOf/anyOf 组合(嵌套按 depth 限制,防循环)。

    allOf 合并所有分支;oneOf/anyOf 取第一个 —— fish 的 `prosody`、`language`
    就藏在组合里,不解这一步它们永远显示成 `any`,前端也就渲染不出输入框。
    """
    if depth > 3 or not isinstance(schema, dict):
        return {}
    ref = schema.get("$ref")
    if isinstance(ref, str):
        target = comps.get(ref.split("/")[-1])
        if isinstance(target, dict):
            return _deref(target, comps, depth + 1)
        return {}
    for key in ("allOf", "oneOf", "anyOf"):
        branches = schema.get(key)
        if not isinstance(branches, list) or not branches:
            continue
        picked = branches if key == "allOf" else branches[:1]
        merged: dict[str, Any] = {}
        for sub in picked:
            part = _deref(sub, comps, depth + 1)
            if isinstance(part, dict):
                merged.update(part)
        if merged:
            # 外层自带的 type/description 优先保留
            for k in ("type", "description", "enum", "default", "required"):
                if k in schema and k not in merged:
                    merged[k] = schema[k]
            return merged
    return schema


def _field_list(
    schema: Any,
    comps: dict[str, Any],
    prefix: str = "",
    depth: int = 0,
    out: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """把一个 requestBody 的 schema 摊成字段表。

    嵌套对象拍平成点路径(fish 的 `prosody.speed`),前端才能直接渲染成一堆
    扁平输入框:父级 object 行不给输入框,子字段自带完整路径。
    """
    if out is None:
        out = []
    schema = _deref(schema, comps)
    props = schema.get("properties")
    if not isinstance(props, dict):
        return out
    required = set(schema.get("required") or [])
    for name, meta in props.items():
        meta = _deref(meta, comps)
        if not isinstance(meta, dict):
            meta = {}
        ftype = str(meta.get("type") or "")
        has_children = isinstance(meta.get("properties"), dict) and bool(meta.get("properties"))
        if ftype == "array":
            item = _deref(meta.get("items") or {}, comps)
            if not isinstance(item, dict):
                item = {}
            ftype = f"array[{item.get('type') or ('object' if item.get('properties') else 'any')}]"
        elif not ftype and has_children:
            ftype = "object"
        if not ftype:
            ftype = "any"
        full = prefix + name
        item: dict[str, Any] = {
            "name": full,
            "type": ftype,
            "required": name in required,
        }
        enum = meta.get("enum")
        if isinstance(enum, list) and enum:
            item["enum"] = [str(x) for x in enum][:12]
        if meta.get("default") is not None:
            item["default"] = meta["default"]
        desc = meta.get("description")
        if isinstance(desc, str) and desc.strip():
            item["description"] = desc.strip()[:120]
        out.append(item)
        # 嵌套对象:拍平展开一层(最多两层),子字段用点路径
        if has_children and depth < 2 and len(out) < 40:
            _field_list(meta, comps, prefix=full + ".", depth=depth + 1, out=out)
        if len(out) >= 40:
            break
    return out


def _endpoints(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """抽出语音相关端点,附上 header/query 参数和请求体字段。"""
    comps = spec.get("components")
    comps = (comps.get("schemas") if isinstance(comps, dict) else None) or {}
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return []

    out: list[dict[str, Any]] = []
    for path, node in paths.items():
        if not isinstance(node, dict) or not _KEEP_RE.search(str(path)):
            continue
        for method in ("post", "get", "put", "delete"):
            op = node.get(method)
            if not isinstance(op, dict):
                continue
            ep: dict[str, Any] = {
                "method": method.upper(),
                "path": str(path),
                "summary": str(op.get("summary") or op.get("operationId") or "")[:80],
                "params": [],
                "content_types": [],
                "fields": [],
            }
            for prm in op.get("parameters") or []:
                if not isinstance(prm, dict):
                    continue
                where = prm.get("in")
                if where not in ("header", "query"):
                    continue
                ep["params"].append({
                    "in": where,
                    "name": str(prm.get("name") or ""),
                    "required": bool(prm.get("required")),
                })
            body = op.get("requestBody")
            content = (body.get("content") if isinstance(body, dict) else None) or {}
            for ctype, media in content.items():
                short = str(ctype).split(";")[0].strip()
                ep["content_types"].append(short)
            # 字段表取结构化程度最高的那份(JSON 优先,其次其它)
            for ctype, media in sorted(
                content.items(),
                key=lambda kv: 0 if "json" in str(kv[0]) else 1,
            ):
                fields = _field_list((media or {}).get("schema") or {}, comps)
                if fields:
                    ep["fields_source"] = str(ctype).split(";")[0].strip()
                    ep["fields"] = fields
                    break
            out.append(ep)
            if len(out) >= 12:
                break
        if len(out) >= 12:
            break

    out.sort(key=lambda e: (e["method"] != "POST", e["path"]))
    return out


def _pick_str(obj: dict[str, Any], keys: tuple[str, ...]) -> str:
    for k in keys:
        v = obj.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return ""


def _normalize_voices(data: Any) -> tuple[list[dict[str, str]], int]:
    """把各家音色列表归一成 [{id, title}],并尽量带出总数。"""
    rows: list[Any] = []
    total = 0
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for k in ("items", "data", "voices", "models", "results", "list"):
            v = data.get(k)
            if isinstance(v, list):
                rows = v
                break
        for k in ("total", "count", "total_count"):
            v = data.get(k)
            if isinstance(v, int):
                total = v
                break
    out: list[dict[str, str]] = []
    for row in rows[:400]:
        if not isinstance(row, dict):
            continue
        vid = _pick_str(row, _ID_KEYS)
        name = _pick_str(row, _NAME_KEYS)
        if not vid and not name:
            continue
        out.append({"id": vid or name, "title": name or vid})
    return out[:80], (total or len(out))


async def probe(base_url: str, api_key: str = "", *, timeout: float = 8.0) -> dict[str, Any]:
    """探测一个云端语音服务。返回 OpenAPI 摘要 + 音色列表,失败项留给前端展示。

    只做只读 GET,不改任何配置;探测失败不抛异常,结果里带 tried 便于排查。
    """
    raw = (base_url or "").strip()
    if not raw:
        return {"ok": False, "error": "base_url 为空"}
    base = raw.rstrip("/")
    if "://" not in base:
        base = "http://" + base
    origin = _origin(base)

    headers = {"Accept": "application/json", "User-Agent": "SymbixProbe/1.0"}
    key = (api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    spec_out: dict[str, Any] = {
        "found": False, "url": None, "title": "", "version": "",
        "servers": [], "endpoints": [], "tried": [],
    }
    voices_out: dict[str, Any] = {
        "found": False, "url": None, "total": 0, "items": [], "tried": [],
    }

    # 远程中转常要靠系统代理,本机/内网服务必须绕过(否则会被代理拦成 502)
    host = urlsplit(base).hostname or ""
    trust_env = not bool(_LOCAL_HOST_RE.match(host))
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, trust_env=trust_env
    ) as client:
        for url in _spec_candidates(base, origin):
            status, data, note = await _get_json(client, url, headers, _SPEC_MAX_BYTES)
            spec_out["tried"].append({"url": url, "status": status, "note": note})
            if not isinstance(data, dict):
                continue
            if "openapi" not in data and "swagger" not in data:
                continue
            info = data.get("info") if isinstance(data.get("info"), dict) else {}
            servers = data.get("servers")
            spec_out.update({
                "found": True,
                "url": url,
                "title": str(info.get("title") or "")[:80],
                "version": str(data.get("openapi") or data.get("swagger") or ""),
                "servers": [
                    str(s.get("url"))
                    for s in (servers or [])
                    if isinstance(s, dict) and s.get("url")
                ][:5],
                "base_path": data.get("basePath") or "",
                "endpoints": _endpoints(data),
            })
            break

        if not spec_out["found"]:
            # spec 没找到时至少看一眼 /docs 是否存在(401/403 也比 404 有信息量)
            for url in (origin + "/docs", origin + "/swagger-ui/index.html"):
                status, _, note = await _get_json(client, url, headers, 64 * 1024)
                spec_out["tried"].append({"url": url, "status": status, "note": note})
                if status == 200:
                    break

        for url in _voice_candidates(base, origin):
            status, data, note = await _get_json(client, url, headers, _VOICE_MAX_BYTES)
            voices_out["tried"].append({"url": url, "status": status, "note": note})
            items, total = _normalize_voices(data)
            if items:
                voices_out.update({
                    "found": True, "url": url, "total": total, "items": items,
                })
                break

    return {
        "ok": True,
        "base_url": base,
        "origin": origin,
        "spec": spec_out,
        "voices": voices_out,
    }


# ---------------- 无 API 文档时的兜底:从 curl 命令反解请求形状 ----------------
#
# OpenAI 官方、商业 API、私有网关都不暴露 openapi.json,而「发个空请求让服务端
# 报缺哪个字段」也行不通(fish 是 402 额度检查在校验前,OpenAI 是 401 鉴权在最前)。
# 但用户手上一定有文档里那条能跑通的 curl 示例 —— 它就是最权威的参数说明。

_SENSITIVE_HEADER_RE = re.compile(
    r"^(authorization|api-key|x-api-key|token|x-auth-token|cookie|proxy-authorization)$",
    re.I,
)
_DROP_TOKENS = {"-s", "--silent", "-i", "--include", "-v", "--verbose", "-k", "--insecure",
                "--compressed", "-g", "--globoff", "-n", "--no-buffer", "--no-progress-meter"}


def _mask_headers(headers: dict[str, str]) -> dict[str, str]:
    """脱敏:密钥一律不让尾部偷露到前端/日志里。"""
    out: dict[str, str] = {}
    for k, v in headers.items():
        if _SENSITIVE_HEADER_RE.match(k):
            scheme = v.split(" ", 1)[0] if " " in v else ""
            if scheme.lower() in ("bearer", "basic", "token", "key"):
                out[k] = f"{scheme} ***"
            else:
                out[k] = "***"
        else:
            out[k] = v
    return out


def _guess_type(v: Any) -> str:
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return "any"


def _sample(v: Any) -> str:
    try:
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    except Exception:
        s = str(v)
    s = s.replace("\n", " ").strip()
    return s if len(s) <= 60 else s[:57] + "..."


def _collect_fields(body: str, form: dict[str, str]) -> tuple[list[dict[str, str]], list[str]]:
    """从 body 里抽字段名 + 样本值。支持 JSON 对象、urlencoded、multipart -F。"""
    fields: list[dict[str, str]] = []
    warnings: list[str] = []
    if body:
        stripped = body.strip()
        if stripped.startswith(("{", "[")):
            try:
                data = json.loads(stripped)
            except Exception:
                warnings.append("body 看起来像 JSON 但解析失败")
                data = None
            if isinstance(data, dict):
                for k, v in data.items():
                    fields.append({"name": str(k), "type": _guess_type(v), "sample": _sample(v)})
            elif isinstance(data, list):
                warnings.append("body 是数组而非对象")
        elif "=" in stripped:
            for pair in stripped.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    fields.append({"name": k.strip(), "type": "string", "sample": _sample(v)})
    elif form:
        for k, v in form.items():
            fields.append({
                "name": k,
                "type": "file" if v.startswith("@") else "string",
                "sample": _sample(v),
            })
    return fields, warnings


def parse_curl(command: str, *, mask: bool = True) -> dict[str, Any]:
    """从 curl 命令反解出 URL / 方法 / header / body 字段(header 已脱敏)。

    没有 OpenAPI 文档时的兜底,也是「自己试出来的能跑的那条命令」的固化形式。
    `mask=False` 保留原值,供 `curl_to_config` 提取 api_key 用 —— 对外一律用默认的脱敏版。
    """
    raw = (command or "").strip()
    if not raw:
        return {"ok": False, "error": "命令为空"}
    # 续行符:bash 的 \ 续行和 Windows cmd 的 ^ 续行
    norm = re.sub(r"\\\r?\n", " ", raw)
    norm = re.sub(r"\^\r?\n", " ", norm).replace("\r", " ")
    head = norm.lstrip()
    for prefix in ("curl.exe ", "curl "):
        if head.lower().startswith(prefix):
            norm = head[len(prefix):]
            break
    else:
        if not re.search(r"\bhttps?://", norm):
            return {"ok": False, "error": "不像是 curl 命令(没找到 http(s) 地址)"}

    try:
        tokens = shlex.split(norm, posix=True)
    except ValueError as e:
        return {"ok": False, "error": f"命令解析失败({e}),试试把引号补全"}

    url = ""
    method = ""
    headers: dict[str, str] = {}
    body = ""
    form: dict[str, str] = {}

    i, n = 0, len(tokens)
    while i < n:
        tok = tokens[i]
        low = tok.lower()
        nxt = tokens[i + 1] if i + 1 < n else None
        if low in ("-x", "--request") and nxt is not None:
            method = nxt.strip().upper()
            i += 2
            continue
        if low in ("-h", "--header") and nxt is not None:
            if ":" in nxt:
                k, v = nxt.split(":", 1)
                headers[k.strip()] = v.strip()
            i += 2
            continue
        if low in ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii") and nxt is not None:
            body = nxt
            i += 2
            continue
        if low in ("-f", "--form") and nxt is not None:
            if "=" in nxt:
                k, v = nxt.split("=", 1)
                form[k.strip()] = v.strip()
            i += 2
            continue
        if low in ("-u", "--user") and nxt is not None:
            headers["Authorization"] = "Basic " + nxt
            i += 2
            continue
        if low in ("-a", "--user-agent") and nxt is not None:
            headers["User-Agent"] = nxt
            i += 2
            continue
        if low in ("-b", "--cookie") and nxt is not None:
            headers["Cookie"] = nxt
            i += 2
            continue
        if low in ("-o", "--output", "-m", "--max-time", "--connect-timeout") and nxt is not None:
            i += 2
            continue
        if low in _DROP_TOKENS:
            i += 1
            continue
        if not url and re.match(r"^https?://", tok, re.I):
            url = tok
        i += 1

    if not url:
        return {"ok": False, "error": "没找到 http(s) 地址"}

    content_type = ""
    for k, v in headers.items():
        if k.lower() == "content-type":
            content_type = v.split(";")[0].strip().lower()
            break

    fields, warnings = _collect_fields(body, form)
    if not method:
        method = "POST" if (body or form) else "GET"
    if fields and not content_type:
        warnings.append("命令里没带 Content-Type,按 body 形态推断")

    return {
        "ok": True,
        "url": url,
        "method": method,
        "content_type": content_type,
        "headers": _mask_headers(headers) if mask else dict(headers),
        "fields": fields,
        "has_body": bool(body or form),
        "body_preview": body[:1500] if body else "",
        # 完整 body 给 curl_to_config 生成模板用(前端只拿 preview,不展示这个)
        "body_raw": body[:20000] if body else "",
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# curl → 配置:把一条能跑通的命令直接变成「自定义请求头 + body 模板」
#
# 目的是消灭「看着文档手填一遍」。用户只需要把厂商文档里那条 curl 贴进来,
# 这里把 header / body 拆成配置项,正文和语速换成占位符,密钥提取到 api_key 字段。
# ---------------------------------------------------------------------------

_AUTH_HEADER_RE = re.compile(r"^(proxy-)?authorization$", re.I)
_SKIP_HEADER_RE = re.compile(
    r"^(content-type|content-length|accept|accept-encoding|accept-language|"
    r"user-agent|host|connection|keep-alive|cookie|transfer-encoding)$",
    re.I,
)
_BEARER_RE = re.compile(r"^\s*(?:bearer|token|key)\s+(.+)$", re.I)

# 运行时会被真实值替换的 header 占位符(只有 api_key 一个,其余头都是固定值)
_HDR_APIKEY_PH = "{{api_key}}"

# 和前端 TEXT_FIELDS / SPEED_FIELDS / VOICE_FIELDS 保持一致
_TEXT_KEYS = {"text", "input", "content", "say", "sentence", "prompt"}
_SPEED_KEYS = {"speed", "rate"}
_VOICE_KEYS = {
    "voice", "voice_id", "voiceid", "speaker", "speaker_id", "timbre", "voice_name",
}
_PH_MARKS = {
    "text": "__SYMBIX_PH_TEXT__",
    "speed": "__SYMBIX_PH_SPEED__",
    "voice": "__SYMBIX_PH_VOICE__",
}


def _ph_kind(key: str) -> str | None:
    """字段名 → 占位符种类。"""
    low = key.lower()
    if low in _TEXT_KEYS:
        return "text"
    if low in _SPEED_KEYS:
        return "speed"
    if low in _VOICE_KEYS:
        return "voice"
    return None


def _mark_placeholders(node: Any) -> Any:
    """递归把正文/语速/音色字段打成哨兵字符串。

    不能直接往 JSON 里塞裸 `{{text}}` —— 那样 dumps 出来会被加引号。先当普通
    字符串塞进去,dumps 完再按哨兵把引号拆掉。
    """
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            kind = _ph_kind(str(k))
            if kind and isinstance(v, (str, int, float)):
                out[k] = _PH_MARKS[kind]
            else:
                out[k] = _mark_placeholders(v)
        return out
    if isinstance(node, list):
        return [_mark_placeholders(v) for v in node]
    return node


def _template_from_body(body: str) -> tuple[str, list[str]]:
    """body 文本 → 带占位符的 body 模板。返回 (模板, 说明)。"""
    text = (body or "").strip()
    if not text:
        return "", []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text, ["body 不是合法 JSON,原样写进模板"]
    if not isinstance(data, dict):
        return "", [f"body 是 {type(data).__name__} 而不是 JSON 对象,无法生成模板"]

    marked = _mark_placeholders(data)
    dumped = json.dumps(marked, ensure_ascii=False, indent=2)
    for kind, mark in _PH_MARKS.items():
        dumped = dumped.replace(f'"{mark}"', "{{%s}}" % kind)

    notes: list[str] = []
    if not any(_ph_kind(str(k)) == "text" for k in data):
        notes.append("body 里没找到正文字段(text/input/content…),模板需要手补 {{text}}")
    return dumped, notes


def curl_to_config(command: str) -> dict[str, Any]:
    """把 curl 命令拆成可直接保存的 TTS 配置。

    - `Authorization: Bearer xxx` → 提取成 api_key(不留在 header 里,避免明文进配置)
    - `model` 头 → 同时填进「模型」和自定义请求头(有的服务只认请求头)
    - 其它非协议头 → 原样保留;值被脱敏过的写成 `{{api_key}}`
    - body → 模板,正文/语速/音色换成 `{{text}}` / `{{speed}}` / `{{voice}}`
    """
    parsed = parse_curl(command, mask=False)
    if not parsed.get("ok"):
        return parsed

    headers: dict[str, str] = parsed.get("headers") or {}
    out_headers: dict[str, str] = {}
    api_key = ""
    model = ""
    notes: list[str] = []

    for name, value in headers.items():
        low = name.lower()
        val = (value or "").strip()
        if _AUTH_HEADER_RE.match(low):
            m = _BEARER_RE.match(val)
            api_key = (m.group(1).strip() if m else val)
            notes.append("已从 Authorization 头提取 API Key,填进「API Key」")
            continue
        if _SKIP_HEADER_RE.match(low):
            continue
        if low == "model":
            model = val
            out_headers[name] = val
            notes.append("model 走请求头,已同时填进「模型」和自定义请求头")
            continue
        # 密钥头一律写成占位符:值是真 key 也不能进配置文件
        if _SENSITIVE_HEADER_RE.match(low) or val.endswith("***"):
            out_headers[name] = _HDR_APIKEY_PH
            notes.append(f"{name} 是密钥头,写成 {_HDR_APIKEY_PH},发送时用「API Key」里的值替换")
            continue
        out_headers[name] = val

    body_template, body_notes = _template_from_body(parsed.get("body_raw") or "")
    notes.extend(body_notes)
    if not body_template:
        notes.append("这条命令没有请求体,保持标准 OpenAI 形状")

    return {
        "ok": True,
        "url": parsed.get("url") or "",
        "method": parsed.get("method") or "",
        "config": {
            "base_url": parsed.get("url") or "",
            "api_key": api_key,
            "model": model,
            "extra_headers": (
                json.dumps(out_headers, ensure_ascii=False, indent=2) if out_headers else ""
            ),
            "body_template": body_template,
        },
        "notes": notes,
        "headers": _mask_headers(headers),
        "fields": parsed.get("fields") or [],
        "warnings": parsed.get("warnings") or [],
    }
