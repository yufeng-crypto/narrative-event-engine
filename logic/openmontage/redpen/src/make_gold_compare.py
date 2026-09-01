# -*- coding: utf-8 -*-
"""生成 gold 混合管线对照页(自包含单文件 HTML,图片全内嵌)。

产物:out/<case>/compare.html + ASCII 路径副本 out/compare_gold.html
(部分浏览器对中文路径 file:// 不友好;本机静态服务=launch.json redpen-out,端口 8791)。
"""
import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "out" / "头发的飘动方向可以配合_对齐处理"
SRC = ROOT.parent / "芙莉莲" / "头发的飘动方向可以配合／对齐处理.jpg"


def b64img(p):
    ext = p.suffix.lstrip(".").lower().replace("jpg", "jpeg")
    return f"data:image/{ext};base64," + base64.b64encode(p.read_bytes()).decode()


def main():
    ir = json.loads((ROOT / "corpus/gold/hair_flow.ir.json").read_text(encoding="utf-8"))
    rows = "".join(
        f"<tr><td>{c.get('color','')}</td><td>{c.get('type','')}/{c.get('scope','')}</td>"
        f"<td>{c.get('transcription','')}</td><td>{c.get('translation','')}</td>"
        f"<td>{c.get('edit_instruction','') or '(跨张指令,本张执行=两版合并)'}</td></tr>"
        for c in ir.get("corrections", []))
    stages = [
        ("① 两版合并(代码·加法重建)", B / "merged_1536.png", "蓝线版几何;旧线零残迹;切口坐标导出给④"),
        ("② 删耳环(模型·裁片贴回)", B / "final_masked.png", "片外字节不变"),
        ("③ 批注清除(代码)", B / "final_clean.png", "逐框纸色回填+去光晕"),
        ("④ 断线修补(模型·裁片)", B / "final_repaired.png", "上游切口+事后检测断口;三判据兜底"),
    ]
    strip = "".join(
        f"<div class='st'><h4>{t}</h4><img src='{b64img(p)}'><p>{note}</p></div>"
        for t, p, note in stages if p.is_file())
    html = f"""<!doctype html><meta charset="utf-8"><title>redpen · gold 混合管线对照</title>
<style>body{{font-family:system-ui;margin:16px;background:#fafafa;color:#222}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.pair img,.st img{{width:100%;border:1px solid #ccc;background:#fff}}
h3,h4{{margin:6px 0}} .strip{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px}}
.st p{{font-size:12px;color:#555;margin:4px 0}}
table{{border-collapse:collapse;margin-top:16px;font-size:13px;background:#fff}}
td,th{{border:1px solid #bbb;padding:4px 8px}}
.meta{{font-size:13px;color:#444;margin-top:10px}}</style>
<h2>gold(人工解读)· 混合管线 最终对照</h2>
<div class="pair">
<div><h3>原稿(带修正批注)</h3><img src="{b64img(SRC)}"></div>
<div><h3>最终成图 final_repaired</h3><img src="{b64img(B / 'final_repaired.png')}"></div>
</div>
<div class="meta">图层语义:蓝线=作监修正版线稿,黑线=原稿rough;两版合并采纳蓝线几何(量化=src/verify_geometry.py)。
分工=代码删得干净(加法重建,残迹构造上不存在)/模型接得完整(外科裁片,三判据兜底)。</div>
<h3>四阶段产物</h3>
<div class="strip">{strip}</div>
<h3>金标准修正 IR(v2 语义)</h3>
<table><tr><th>颜色</th><th>类型/域</th><th>原文</th><th>译文</th><th>执行方式</th></tr>{rows}</table>
"""
    out = B / "compare.html"
    out.write_text(html, encoding="utf-8")
    (ROOT / "out" / "compare_gold.html").write_text(html, encoding="utf-8")
    print("saved:", out, "+ out/compare_gold.html")


if __name__ == "__main__":
    main()
