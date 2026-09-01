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

sys.path.insert(0, str(Path(__file__).parent))
from rp_common import CORPUS, OUT, image_edit
from merge_versions import merge

SRC = CORPUS / "头发的飘动方向可以配合／对齐处理.jpg"
B = OUT / "头发的飘动方向可以配合_对齐处理"
FRAME = (130, 230, 1750, 1310)          # 作画框(1620x1080=3:2,与输出同比例=闸可用)
EARRING_BOX = (175, 120, 345, 260)      # 1536x1024 坐标系
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
    # 2. masked inpaint:删耳环(外科,mask 外不许改几何)
    mask = Image.new("RGBA", (1536, 1024), (0, 0, 0, 255))
    x0, y0, x1, y1 = EARRING_BOX
    a = np.array(mask)
    a[y0:y1, x0:x1, 3] = 0
    Image.fromarray(a).save(B / "mask_earring.png")
    image_edit([B / "merged_1536.png"],
               "Remove the double-ring earring hanging at the base of the left horn "
               "entirely. Fill with the plain paper background and continue the horn-base "
               "contour and nearby hair strands naturally in the same clean black line art "
               "style. Change nothing else.",
               B / "final_masked.png", size="1536x1024",
               mask_path=B / "mask_earring.png")
    gate(B / "final_masked.png", "inpaint")
    # 3. 确定性批注清除(纸面回填/局部去绿)
    img = np.array(Image.open(B / "final_masked.png").convert("RGB")).astype(int)
    r, g, bl = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    line = (r < 110) & (g < 110) & (bl < 110) | ((g - r > 40) & (g > 120))
    paper = [int(np.median(img[:, :, c][~line])) for c in range(3)]
    for bx in TEXT_FILL:
        img[bx[1]:bx[3], bx[0]:bx[2]] = paper
    for bx in TEXT_DEGREEN:
        reg = img[bx[1]:bx[3], bx[0]:bx[2]]
        gm = (reg[:, :, 1] - reg[:, :, 0] > 40) & (reg[:, :, 1] > 120)
        reg[gm] = paper
    Image.fromarray(img.astype(np.uint8)).save(B / "final_clean.png")
    gate(B / "final_clean.png", "final")
    print("hybrid pipeline done:", B / "final_clean.png")


if __name__ == "__main__":
    main()
