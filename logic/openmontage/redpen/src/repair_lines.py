# -*- coding: utf-8 -*-
"""断线修补(混合管线第4步):代码找断口 → 模型裁片接线 → 判据贴回。

分工定案(用户 2026-09-02 拍板):代码负责"删得干净"(加法重建必然留下断口——
被删旧线与保留线交叉处、keep 掩膜边缘),**模型负责"接得完整"**。
模型只经由已验证的外科通道:裁片整片编辑 + 只贴回裁片区 + 判据:
  · 保留判据:框内原有墨迹 ≥95% 保留(模型只许添墨不许移线)
  · 增量判据:新增墨迹 ≤ 框内原墨迹 60%(防画蛇添足)
断口检测:骨架化 → 端点(骨架上恰 1 邻居) → 跨连通域的近距端点对 = 断口。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.morphology import skeletonize

sys.path.insert(0, str(Path(__file__).parent))
from rp_common import image_edit

REPAIR_PROMPT = (
    "This is a zoomed-in crop of a Japanese anime key animation drawing (clean black "
    "line art on plain light-green paper). Some line strokes are BROKEN mid-stroke. "
    "Reconnect every broken stroke by drawing the missing short segment along the "
    "stroke's natural trajectory, matching its thickness and darkness. Do NOT move, "
    "reshape or redraw any existing line; do NOT add any new element, detail or "
    "shading. Output the same crop with only the breaks bridged."
)


def ink_mask(img):
    paper = np.median(img.reshape(-1, 3), axis=0)
    return (np.abs(img - paper).sum(axis=2) > 60), paper


def detect_gaps(img, max_gap=16):
    """返回断口中点列表 [(x,y),...]:不同连通域的骨架端点、距离 ≤ max_gap。"""
    ink, _ = ink_mask(img)
    ink = ndimage.binary_closing(ink, iterations=1)
    skel = skeletonize(ink)
    nb = ndimage.convolve(skel.astype(int), np.ones((3, 3)), mode="constant")
    endpoints = skel & (nb == 2)                      # 自身1+邻居1
    lbl, n = ndimage.label(ink)
    sizes = ndimage.sum_labels(np.ones_like(lbl), lbl, index=np.arange(1, n + 1))
    eys, exs = np.nonzero(endpoints)
    pts = np.stack([exs, eys], axis=1)
    comps = lbl[eys, exs]
    gaps = []
    for i in range(len(pts)):
        # 端点必须属于足够大的连通域 —— 虚线装饰框的短段(10-20px)天然成对断口,
        # 不滤会把修补框引到纯纸面上(实撞:1380 个"断口"大半是虚线框)
        if sizes[comps[i] - 1] < 40:
            continue
        d = np.abs(pts - pts[i]).sum(axis=1)
        for j in np.nonzero((d > 0) & (d <= max_gap))[0]:
            if comps[i] != comps[j] and i < j and sizes[comps[j] - 1] >= 40:
                gaps.append(tuple((pts[i] + pts[j]) // 2))
    return gaps


def cluster_boxes(gaps, img_shape, ctx=150, max_boxes=6):
    """断口中点贪心聚类成修补框(ctx 为半径),按覆盖断口数排序取前 max_boxes。"""
    remaining = list(gaps)
    boxes = []
    while remaining and len(boxes) < max_boxes:
        cx, cy = remaining[0]
        members = [(x, y) for x, y in remaining if abs(x - cx) < ctx and abs(y - cy) < ctx]
        xs = [p[0] for p in members]
        ys = [p[1] for p in members]
        x0 = max(0, min(xs) - 60); y0 = max(0, min(ys) - 60)
        x1 = min(img_shape[1], max(xs) + 60); y1 = min(img_shape[0], max(ys) + 60)
        boxes.append(((x0, y0, x1, y1), len(members)))
        remaining = [p for p in remaining if p not in members]
    boxes.sort(key=lambda t: -t[1])
    return [b for b, _ in boxes]


def repair(img_path, out_path, work_dir, max_boxes=6):
    img = np.array(Image.open(img_path).convert("RGB"))
    gaps = detect_gaps(img.astype(int))
    print(f"[repair] 检测到断口 {len(gaps)} 处")
    if not gaps:
        Image.fromarray(img).save(out_path)
        return 0
    boxes = cluster_boxes(gaps, img.shape, max_boxes=max_boxes)
    work = Path(work_dir)
    fixed = 0
    for k, (x0, y0, x1, y1) in enumerate(boxes):
        crop = img[y0:y1, x0:x1]
        ink_b, _ = ink_mask(crop.astype(int))
        if float(ink_b.mean()) < 0.005:          # 纯纸面框跳过,不给模型画蛇添足的机会
            print(f"[repair box{k}] 墨迹密度过低,跳过")
            continue
        pin = work / f"_repair_{k}_in.png"
        pout = work / f"_repair_{k}_out.png"
        Image.fromarray(crop).resize((1024, 1024), Image.LANCZOS).save(pin)
        ok = False
        for attempt in range(2):
            image_edit([pin], REPAIR_PROMPT, pout, size="1024x1024")
            got = np.array(Image.open(pout).convert("RGB")
                           .resize((x1 - x0, y1 - y0), Image.LANCZOS))
            ink_before, _ = ink_mask(crop.astype(int))
            ink_after, _ = ink_mask(got.astype(int))
            # 2px 容差:接线卷难免亚像素漂移,逐像素精确重合会把好卷también拒掉;
            # 真正的重画(几何漂移>2px)仍然过不了
            after_d = ndimage.binary_dilation(ink_after, iterations=2)
            before_d = ndimage.binary_dilation(ink_before, iterations=2)
            keep_rate = float((ink_before & after_d).sum() / max(1, ink_before.sum()))
            added = float((ink_after & ~before_d).sum() / max(1, ink_before.sum()))
            print(f"[repair box{k} roll{attempt}] 原墨保留 {keep_rate:.1%} 新增 {added:.1%}")
            if keep_rate >= 0.95 and added <= 0.60:
                ok = True
                break
        if ok:
            # 贴回=纸色配平+8px羽化(与耳环片同法);裸贴会留色调矩形(实撞)
            base_box = img[y0:y1, x0:x1].astype(int)
            gi = got.astype(int)
            bb = base_box.sum(axis=2) > 600
            bp = gi.sum(axis=2) > 600
            if bb.any() and bp.any():
                off = np.median(base_box[bb], axis=0) - np.median(gi[bp], axis=0)
                got = np.clip(gi + off, 0, 255).astype(np.uint8)
            h, w = got.shape[:2]
            ramp = np.minimum.outer(np.minimum(np.arange(h), np.arange(h)[::-1]),
                                    np.minimum(np.arange(w), np.arange(w)[::-1]))
            alpha = np.clip(ramp / 8, 0, 1)[..., None]
            img[y0:y1, x0:x1] = np.clip(
                base_box * (1 - alpha) + got.astype(float) * alpha, 0, 255).astype(np.uint8)
            fixed += 1
        else:
            print(f"[repair box{k}] 两卷判据都不过,该框放弃(保留断裂,如实入账)")
    Image.fromarray(img).save(out_path)
    print(f"[repair] 修补 {fixed}/{len(boxes)} 框")
    return fixed
