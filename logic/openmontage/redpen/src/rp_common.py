# -*- coding: utf-8 -*-
"""redpen 研究公共层:密钥 / OpenAI 客户端 / 图像编辑调用。

独立研究项目,不依赖 forge 包;但网络与超时参数照搬 forge 踩平的坑:
- connect 60s / read 900s(SDK 默认 connect=5s 挡不住分钟级抖动)
- input_fidelity=high 优先,网关不认则去掉重试
"""
import base64
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # redpen/
CORPUS = ROOT.parent / "芙莉莲"                      # 语料目录(官方公开修正稿)
OUT = ROOT / "out"

_ENV_CANDIDATES = [
    ROOT.parent / "OpenMontage" / ".env",
    ROOT.parent / "OpenMontage" / "forge" / ".env",
    ROOT.parent / ".env",
]


def openai_key() -> str:
    k = os.environ.get("OPENAI_API_KEY", "")
    if k and not k.startswith("#") and " " not in k:
        return k
    for env in _ENV_CANDIDATES:
        if not env.is_file():
            continue
        for ln in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = ln.strip()
            if s.startswith("OPENAI_API_KEY="):
                v = s.split("=", 1)[1].strip().strip('"').strip("'")
                if v and not v.startswith("#") and " " not in v:
                    return v
    raise RuntimeError("未取到有效 OPENAI_API_KEY(env 或 .env)")


def client():
    import httpx
    from openai import OpenAI
    return OpenAI(api_key=openai_key(), max_retries=4,
                  timeout=httpx.Timeout(connect=60.0, read=900.0, write=900.0, pool=900.0))


def image_edit(image_paths: list, prompt: str, out_path, size: str = "1536x1024",
               model: str = "gpt-image-2", fidelity: str = "high",
               mask_path=None) -> Path:
    """images.edit 一次调用,写 PNG。多图时第一张是被编辑对象,其余为参考。

    `mask_path`:RGBA 掩膜(alpha=0 处=允许改写,其余保持)——**外科路**。
    全图 edit 是整图重合成,几何会被模型先验拉走(失败模式7:缝合段把已合并的
    肩线拉回原稿 ±12px);要局部修改必须走 mask,对应 scrub 律(改存量不整图重掷)。
    """
    cli = client()
    fhs = [open(p, "rb") for p in image_paths]
    mfh = open(mask_path, "rb") if mask_path else None
    try:
        base = dict(model=model, image=fhs, prompt=prompt, size=size)
        if mfh is not None:
            base["mask"] = mfh
        try:
            r = cli.images.edit(**base, input_fidelity=fidelity)
        except Exception as e:
            if isinstance(e, TypeError) or "input_fidelity" in str(e).lower():
                r = cli.images.edit(**base)
            else:
                raise
    finally:
        for f in fhs:
            f.close()
        if mfh is not None:
            mfh.close()
    dst = Path(out_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(base64.b64decode(r.data[0].b64_json))
    return dst
