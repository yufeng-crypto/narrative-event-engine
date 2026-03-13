# markdown-to-feishu

将 Markdown 文档转换为飞书云文档的 Skill。支持流程图自动渲染、表格转换、代码块保留。

## 触发条件

当用户要求将 Markdown 文档转换为飞书文档时自动触发，或明确提及：
- "md 转飞书"
- "markdown 转飞书文档"
- "把 xxx.md 转为飞书"
- "导入飞书文档"

## 核心原则

1. **原文完全保留**：不改写、不概括、不遗漏任何内容
2. **视觉优化优先**：将 ASCII 表格转为飞书原生表格
3. **流程图增强**：检测流程图描述，自动插入 Board 可编辑流程图

## 转换规则

### 1. Heading 结构

| Markdown | 飞书 |
|----------|------|
| `# 标题` | Heading1 |
| `## 标题` | Heading2 |
| `### 标题` | Heading3 |

飞书会自动根据 Heading 生成目录树。

### 2. 代码块

- 识别 Markdown 代码块：\`\`\`json / \`\`\`python 等
- 使用 `feishu_doc` 的 `code` 格式插入
- 保留原始缩进和格式

### 3. 表格

- ASCII 表格（使用 `-` `|` 绘制）转为飞书原生表格
- **重要**：飞书单表格有行数限制（建议每表 ≤20 行），超长表格需拆分
- 表格内容逐行写入，使用 `feishu_doc` 的 `create_table` + `write_table_cells`

### 4. 流程图（重点）

检测以下内容时，自动调用 `feishu-flowchart` 渲染 Board 流程图：

**触发条件：**
- Mermaid 代码块：\`\`\`mermaid
- 流程图关键词：流程图、数据流、工作流、节点流向、时序图
- 文字版流程描述（带箭头 `↓` `→` `├──`）

**处理流程：**
1. 解析流程图内容（提取 Mermaid 或转换为 Mermaid）
2. 调用 `feishu-flowchart` 脚本渲染 Board 图
3. 在流程图位置插入 Board 块
4. **保留原文**：流程图下方的文字描述一并保留

**调用方式：**
```bash
python skills/feishu-flowchart/scripts/board_render.py \
  --doc-token <DOC_TOKEN> \
  --mermaid-file <mermaid_file> \
  --title "流程图标题"
```

### 5. 文档创建

**必须使用 `feishu-create-doc`（不是 feishu-doc）：**
1. 先用 `feishu_wiki` 或 `feishu_doc` 创建空文档
2. 获取 `doc_token`
3. 分段 `append` 内容（飞书有单次写入长度限制，建议每段 <5000 字符）

## 执行步骤

### Step 1: 创建文档
```python
feishu_wiki(
  action="create",
  space_id="<知识库ID>",
  title="<文档标题>",
  obj_type="docx"
)
```

### Step 2: 解析 Markdown
读取源文件，按以下顺序处理：
1. 提取所有 Heading，保留层级
2. 识别代码块，标记位置
3. 识别表格，解析行列
4. 识别流程图（Mermaid 或文字版）

### Step 3: 分段写入
- 每段内容 <5000 字符
- 表格单独写入（用 create_table + write_table_cells）
- 流程图单独处理（先写文字描述，再调用 board_render）

### Step 4: 内容校验
完成后必须校验：
1. 读取飞书文档内容
2. 与原 Markdown 对比段落数
3. 确认无截断、无遗漏

## 工具清单

| 工具 | 用途 |
|------|------|
| `feishu_wiki` | 创建知识库文档 |
| `feishu_doc` | 追加内容、创建表格、代码块 |
| `feishu-flowchart` | 渲染 Board 流程图 |
| `exec` | 调用 Python 脚本 |

## 错误处理

| 错误场景 | 处理方式 |
|----------|----------|
| 表格超行 | 拆分为多个表格，分别写入 |
| 流程图渲染失败 | 保留原文字描述，跳过 Board 图 |
| 内容超长 | 分多段 append |
| 权限不足 | 用 `feishu_perm` 添加权限 |

## 输出示例

转换完成后，返回：
- 飞书文档链接
- 插入的表格数量
- 插入的流程图数量
- **内容校验报告**（必须包含以下清单项）

## 补充说明

### 表格拆分策略
飞书单表格限制约 20 行，超过时需拆分为多个表格：
- 原始表格 >20 行 → 拆分为 2 个或更多表格
- 每个表格单独 create_table + write_table_cells
- 标题注明"（续）"区分

### 流程图保留策略
- **Board 图**：可编辑，推荐使用
- **原文字描述**：始终保留，不删除
- 顺序：先文字描述 → 后 Board 图

### ⚠️ 必须执行的内容校验清单

**每次转换完成后，必须执行以下校验步骤：**

1. **标题数量校验**
   - 读取源 Markdown 文件，统计 Heading（# ## ###）数量
   - 读取飞书文档，对比数量是否一致
   
2. **代码块数量校验**
   - 统计源文件中的 \`\`\` 代码块数量
   - 统计飞书文档中的 Code 块数量
   
3. **表格数量校验**
   - 统计源文件中的 | 表格数量
   - 统计飞书文档中的 Table 块数量（拆分后应更多）
   
4. **流程图校验**
   - 确认 Board 流程图已插入
   - 确认原文字描述保留在流程图上方
   
5. **段落完整性校验**
   - 抽样检查关键段落（每章前200字）
   - 确认无非预期截断

**如果校验不通过：**
- 标记缺失内容
- 补写缺失部分
- 重新校验直至通过

### 依赖 Skills
- `feishu-flowchart`：用于渲染 Board 流程图
- `feishu-doc`：用于内容写入
- `feishu-wiki`：用于知识库创建
