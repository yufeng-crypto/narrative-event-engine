# -*- coding: utf-8 -*-
"""实验A(端到端):带修正注释的原稿直接喂 images.edit,让生图模型自己读红笔并执行。

⚠ 提示词不许透露具体修正内容 —— 这一路测的就是"模型能否自己读懂批注"。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rp_common import CORPUS, OUT, image_edit

CASE = "hair_flow"
SRC = CORPUS / "头发的飘动方向可以配合／对齐处理.jpg"

PROMPT_A = (
    "This is a Japanese anime key animation (genga) sheet. The black lines and light-blue "
    "pencil are the original drawing. The colored pen strokes (green/red/orange) and the "
    "handwritten Japanese notes are the animation supervisor's correction instructions "
    "(shuusei). Read and understand every correction instruction on the sheet, then APPLY "
    "them to the drawing. Output the corrected key animation drawing: preserve the original "
    "black line art and light-blue pencil shading exactly, changing ONLY what the corrections "
    "instruct. Remove all correction pen strokes, all handwritten annotation text, the peg-hole "
    "markers and frame guides. Plain light-green paper background, same framing and scale as "
    "the input. Clean line art style identical to the original drawing."
)

if __name__ == "__main__":
    out = OUT / CASE / "expA_e2e.png"
    print("calling images.edit ...", flush=True)
    p = image_edit([SRC], PROMPT_A, out, size="1536x1024")
    print("saved:", p)
