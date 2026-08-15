"""Provider (AI 提供商) 管理路由。"""
from fastapi import APIRouter, HTTPException

from application.schemas import ProviderAddRequest
from application.state import provider_registry
from Symbix_sdk.model_capabilities import get_model_capabilities, check_vision, clear_vision_cache

router = APIRouter(tags=["providers"])


@router.get("/providers")
async def list_providers():
    providers = {
        name: {
            "model": p.model,
            "api_base": p.api_base,
        }
        for name, p in provider_registry.providers.items()
    }
    return {"active": provider_registry.active, "providers": providers}


@router.post("/providers")
async def add_provider(request: ProviderAddRequest):
    try:
        provider_registry.add(
            name=request.name,
            model=request.model,
            api_key=request.api_key,
            api_base=request.api_base,
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
    supports = await check_vision(target, api_key, api_base)
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
