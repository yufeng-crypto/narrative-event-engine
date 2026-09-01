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


def merge(src_path, out_path, radius=45):
    img = np.array(Image.open(src_path).convert("RGB")).astype(int)
    r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]

    blue = (b - r > 30) & (b > 120)
    black = (r < 110) & (g < 110) & (b < 110)

    # 纸色 = 非线条区域的中位色(逐通道)
    paper_mask = ~(blue | black)
    paper = [int(np.median(img[:, :, c][paper_mask])) for c in range(3)]

    # 距蓝线的欧氏距离场;R 内的黑线像素 = 被取代的旧版
    dist_to_blue = ndimage.distance_transform_edt(~blue)
    superseded = black & (dist_to_blue <= radius)

    out = img.copy()
    out[superseded] = paper          # 先抹旧版
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
