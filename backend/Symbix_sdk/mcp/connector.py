import requests
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