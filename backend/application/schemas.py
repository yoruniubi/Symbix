"""所有 API 请求 / 响应 Pydantic 模型。"""
from typing import List
from pydantic import BaseModel


class AttachmentMeta(BaseModel):
    """上传接口返回的附件元数据，发送聊天时回传 path。"""
    path: str = ""
    filename: str = ""
    name: str = ""
    mime: str = ""
    type: str = ""
    content: str = ""  # 可选：前端直接给文本内容
    size: int = 0


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    history: list[dict] = []
    system_prompt: str = ""
    api_key: str = ""
    api_base: str = ""
    model: str = ""
    use_mcp: bool = False
    use_memory: bool = True
    attachments: list[AttachmentMeta] = []
    superseded_round_id: str = ""  


class ChatResponse(BaseModel):
    content: str
    session_id: str
    reasoning: str = None
    steps: list = []
    act_mode: str = "reactive"
    act_plan: list[str] = []


class ApproveRequest(BaseModel):
    approval_id: str
    approve: bool
    session_id: str = "default"
    system_prompt: str = ""
    api_key: str = ""
    api_base: str = ""
    model: str = ""
    use_memory: bool = True


class ProviderAddRequest(BaseModel):
    name: str
    model: str
    api_key: str = None
    api_base: str = None


class MessageItem(BaseModel):
    role: str
    content: str


class SessionPayload(BaseModel):
    session_id: str = ""
    title: str = "新对话"
    history: List[MessageItem] = []


class DeleteMarkdownRequest(BaseModel):
    session_id: str = ""
    title: str = ""


class RenameSessionRequest(BaseModel):
    session_id: str
    title: str
    old_title: str = ""


class GenerateTitleRequest(BaseModel):
    session_id: str = ""
    context: str = ""
    model: str = ""
    api_base: str = ""
    api_key: str = ""


class InstallNpmRequest(BaseModel):
    package_name: str
    server_id: str
    args: list[str] = []


class AddMcpServerRequest(BaseModel):
    """统一添加 MCP：本地 npm/command 或远程 URL。"""
    server_id: str
    # 远程
    url: str = ""
    transport: str = "sse"
    headers: dict = {}
    # 本地 npm
    package_name: str = ""
    args: list[str] = []
    # 本地 command
    command: str = ""


class AddMcpServersRawRequest(BaseModel):
    """直接粘贴一段 mcpServers JSON 片段，后端 merge 进 mcp_config.json。

    客户端传形如:
    {
      "servers": {
        "my_local": {"command": "python", "args": ["-m", "my_server"]},
        "another":  {"command": "node", "args": ["./srv.js"]}
      }
    }
    覆盖同名 server_id。
    """
    servers: dict[str, dict]


class CreateSkillRequest(BaseModel):
    skill_name: str
    display_name: str = ""
    description: str = ""
    purpose: str = ""
    instructions: str = ""
    overwrite: bool = False


class InstallSkillGithubRequest(BaseModel):
    """对标: npx skills add <repo> --skill <name>"""
    repo_url: str
    skill_name: str = ""
    branch: str = ""
    overwrite: bool = False
