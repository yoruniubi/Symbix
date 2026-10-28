from fastapi import APIRouter, HTTPException
from application.schemas import ProviderAddRequest
from application.state import provider_registry
from Symbix_sdk.model_capabilities import get_model_capabilities, get_vision_note, resolve_vision, clear_vision_cache
from Symbix_sdk.providers import has_real_api_key

router = APIRouter(tags=["providers"])


@router.get("/providers")
async def list_providers():
    """列出 provider 配置。密钥本身不回传（前端不需要、也不应该持有），
    只给 has_key 布尔值，前端据此判断「后端已保存密钥」，避免误报未配置。"""
    providers = {
        name: {
            "model": p.model,
            "api_base": p.api_base,
            "sub_model": p.sub_model or "",
            "has_key": has_real_api_key(p.api_key),
        }
        for name, p in provider_registry.providers.items()
    }
    active = provider_registry.active
    active_has_key = bool(active and providers.get(active, {}).get("has_key"))
    return {
        "active": active,
        "providers": providers,
        "active_has_key": active_has_key,
    }


@router.post("/providers")
async def add_provider(request: ProviderAddRequest):
    try:
        provider_registry.add(
            name=request.name,
            model=request.model,
            api_key=request.api_key,
            api_base=request.api_base,
            sub_model=request.sub_model,
        )
        return {"status": "ok", "message": f"Provider '{request.name}' added"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/providers/{name}/activate")
async def activate_provider(name: str):
    try:
        provider_registry.set_active(name)
        return {"status": "ok", "message": f"Provider '{name}' activated"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/providers/{name}/model")
async def update_provider_model(name: str, body: dict):
    """仅更新 provider 的 model(不改 api_key / api_base / 能力位)。
    供 ChatInput 切换模型时同步到 providers.json,让非流式后台链路
    (generate_title / 记忆压缩 / 记忆提取 / 定时任务)也能用到最新模型。

    body 里带 sub_model 时一并更新子 Agent 模型("" 表示清空 → 回退主模型)。
    """
    new_model = (body.get("model") or "").strip()
    if not new_model:
        raise HTTPException(status_code=400, detail="model 不能为空")
    if name not in provider_registry.providers:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")
    try:
        provider_registry.providers[name].model = new_model
        if "sub_model" in body:
            provider_registry.providers[name].sub_model = (body.get("sub_model") or "").strip() or None
        provider_registry.save()
        return {"status": "ok", "message": f"Provider '{name}' model updated to {new_model}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/model/capabilities")
async def model_capabilities(model: str = ""):
    """
    查询模型的视觉能力。

    - 不传 model 时使用当前活跃 provider 的模型
    - 如果尚未探测过，返回 vision=null（待探测）
    - 传 probe=true 时发起实时探测（用于前端「测试」按钮）
    """
    target = model or (provider_registry.get_active().model if provider_registry.active else "")
    if not target:
        return {"model": "", "vision": None, "vision_reason": "未配置模型"}

    # 先返回缓存结果
    caps = get_model_capabilities(target)
    return caps


@router.get("/model/probe-vision")
async def probe_model_vision(model: str = ""):
    """
    实时探测模型视觉能力（发起一次最小请求）。
    用于前端在用户上传图片前主动检查，或手动「重新检测」。
    """
    target = model or (provider_registry.get_active().model if provider_registry.active else "")
    if not target:
        return {"model": "", "vision": False, "vision_reason": "未配置模型"}

    provider = provider_registry.get_active()
    api_key = provider.api_key or ""
    api_base = provider.api_base or ""
    supports = await resolve_vision(target, api_key, api_base)
    if supports is None:
        note = get_vision_note(target) or "未知原因"
        return {
            "model": target,
            "vision": None,
            "vision_reason": f"探测未得出结论({note});可能是上游限流或网络问题,可稍后重试",
        }
    reason = (
        f"模型 {target} 支持视觉理解，图片将以 base64 方式发送"
        if supports
        else f"模型 {target} 不支持视觉理解，图片将降级为文本描述"
    )
    return {"model": target, "vision": supports, "vision_reason": reason}


@router.post("/model/clear-vision-cache")
async def clear_model_vision_cache(model: str = ""):
    """清除视觉能力探测缓存（model 为空时清除全部）。"""
    clear_vision_cache(model or None)
    return {"status": "ok"}
