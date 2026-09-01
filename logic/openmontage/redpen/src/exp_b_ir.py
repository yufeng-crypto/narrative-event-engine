# -*- coding: utf-8 -*-
"""实验B(结构化中介):VLM 解读批注 → 修正IR(JSON) → 编译成显式指令 → images.edit 执行。

与实验A同一张输入图、同一个执行模型;唯一变量 = 提示词里有没有显式修正指令。
"""
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rp_common import CORPUS, OUT, client, image_edit

CASE = "hair_flow"
SRC = CORPUS / "头发的飘动方向可以配合／对齐处理.jpg"
VLM = "gpt-4o"

INTERPRET_PROMPT = """\
You are an expert in Japanese anime production. This image is a key animation sheet (原画) \
that may carry the animation supervisor's correction annotations (修正指示).

⚠ A genga sheet carries TWO INDEPENDENT systems of colored lines. You MUST distinguish them:

(1) COLOR TRACE (色トレス) — part of the DRAWING itself, instructions to the paint department:
    - BLACK: main lines (実線). LIGHT-BLUE pencil: shadow boundary (影指定).
    - RED thin lines hugging forms (e.g. small marks on hair): highlight boundary (ハイライト指定).
    - YELLOW-GREEN/EMERALD lines hugging forms: other color separation.
    These are NOT corrections. Do NOT list them as corrections; do NOT generate edit
    instructions for them; they must be PRESERVED in the drawing.

(2) CORRECTION ANNOTATIONS (修正指示) — the supervisor's instructions to the animator:
    rough/gestural pen strokes, circles, X marks, leader lines, redrawn shapes, and
    handwritten Japanese text. Cues: gestural not form-hugging; sits in margins or crosses
    over the drawing; often paired with text.

(3) METADATA: cel notations like "Aの3", circled numbers, greetings (よろしくお願いします),
    timing/process notes — not drawing changes.

Task: enumerate EVERY correction annotation (system 2) on this sheet. For each, output an object:
- id: short slug
- color: pen color
- location: where on the drawing it points to, in plain words
- transcription: the Japanese text as written (empty if pure stroke)
- translation: English translation
- type: one of replace / displace / indicate / constrain / annotate / delete / meta
  (delete = crossing out something; constrain = states a condition, e.g. "align hair flow";
   meta = cel numbers, greetings, timing notes — not a drawing change)
- edit_instruction: ONE concrete imperative sentence telling an image editor exactly what to
  change in the drawing (empty for type=meta). Be specific about what and where.

Return ONLY a JSON object: {"corrections": [...]}."""


def interpret(src: Path) -> dict:
    cli = client()
    b64 = base64.b64encode(src.read_bytes()).decode()
    r = cli.chat.completions.create(
        model=VLM,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": INTERPRET_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
        response_format={"type": "json_object"},
    )
    return json.loads(r.choices[0].message.content)


def compile_prompt(ir: dict) -> str:
    lines = []
    n = 0
    for c in ir["corrections"]:
        if c.get("type") == "meta" or not c.get("edit_instruction"):
            continue
        n += 1
        lines.append(f"{n}. {c['edit_instruction']}")
    body = "\n".join(lines)
    return (
        "This is a Japanese anime key animation (genga) sheet. The black lines and light-blue "
        "pencil are the original drawing; colored pen strokes and handwritten notes are "
        "correction annotations.\n"
        "Apply EXACTLY the following corrections to the drawing:\n"
        f"{body}\n"
        "Everything else in the drawing must stay exactly as drawn (same lines, same framing, "
        "same scale). PRESERVE all color-trace lines — they are part of the drawing: light-blue "
        "shadow boundary lines, thin red highlight marks hugging the forms, yellow-green color "
        "separation lines. Remove ONLY the correction pen strokes listed above, all handwritten "
        "annotation text, cel-number notations, the peg-hole markers and frame guides. Plain "
        "light-green paper background. Clean line art style identical to the original drawing."
    )


if __name__ == "__main__":
    out_dir = OUT / CASE
    out_dir.mkdir(parents=True, exist_ok=True)
    print("interpreting via", VLM, "...", flush=True)
    ir = interpret(SRC)
    (out_dir / "ir.json").write_text(json.dumps(ir, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(ir, ensure_ascii=False, indent=2))
    prompt = compile_prompt(ir)
    (out_dir / "expB_prompt.txt").write_text(prompt, encoding="utf-8")
    print("\ncalling images.edit ...", flush=True)
    p = image_edit([SRC], prompt, out_dir / "expB_ir.png", size="1536x1024")
    print("saved:", p)
