"""文件上传/解析路由:/upload, /parse_file。"""
from fastapi import APIRouter, HTTPException, File, UploadFile, Form

router = APIRouter(tags=["chat"])

@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    session_id: str = Form("default"),
):
    """上传一个或多个附件到 uploads/{session_id}/。"""
    from Symbix_sdk.tools.file_pipeline import save_upload, parse_file_path

    results = []
    for uf in files:
        data = await uf.read()
        meta = save_upload(
            session_id=session_id or "default",
            filename=uf.filename or "file",
            data=data,
        )
        if meta.get("status") == "ok":
            preview = parse_file_path(
                meta["path"],
                max_chars=2000,
                include_image_base64=False,
            )
            meta["kind"] = preview.get("kind")
            meta["preview"] = (preview.get("text") or "")[:500]
        results.append(meta)

    ok_count = sum(1 for r in results if r.get("status") == "ok")
    return {
        "status": "ok" if ok_count else "error",
        "uploaded": results,
        "count": ok_count,
    }


@router.post("/parse_file")
async def parse_file_api(body: dict):
    """按路径解析已上传/工作区内文件。"""
    from Symbix_sdk.tools.file_pipeline import parse_file_path

    path = (body or {}).get("path") or (body or {}).get("file_path") or ""
    max_chars = int((body or {}).get("max_chars") or 50000)
    if not path:
        raise HTTPException(status_code=400, detail="path 不能为空")
    return parse_file_path(path, max_chars=max_chars, include_image_base64=False)
