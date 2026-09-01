# -*- coding: utf-8 -*-
"""确定性两版合并:采纳蓝线版几何,剔除被取代的黑 rough 线。纯像素操作,不烧生成模型。

来源(失败模式6):"采纳B版几何"三轮迭代证明超出 raster edit 模型可靠通道——
模型只会表面服从(消蓝不改形)。而这一步本质是确定性的:
  1. 蓝线像素 → 变成正式黑线(蓝线本身就是目标几何)
  2. 距蓝线 R 像素内的黑线像素 → 视为被取代的旧版,抹成纸色
     (安全性依据:蓝线只画在被修正的部位;那里的替代线由蓝线自己提供)
  3. 其余(脸/眼/无蓝区域的黑线、绿色分色标记、批注文字)原样保留
生成模型只负责下游:对象删除/批注清除/缝合(在合并后的中间稿上跑)。

用法: python src/merge_versions.py <sheet.jpg> <out.png> [--radius 45]
"""
import argparse
import numpy as np
from PIL import Image
from scipy import ndimage


def merge(src_path, out_path, radius=45, protect=()):
    """protect: [(x0,y0,x1,y1), ...] 源图坐标的保护区 —— 区内不做任何删除。

    ⚠ 蓝线重绘区 ≠ 全图:眼睑等处有蓝色**点缀笔触**(不是版本重绘),一揽子
    "距蓝线R内即旧版"会把那里的正式线蚕食成灰壳(v1 起即有,被残留灰晕遮蔽,
    2026-09-02 用户发现)。合并必须限定区域;区域与 bbox 同源,worker 化后由 IR 供给。"""
    img = np.array(Image.open(src_path).convert("RGB")).astype(int)
    r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]

    blue = (b - r > 30) & (b > 120)

    # 纸色 = 全图中位色(纸面占绝对多数,中位数就是纸)
    paper = np.median(img.reshape(-1, 3), axis=0)

    # ⚠ 减法路(在扫描上擦旧线)追了三轮阈值仍有漏网灰痕:v1 只删深色芯留灰晕;
    #   v2 芯+自身晕,通体浅灰的轻笔画整根幸存;v3 R内一切灰性墨迹,右角仍剩
    #   蓝灰色调/低于阈值的绒毛残迹 —— 每类残迹都是一轮迭代,追不完。
    # 定稿=**加法重建**:纯纸色画布上只落"要保留的墨迹"(保留黑线/彩色trace/
    #   保护区整块搬运/蓝转正式线);被删的线在构造上不可能留任何残迹。
    paper_dist = np.abs(img - paper).sum(axis=2)
    ptp = np.ptp(img, axis=2)
    dist_to_blue = ndimage.distance_transform_edt(~blue)

    colored = ((g - r > 40) & (g > 120)) | ((r - g > 40) & (r > 120)) | blue \
              | ((b - r > 15) & (b > 150))            # 绿/红 trace、蓝、淡水色
    gray_ink = (paper_dist > 20) & (ptp < 45) & (b - r <= 15)
    keep = colored | (gray_ink & (dist_to_blue > radius))
    # 去噪:纯色画布会让 JPEG 噪斑显形(在原扫描里融在纸纹里),<6px 的孤立碎点丢弃
    lbl, n = ndimage.label(keep)
    sizes = ndimage.sum_labels(np.ones_like(lbl), lbl, index=np.arange(1, n + 1))
    keep &= np.isin(lbl, np.arange(1, n + 1)[sizes >= 6])
    keep = ndimage.binary_dilation(keep, iterations=1)  # 带上保留线自己的抗锯齿晕

    out = np.empty_like(img)
    out[:] = paper                                     # 画布=纯纸色
    out[keep] = img[keep]                              # 只落保留墨迹(原像素)
    for x0, y0, x1, y1 in protect:
        out[y0:y1, x0:x1] = img[y0:y1, x0:x1]          # 保护区整块原样搬运
    ink = [40, 40, 40]
    out[blue] = ink                                    # 蓝线变正式线(含保护区内)
    superseded = gray_ink & (dist_to_blue <= radius)   # 仅供统计

    Image.fromarray(out.astype(np.uint8)).save(out_path)

    # 切口导出:半径判据逐像素,会把保留笔画拦腰切开(发梢"像被刀割",用户 2026-09-02
    # 抓的)。合并段自己最清楚在哪里下了刀 —— 保留墨迹与被删墨迹的邻接处=切口,
    # 坐标交给修补段当种子,不靠事后猜断口。
    removed = gray_ink & ~keep
    cut_mask = keep & gray_ink & ndimage.binary_dilation(removed, iterations=2)
    cys, cxs = np.nonzero(cut_mask)
    cuts = []
    taken = np.zeros(len(cxs), dtype=bool)
    pts = np.stack([cxs, cys], axis=1)
    for i in range(len(pts)):                      # 20px 贪心去重
        if taken[i]:
            continue
        cuts.append((int(pts[i][0]), int(pts[i][1])))
        taken |= (np.abs(pts - pts[i]).sum(axis=1) < 20)

    stats = dict(blue_px=int(blue.sum()), superseded_px=int(superseded.sum()),
                 radius=radius, paper=paper, cuts=cuts)
    print("merged:", out_path, {k: v if k != "cuts" else f"{len(v)}处" for k, v in stats.items()})
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--radius", type=int, default=45)
    a = ap.parse_args()
    merge(a.src, a.out, a.radius)
