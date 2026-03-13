---
name: feishu-flowchart
description: 在飞书文档中创建流程图，优先使用飞书画板（Board）可编辑节点渲染。使用场景：用户要求生成流程图、在飞书文档中添加图表、解析 Markdown 并将流程图内容可视化。输入支持 Mermaid 代码、Markdown 文本（含 mermaid 代码块）、流程描述文本。输出：在飞书文档中插入画板流程图（非图片优先）。
---

# Feishu Flowchart (Board-first)

在飞书文档中创建流程图，默认走 **飞书画板 API**，尽量不走“图片上传”方案。

## 触发条件（优先触发）

当用户出现以下任一意图时，应使用本 skill：

1. 明确要求“流程图 / 时序图 / 决策流程 / 架构流程图”
2. 要求“在飞书文档里画图 / 插入流程图 / 可编辑图”
3. 提供了 Markdown，并包含：
   - ` ```mermaid ` 代码块
   - 关键词：流程、判断、节点、状态、时序、泳道
4. 要求“解析 md 文档并在飞书文档展示流程”

## 输出策略（固定）

1. **默认输出**：飞书文档内画板（Board）节点图（可协作编辑）
2. **默认参数**：
   - `syntax_type = 2`（Mermaid）
   - `style_type = 1`（解析为多个画板节点）
3. 非用户明确要求，不使用“Mermaid 生成图片再插入”方案

## 标准执行流程

### 步骤 1：确定目标文档

- 若用户提供 docx 链接：提取 `doc_token`
- 若用户未提供：先创建文档（如“流程图-自动生成”）

### 步骤 2：准备画板容器（docx block）

通过文档块 API 在文档根块下插入一个 `block_type=43` 的 `board` 块。

请求体示例：

```json
{
  "children": [
    {
      "block_type": 43,
      "board": {}
    }
  ]
}
```

然后通过“获取文档所有块”找到该 block 的 `board.token`，作为 `whiteboard_id`。

### 步骤 3：生成 Mermaid（按输入类型）

- 输入本来就是 Mermaid：直接使用
- 输入是 Markdown：优先提取 ` ```mermaid ` 代码块
- 输入是流程描述文本：先转换为 Mermaid，再继续

### 步骤 4：写入画板节点（核心）

调用：

`POST /open-apis/board/v1/whiteboards/:whiteboard_id/nodes/plantuml`

请求体推荐：

```json
{
  "plant_uml_code": "flowchart TD\nA[开始]-->B{有输入?}\nB-->|是|C[处理]\nB-->|否|D[等待]\nC-->E[结束]\nD-->E",
  "syntax_type": 2,
  "style_type": 1,
  "diagram_type": 0
}
```

### 步骤 5：校验结果

调用 `GET /open-apis/board/v1/whiteboards/:whiteboard_id/nodes` 检查节点是否已生成。

## 失败降级策略（必须）

若画板解析失败：

1. 先重试一次（清洗 Mermaid：去 markdown 包裹、去无关前后文）
2. 仍失败：在文档里写入
   - 失败原因（简短）
   - 原 Mermaid 文本（代码块）
3. 不静默失败，不丢用户内容

## 工具使用建议

- 文档创建/补写：`feishu_doc`
- 文档权限：`feishu_perm`（必要时为用户加权限）
- 画板节点渲染：直接调用飞书开放 API（Python/Node）

## 注意事项

1. 画板在 docx 中是 `block_type=43`，字段名是 `board`（不是 `whiteboard`）
2. `board.token` 才是后续 Board API 的 `whiteboard_id`
3. `style_type=1` 才是“节点化结果”（非图片）
4. 若用户明确要“经典样式图像”，可用 `style_type=2`

## 最小可复用模板（Python）

```python
import requests

# 已有: tenant_access_token, doc_token, whiteboard_id
headers = {
    "Authorization": f"Bearer {tenant_access_token}",
    "Content-Type": "application/json; charset=utf-8"
}

mermaid = """flowchart TD
A[开始]-->B{条件}
B-->|是|C[执行]
B-->|否|D[等待]
C-->E[结束]
D-->E
"""

resp = requests.post(
    f"https://open.feishu.cn/open-apis/board/v1/whiteboards/{whiteboard_id}/nodes/plantuml",
    headers=headers,
    json={
        "plant_uml_code": mermaid,
        "syntax_type": 2,
        "style_type": 1,
        "diagram_type": 0
    },
    timeout=30,
)

print(resp.status_code, resp.text)
```
