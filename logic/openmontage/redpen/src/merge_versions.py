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

    # 被取代的旧版 = **深色芯在蓝线 R 内的笔画 + 这些笔画自己的灰晕**(结构性判据)。
    # 两个都踩过的坑,别回去:
    # · 只删深色芯(RGB各<110) ⇒ 抗锯齿灰晕存活,旧线以"被橡皮擦过"的灰痕留在纸上;
    # · "R内一切灰性墨迹都算旧版" ⇒ 把恰好离蓝线近的**正式画**也吃掉(眼睛内部被抹空,
    #   2026-09-02 实撞)。蓝线近旁 ≠ 被取代;被取代的判据是"它的深色芯要被删"。
    core = (r < 110) & (g < 110) & (b < 110) & ~blue
    dist_to_blue = ndimage.distance_transform_edt(~blue)
    core_removed = core & (dist_to_blue <= radius)
    # 灰晕 = 被删芯周边 3px 内的灰性像素(偏离纸色+低饱和,排除蓝/彩色 trace)
    paper_dist = np.abs(img - paper).sum(axis=2)
    grayish = (paper_dist > 25) & (np.ptp(img, axis=2) < 45) & (b - r <= 15)
    halo_zone = ndimage.binary_dilation(core_removed, iterations=3)
    superseded = (core_removed | (grayish & halo_zone)) & ~blue
    for x0, y0, x1, y1 in protect:
        superseded[y0:y1, x0:x1] = False

    out = img.copy()
    out[superseded] = paper          # 先抹旧版(含灰晕)
    ink = [40, 40, 40]               # 再落新版:蓝线变正式线(与原线稿墨色一致)
    out[blue] = ink

    Image.fromarray(out.astype(np.uint8)).save(out_path)
    stats = dict(blue_px=int(blue.sum()), superseded_px=int(superseded.sum()),
                 radius=radius, paper=paper)
    print("merged:", out_path, stats)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--radius", type=int, default=45)
    a = ap.parse_args()
    merge(a.src, a.out, a.radius)
