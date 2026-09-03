import urllib.request, json, socket
socket.setdefaulttimeout(10)
# 禁用代理(可能 WSL 环境有 proxy 干扰 localhost)
proxy = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(proxy)
for path in ["/", "/mcp/test"]:
    try:
        with opener.open("http://127.0.0.1:8000" + path, timeout=8) as r:
            body = r.read().decode("utf-8", "replace")
            print(path, "->", r.status, body[:200].replace("\n", " "))
    except Exception as e:
        print(path, "ERR:", type(e).__name__, str(e)[:150])
