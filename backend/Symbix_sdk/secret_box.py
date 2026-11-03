import base64
import ctypes
import os

_PREFIX = "dpapi:"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_ulong),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _blob_from_bytes(data: bytes) -> _DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))


def _bytes_from_blob(blob: _DATA_BLOB) -> bytes:
    out = ctypes.string_at(blob.pbData, blob.cbData)
    ctypes.windll.kernel32.LocalFree(blob.pbData)  # 系统分配的缓冲区要还
    return out


def seal(plaintext: str) -> str:
    """加密(仅 Windows):失败或空值时原样返回,配置写入永不因此报错。"""
    if os.name != "nt" or not plaintext or plaintext.startswith(_PREFIX):
        return plaintext
    try:
        in_blob = _blob_from_bytes(plaintext.encode("utf-8"))
        out_blob = _DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        )
        if not ok:
            return plaintext
        return _PREFIX + base64.b64encode(_bytes_from_blob(out_blob)).decode("ascii")
    except Exception:
        return plaintext


def unseal(stored: str) -> str:
    """解密:没有前缀(明文/历史数据)原样返回;解密失败返回空串(别把密文当明文用)。"""
    if not stored or not stored.startswith(_PREFIX):
        return stored
    try:
        raw = base64.b64decode(stored[len(_PREFIX):])
        in_blob = _blob_from_bytes(raw)
        out_blob = _DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        )
        if not ok:
            return ""
        return _bytes_from_blob(out_blob).decode("utf-8")
    except Exception:
        return ""


def is_sealed(stored: str) -> bool:
    """落盘值是否为密文(诊断/迁移提示用)。"""
    return bool(stored) and stored.startswith(_PREFIX)
