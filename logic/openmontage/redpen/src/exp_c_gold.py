# -*- coding: utf-8 -*-
"""实验C(金标准解读=WoZ上限):人工判读的精确指令 → images.edit 执行。

隔离变量:解读质量。C 成功而 B 失败 ⇒ 瓶颈在 VLM 解读端,执行端成立。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rp_common import CORPUS, OUT, image_edit

CASE = "hair_flow"
SRC = CORPUS / "头发的飘动方向可以配合／对齐处理.jpg"

PROMPT_C = (
    "This is a Japanese anime key animation (genga) sheet. The black lines and light-blue "
    "pencil are the original drawing; colored pen strokes and handwritten notes are the "
    "supervisor's correction annotations.\n"
    "Apply EXACTLY the following corrections to the drawing:\n"
    "1. DELETE the earring — the two small hanging rings at the base of the character's left "
    "horn (screen-left, marked with a green X on the sheet). Remove the double rings entirely; "
    "the horn base and nearby hair must look natural, as if the earring never existed.\n"
    "2. Unify the hair flow: all loose hair strands should wave in ONE consistent direction, "
    "matching the overall leftward-blowing motion, instead of pointing in mixed directions.\n"
    "Everything else in the drawing must stay exactly as drawn (same lines, same framing, same "
    "scale, same face, same gaze). PRESERVE all color-trace lines that are part of the drawing "
    "(light-blue shadow lines). Remove the green correction strokes, all handwritten annotation "
    "text, cel-number notations, peg-hole markers and frame guides. Plain light-green paper "
    "background. Clean line art style identical to the original drawing."
)

if __name__ == "__main__":
    out = OUT / CASE / "expC_gold.png"
    print("calling images.edit ...", flush=True)
    p = image_edit([SRC], PROMPT_C, out, size="1536x1024")
    print("saved:", p)
