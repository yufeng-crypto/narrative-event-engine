# -*- coding: utf-8 -*-
"""几何验证件:merge/replace 类指令的执行证据 —— 输出轮廓必须贴近目标图层。

来源(2026-09-02,用户发现):蓝线合并"完全执行"是假阳性 —— 执行器消掉了蓝色、
合成单版,但肩线几何谁都没跟(离黑17.5px/离蓝18.7px,自画折中线)。
**表面服从**(满足指令的视觉签名、不执行几何内容)只看成图发现不了,
必须逐列比对输出轮廓 vs 目标图层轮廓。

用法:
    python src/verify_geometry.py <src.jpg> <corrected.png> --x0 120 --x1 400 --y0 900
输出:输出↔原稿层 / 输出↔目标层 的平均距离与判定(target 必须显著更近才算执行)。
"""
import argparse
import numpy as np
from PIL import Image


def top_contour(mask: np.ndarray, x: int, y0: int) -> int | None:
    col = np.where(mask[y0:, x])[0]
    return y0 + int(col[0]) if len(col) else None


def run(src_path, out_path, x0, x1, y0, step=10):
    src = np.array(Image.open(src_path).convert("RGB")).astype(int)
    out = np.array(Image.open(out_path).convert("RGB")).astype(int)
    r, g, b = src[:, :, 0], src[:, :, 1], src[:, :, 2]
    black_s = (r < 110) & (g < 110) & (b < 110)
    blue_s = (b - r > 30) & (b > 120)
    ro, go, bo = out[:, :, 0], out[:, :, 1], out[:, :, 2]
    black_o = (ro < 110) & (go < 110) & (bo < 110)

    sx = out.shape[1] / src.shape[1]
    sy = out.shape[0] / src.shape[0]
    d_orig, d_target, n = 0.0, 0.0, 0
    for x in range(x0, x1, step):
        yb = top_contour(black_s, x, y0)
        yu = top_contour(blue_s, x, y0)
        yo = top_contour(black_o, int(x * sx), int(y0 * sy))
        if yb is None or yu is None or yo is None:
            continue
        yo_src = yo / sy
        d_orig += abs(yo_src - yb)
        d_target += abs(yo_src - yu)
        n += 1
    if not n:
        print("no comparable columns — 区间选错或图层掩膜为空")
        return 2
    d_orig /= n
    d_target /= n
    adopted = d_target < d_orig * 0.5          # 判据:必须**显著**贴近目标层,不是险胜
    print(f"输出↔原稿层 {d_orig:.1f}px | 输出↔目标层 {d_target:.1f}px (n={n})")
    print("判定:", "✓ 已采纳目标几何" if adopted else "✗ 未采纳(表面服从/折中线)")
    return 0 if adopted else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("corrected")
    ap.add_argument("--x0", type=int, required=True)
    ap.add_argument("--x1", type=int, required=True)
    ap.add_argument("--y0", type=int, required=True)
    a = ap.parse_args()
    raise SystemExit(run(a.src, a.corrected, a.x0, a.x1, a.y0))
