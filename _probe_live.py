import urllib.request, json
def get(path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=5) as r:
            return r.status, r.read().decode("utf-8", "replace")[:500]
    except Exception as e:
        return None, str(e)[:200]

s, b = get("/mcp/oauth/status/test-nonexistent")
print("oauth/status:", s, b)
