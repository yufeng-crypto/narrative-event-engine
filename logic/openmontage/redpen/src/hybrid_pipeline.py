# -*- coding: utf-8 -*-
"""混合执行管线:按指令类型路由到引擎,几何闸验收。hair_flow 案例的完整可复现脚本。

路由原则(失败模式6/7的工程结论):
  - **几何类**(采纳B版/移动轮廓)→ 确定性图像处理(merge_versions),生成模型做不到
  - **对象删除**(删耳环)→ masked inpaint(外科),全图 edit 会把几何拉回先验
  - **批注清除**(纸面文字/引出线)→ 确定性抹除(纸面回填/去色),不烧模型
  - 每步之后 verify_geometry 闸:几何必须始终贴住目标层

案例专属参数(作画框/耳环框/文字框)当前手工给定;worker 化时由 VLM 的 IR 供 bbox。
用法: python src/hybrid_pipeline.py
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
from rp_common import CORPUS, OUT, image_edit
from merge_versions import merge

SRC = CORPUS / "头发的飘动方向可以配合／对齐处理.jpg"
B = OUT / "头发的飘动方向可以配合_对齐处理"
FRAME = (130, 230, 1750, 1310)          # 作画框(1620x1080=3:2,与输出同比例=闸可用)
EARRING_BOX = (175, 120, 345, 260)      # 1536x1024 坐标系
PATCH_BOX = (100, 40, 420, 360)         # 裁片(320x320):耳环+角根+周边发丝上下文
TEXT_FILL = [(20, 150, 160, 330), (830, 540, 1230, 740), (1130, 110, 1360, 540)]
TEXT_DEGREEN = [(120, 120, 480, 240)]
GATE = dict(x0=10, x1=270, y0=670)      # 左肩段(src_cropped 坐标系)


def gate(out_png, label):
    r = subprocess.run([sys.executable, "-X", "utf8",
                        str(Path(__file__).parent / "verify_geometry.py"),
                        str(B / "src_cropped.png"), str(out_png),
                        "--x0", str(GATE["x0"]), "--x1", str(GATE["x1"]),
                        "--y0", str(GATE["y0"])], capture_output=True, text=True)
    print(f"[gate:{label}] {r.stdout.strip()}")
    if r.returncode != 0:
        raise SystemExit(f"几何闸未过({label}),停止 —— 不许带着错几何往下走")


def main():
    B.mkdir(parents=True, exist_ok=True)
    # 0. 裁作画框(输入输出同比例,几何闸坐标映射才严格成立)
    Image.open(SRC).crop(FRAME).save(B / "src_cropped.png")
    # 1. 确定性合并:采纳蓝线版几何
    merge(SRC, B / "merged_full.png")
    Image.open(B / "merged_full.png").crop(FRAME).resize((1536, 1024), Image.LANCZOS)\
         .save(B / "merged_1536.png")
    gate(B / "merged_1536.png", "merge")
    # 2. 删耳环 = **局部裁片编辑**(外科)。两条死路都走过,别回去:
    #    · 全图 edit(含"只缝合") → 整图重合成,几何被先验拉走(失败模式7);
    #    · API mask edit → gpt-image 不严格遵守 mask,透明洞常被原样画成黑块
    #      (2026-09-02 实测 4/5 卷失败,首卷成功属幸运;且 mask 外仍整幅重编码⇒黑线发灰)。
    #    ⇒ 裁耳环周边小片送整片编辑(片内重合成无妨),缩回后**只贴回裁片区**,
    #      片外字节不变;框内"非黑块"判据筛卷(无 seed,好卷靠判据不靠运气),上限 3 次。
    ex0, ey0, ex1, ey1 = EARRING_BOX
    px0, py0, px1, py1 = PATCH_BOX
    base_img = np.array(Image.open(B / "merged_1536.png").convert("RGB"))
    Image.fromarray(base_img[py0:py1, px0:px1]).resize((1024, 1024), Image.LANCZOS)\
         .save(B / "_patch_in.png")

    def load_patch():
        if not (B / "_patch_out.png").is_file():
            return None
        p = np.array(Image.open(B / "_patch_out.png").convert("RGB")
                     .resize((px1 - px0, py1 - py0), Image.LANCZOS))
        sub = p[ey0 - py0:ey1 - py0, ex0 - px0:ex1 - px0].astype(int)
        return p if float((sub.sum(axis=2) < 240).mean()) < 0.20 else None

    patch = load_patch()                      # 已接受的卷=固化资产,复用不重掷(无 seed 律)
    if patch is None:
        for attempt in range(3):
            image_edit([B / "_patch_in.png"],
                       "This is a zoomed-in crop of a Japanese anime key animation drawing "
                       "(clean black line art on plain light-green paper). Remove the double-ring "
                       "earring hanging at the base of the horn entirely: fill that area with the "
                       "plain paper background and continue the horn-base contour and nearby hair "
                       "strands naturally. Keep every other line exactly as drawn, same position, "
                       "same darkness. Output the same crop, nothing else changed.",
                       B / "_patch_out.png", size="1024x1024")
            patch = load_patch()
            print(f"[patch roll {attempt}] {'✓过判据' if patch is not None else '✗废卷'}")
            if patch is not None:
                break
    if patch is None:
        raise SystemExit("裁片编辑三卷全废,停止 —— 如实报告,不带病下行")

    # 纸色配平:贴片亮区中位色对齐基图同区,消矩形色差;边缘 12px 线性羽化藏接缝
    box_base = base_img[py0:py1, px0:px1].astype(int)
    bright_b = box_base.sum(axis=2) > 600
    bright_p = patch.astype(int).sum(axis=2) > 600
    if bright_b.any() and bright_p.any():
        off = (np.median(box_base[bright_b], axis=0)
               - np.median(patch.astype(int)[bright_p], axis=0))
        patch = np.clip(patch.astype(int) + off, 0, 255).astype(np.uint8)
    h, w = patch.shape[:2]
    f = 12
    ramp = np.minimum.outer(np.minimum(np.arange(h), np.arange(h)[::-1]),
                            np.minimum(np.arange(w), np.arange(w)[::-1]))
    alpha = np.clip(ramp / f, 0, 1)[..., None]
    comp = base_img.copy()
    region = box_base * (1 - alpha) + patch.astype(float) * alpha
    comp[py0:py1, px0:px1] = np.clip(region, 0, 255).astype(np.uint8)
    Image.fromarray(comp).save(B / "final_masked.png")
    diff_out = np.abs(comp.astype(int) - base_img.astype(int)).sum(axis=2)
    diff_out[py0:py1, px0:px1] = 0
    assert int((diff_out > 0).sum()) == 0, "裁片区外像素被改动 —— 外科合成失效"
    gate(B / "final_masked.png", "inpaint")
    # 3. 确定性批注清除。⚠ 纸色**逐框就地采样**且只改墨迹像素,不整框填常数——
    #    常数填充与周边纸纹理有色差,矩形边界肉眼可见(2026-09-02 审图撞到)。
    img = np.array(Image.open(B / "final_masked.png").convert("RGB")).astype(int)

    def wipe(bx, only_green=False):
        # ⚠ 纸是绿的:任何"通道极差/绝对暗度"类判据都会把纸当墨(实撞:ptp>45 判中 100%
        #   像素,保护分支静默跳过=整步没生效,闸不看这里,靠审图才发现)。
        #   稳健判据 = 偏离**逐框中位色**(文字稀疏 ⇒ 中位数就是纸色);异常占比必须报错。
        x0_, y0_, x1_, y1_ = bx
        reg = img[y0_:y1_, x0_:x1_]
        paper_med = np.median(reg.reshape(-1, 3), axis=0)
        if only_green:
            ink = (reg[:, :, 1] - reg[:, :, 0] > 40) & (reg[:, :, 1] > 120)
        else:
            # 阈值放低到 25 并膨胀 2px:笔画的抗锯齿光晕若不清,会留可见鬼影(实撞)
            ink = np.abs(reg - paper_med).sum(axis=2) > 25
        ink = ndimage.binary_dilation(ink, iterations=2)
        frac = float(ink.mean())
        assert frac < 0.60, f"wipe{bx}: 墨迹占比 {frac:.0%} 异常 —— 判据或框错了,不许静默"
        reg[ink] = paper_med

    for bx in TEXT_FILL:
        wipe(bx)
    for bx in TEXT_DEGREEN:
        wipe(bx, only_green=True)
    Image.fromarray(img.astype(np.uint8)).save(B / "final_clean.png")
    gate(B / "final_clean.png", "final")
    print("hybrid pipeline done:", B / "final_clean.png")


if __name__ == "__main__":
    main()
