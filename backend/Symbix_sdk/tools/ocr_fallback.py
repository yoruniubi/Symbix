"""可选 OCR 兜底(RapidOCR / PaddleOCR-onnx)。

定位:文档嵌图 / 扫描页在**拿不到文字层**时的兜底,懒加载 + 全部可缺省 ——
rapidocr 未安装时 `_ocr_image_bytes` 返回 None,调用方退回原行为,零影响。

实验数据(2026-10,§8.62.1):中英 5/5 行 0.82~0.90 置信度,热跑 0.5s/张;
依赖 165MB(决策点:打包后看 exe 增量再定去留)。
"""
from __future__ import annotations

import io
import threading
from typing import Optional

# 单页/单图 OCR 文字上限(拼进"文字替身"防止上下文爆炸)
MAX_OCR_CHARS = 4000

_engine = None
_engine_lock = threading.Lock()
_engine_failed = False


def _get_engine():
    """懒加载 RapidOCR 单例;导入/初始化失败记 _engine_failed 不再重试。"""
    global _engine, _engine_failed
    if _engine is not None or _engine_failed:
        return _engine
    with _engine_lock:
        if _engine is not None or _engine_failed:
            return _engine
        try:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
        except Exception:
            _engine_failed = True
            _engine = None
    return _engine


def ocr_available() -> bool:
    """OCR 是否可用(会触发首次加载;失败即 False)。"""
    return _get_engine() is not None


def _ocr_image_bytes(data: bytes) -> Optional[str]:
    """对图片字节做 OCR,返回换行拼接的文本;不可用/无文字/失败 → None。"""
    engine = _get_engine()
    if engine is None:
        return None
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        return None
    # PNG/JPEG 之外(如带 alpha 的 webp)统一转 RGB PNG,防 onnx 输入不认
    try:
        buf = io.BytesIO()
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()
    except Exception:
        img_bytes = data
    try:
        result, _ = engine(img_bytes)
    except Exception:
        return None
    if not result:
        return None
    lines = [str(t).strip() for _, t, _c in result if str(t).strip()]
    text = "\n".join(lines)
    if len(text) > MAX_OCR_CHARS:
        text = text[:MAX_OCR_CHARS] + "\n… [OCR 截断]"
    return text or None
