"""会话 Markdown 导出 / 重命名 / 标题生成 / 用户画像。"""
import os
import json as _json
import shutil
from fastapi import APIRouter, HTTPException

from application.schemas import (
    SessionPayload,
    DeleteMarkdownRequest,
    RenameSessionRequest,
    GenerateTitleRequest,
)
from application.state import (
    memory,
    symbix_client,
    skill_registry,
    provider_registry,
    SDK_CONFIG_DIR,
    SESSION_INDEX_PATH,
)
from Symbix_sdk.tools.file_pipeline import get_uploads_root

router = APIRouter(tags=["sessions"])


def _load_index() -> dict:
    if not os.path.exists(SESSION_INDEX_PATH):
        return {}
    try:
        with open(SESSION_INDEX_PATH, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return {}


def _save_index(data: dict):
    with open(SESSION_INDEX_PATH, "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False, indent=2)


def _get_md_path(session_id: str) -> str:
    """按 session_id 返回 MD 文件路径"""
    return os.path.join(SDK_CONFIG_DIR, f"{session_id}.md")


def _get_index_title(session_id: str) -> str:
    """从 index 取标题，没有则返回默认"""
    idx = _load_index()
    return idx.get(session_id, "未命名对话")


# ============ 用户画像 ============

@router.get("/api/profile")
async def get_user_profile():
    """获取当前用户画像"""
    return {"profile": memory.get_profile()}


@router.post("/api/profile")
async def update_user_profile(facts: dict):
    """手动更新用户画像（部分覆盖）"""
    if not isinstance(facts, dict):
        raise HTTPException(status_code=400, detail="需要 JSON 对象")
    memory.set_profile_facts({str(k): str(v) for k, v in facts.items()})
    return {"status": "ok", "profile": memory.get_profile()}


@router.delete("/api/profile/{key}")
async def delete_profile_key(key: str):
    """删除一条画像事实"""
    memory.delete_profile_fact(key)
    return {"status": "ok", "profile": memory.get_profile()}


# ============ Markdown 导出 ============

@router.post("/api/save_markdown")
async def save_markdown(payload: SessionPayload):
    """保存/覆盖当前会话为 Markdown 文件"""
    sid = payload.session_id or "default"
    md_content = f"# {payload.title}\n\n"
    for msg in payload.history:
        role_label = "**User**" if msg.role == "user" else "**Assistant**"
        md_content += f"### {role_label}:\n{msg.content}\n\n---\n\n"

    file_path = _get_md_path(sid)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    index = _load_index()
    index[sid] = payload.title or index.get(sid, "新对话")
    _save_index(index)

    return {"status": "success", "session_id": sid, "path": file_path}


@router.post("/api/delete_markdown")
async def delete_markdown(req: DeleteMarkdownRequest):
    """按 session_id 删除 Markdown + memory 中的消息/摘要 + 关联附件(uploads/) + checkpoint/blob"""
    sid = req.session_id or "default"
    file_path = _get_md_path(sid)
    if os.path.exists(file_path):
        os.remove(file_path)
    index = _load_index()
    index.pop(sid, None)
    _save_index(index)
    try:
        memory.clear_session(sid)
    except Exception as e:
        print(f"[Memory] clear_session failed: {e}")
    # 同步清该会话的 trust 状态(auto-pilot 开关 + 永久 grant,防孤儿残留)
    try:
        from application.services.risk_context import clear_session as clear_risk_session
        clear_risk_session(sid)
    except Exception as e:
        print(f"[Risk] clear_session failed: {e}")
    # 解绑关联的定时任务(任务本体保留,仅断开 session_id 引用,下一次运行自动新建 schedule__ 会话)
    try:
        from application.state import job_manager
        released = job_manager.release_session(sid)
        if released:
            print(f"[Jobs] released session {sid} from jobs: {released}")
    except Exception as e:
        print(f"[Jobs] release_session failed: {e}")
    # 级联清理附件目录 uploads/{sanitized_sid}/
    try:
        from Symbix_sdk.tools.file_pipeline import session_upload_dir
        upload_dir = session_upload_dir(sid)
        if os.path.isdir(upload_dir):
            for name in os.listdir(upload_dir):
                p = os.path.join(upload_dir, name)
                if os.path.isfile(p) or os.path.islink(p):
                    os.remove(p)
                elif os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
            os.rmdir(upload_dir)
            print(f"[Uploads] removed {upload_dir}")
    except Exception as e:
        print(f"[Uploads] cleanup failed: {e}")
    return {"status": "success", "message": f"Deleted: {sid}.md"}


@router.post("/api/rename_session")
async def rename_session(req: RenameSessionRequest):
    """重命名会话标题（index + MD 文件标题行）"""
    sid = req.session_id
    new_title = req.title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="标题不能为空")

    index = _load_index()
    index[sid] = new_title
    _save_index(index)

    md_path = _get_md_path(sid)
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if lines and lines[0].startswith("# "):
            lines[0] = f"# {new_title}\n"
        with open(md_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    return {"status": "success", "session_id": sid, "title": new_title}


@router.post("/api/generate_title")
async def generate_title(req: GenerateTitleRequest):
    """使用 AI 根据对话上下文生成简短标题（≤15 字）"""
    context = req.context
    if not context:
        return {"status": "skipped", "reason": "无对话上下文"}

    # 检查 Provider 是否可用，避免未配置 API Key 时返回 500
    try:
        provider = provider_registry.get_active()
        # 前端可选传入当前会话实际使用的 model/api_base/api_key，避免用 providers.json 里的过期 default
        use_model = req.model or provider.model
        use_base = req.api_base or provider.api_base
        use_key = req.api_key or provider.api_key
        if not use_key:
            return {"status": "skipped", "reason": "未配置 API Key"}
    except Exception:
        return {"status": "skipped", "reason": "Provider 未就绪"}

    prompt = (
        "根据以下对话内容，生成一个简短的标题（不超过 15 个字）。"
        "直接返回标题，不要带引号、标点或多余说明：\n\n" + context
    )
    try:
        result = await symbix_client.chat(
            user_input=prompt,
            history=[],
            registry=skill_registry,
            tools=None,
            override_model=use_model or None,
            override_api_base=use_base or None,
            override_api_key=use_key or None,
        )
        title = result.get("content", "").strip().strip('"').strip("'")[:30]
        if len(title) > 15:
            title = title[:15] + "…"

        sid = req.session_id or "default"
        if sid and title:
            index = _load_index()
            index[sid] = title
            _save_index(index)

        return {"status": "success", "title": title}
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 返回 200 但标记为跳过,避免前端触发 500
        return {"status": "skipped", "reason": str(e)}


# ============ 孤儿数据清理 ============

@router.get("/api/orphans/scan")
async def scan_orphans():
    """扫描并返回孤儿数据清单(只读,不删除):
    - checkpoint_records 有记录但 messages 没有的 session(checkpoint 孤儿)
    - history_list 下不在 sessions_index.json 里的 .md 文件(旧文件名会话遗留)
    - uploads/ 下不在任何会话里的目录(理论上 delete_markdown 已级联清理,双保险)
    - checkpoint_blobs 里不再被任何记录引用的 blob 文件
    """
    scan = {"orphan_checkpoint_sessions": [], "orphan_md_files": [], "orphan_upload_dirs": [], "orphan_blobs": []}
    try:
        import sqlite3
        db_path = memory.db_path
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        # 1) checkpoint 孤儿 session
        ckpt_rows = cur.execute(
            "SELECT DISTINCT session_id FROM checkpoint_records WHERE session_id NOT IN (SELECT DISTINCT session_id FROM messages)"
        ).fetchall()
        for (sid,) in ckpt_rows:
            n = cur.execute("SELECT COUNT(*) FROM checkpoint_records WHERE session_id=?", (sid,)).fetchone()[0]
            scan["orphan_checkpoint_sessions"].append({"session_id": sid, "records": n})
        # 2) MD 孤儿文件
        for f in sorted(os.listdir(SDK_CONFIG_DIR)):
            if f.endswith(".md"):
                sid = f[:-3]
                idx = _load_index()
                if sid not in idx:
                    scan["orphan_md_files"].append(f)
        # 3) uploads 孤儿目录(有子目录但不在 messages 表 session 里)
        up_root = get_uploads_root()
        if os.path.isdir(up_root):
            for d in sorted(os.listdir(up_root)):
                p = os.path.join(up_root, d)
                if os.path.isdir(p) and d not in {r[0] for r in cur.execute("SELECT DISTINCT session_id FROM messages")}:
                    scan["orphan_upload_dirs"].append(d)
        # 4) blob 孤儿
        blobs_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), "checkpoint_blobs")
        if os.path.isdir(blobs_dir):
            referenced = set()
            for (payload_json,) in cur.execute("SELECT payload FROM checkpoint_records").fetchall():
                try:
                    p = _json.loads(payload_json)
                    for k in ("hash_before", "hash_after"):
                        h = p.get(k)
                        if isinstance(h, str) and len(h) == 12:
                            referenced.add(h)
                except Exception:
                    pass
            for f in sorted(os.listdir(blobs_dir)):
                if f[:12] not in referenced:
                    scan["orphan_blobs"].append(f)
        conn.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "detail": str(e)}
    scan["status"] = "ok"
    return scan


@router.post("/api/orphans/clean")
async def clean_orphans():
    """清理孤儿数据:删除 checkpoint 孤儿记录(含 blob 回收)/ 孤儿 MD / 孤儿 uploads 目录。"""
    result = {"status": "ok", "cleaned": {"checkpoint_sessions": [], "md_files": [], "upload_dirs": [], "blobs": []}}
    try:
        scan = await scan_orphans()
        if scan.get("status") != "ok":
            return scan
        # 1) checkpoint 孤儿:复用 clear_session(会收集并回收 blob)
        for item in scan["orphan_checkpoint_sessions"]:
            sid = item["session_id"]
            try:
                memory.clear_session(sid)
                result["cleaned"]["checkpoint_sessions"].append(sid)
            except Exception as e:
                print(f"[CleanOrphans] clear_session {sid} failed: {e}")
        # 2) 孤儿 MD 文件
        for f in scan["orphan_md_files"]:
            p = os.path.join(SDK_CONFIG_DIR, f)
            try:
                os.remove(p)
                result["cleaned"]["md_files"].append(f)
            except Exception as e:
                print(f"[CleanOrphans] remove {f} failed: {e}")
        # 3) 孤儿 uploads 目录
        up_root = get_uploads_root()
        for d in scan["orphan_upload_dirs"]:
            p = os.path.join(up_root, d)
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                    result["cleaned"]["upload_dirs"].append(d)
            except Exception as e:
                print(f"[CleanOrphans] remove upload dir {d} failed: {e}")
        # 4) 孤儿 blob 文件
        blobs_dir = os.path.join(os.path.dirname(os.path.abspath(memory.db_path)), "checkpoint_blobs")
        for f in scan["orphan_blobs"]:
            p = os.path.join(blobs_dir, f)
            try:
                if os.path.isfile(p):
                    os.remove(p)
                    result["cleaned"]["blobs"].append(f)
            except Exception as e:
                print(f"[CleanOrphans] remove blob {f} failed: {e}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "detail": str(e)}
    return result
