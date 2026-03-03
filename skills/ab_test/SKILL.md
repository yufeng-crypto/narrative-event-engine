# SKILL.md - AB测试自动化

## 用途
运行10轮AB测试（有引擎 vs 无引擎），用于验证引擎效果

## 适用场景
- 测试新角色的对话效果
- 对比有/无引擎的对话质量
- 验证Director/Predictor/Performer流程

## 使用方法

### 1. 准备角色文件
角色JSON文件需包含：
```json
{
  "name": "角色名",
  "role_id": "角色ID",
  "world": "世界观",
  "content": "角色设定",
  "axes": {"Intimacy": 3, "Risk": 6, "Info": 5, "Action": 4, "Rel": 2, "Growth": 7}
}
```

### 2. 运行测试
```bash
cd C:\Users\20731\.openclaw\workspace\logic\test_logs
python run_ab_test.py <角色文件路径> <输出目录>
```

### 3. 示例对话场景
```python
DIALOGUE_SCENARIOS = [
    {"type": "积极", "input": "姐姐一个人在这冷宫，可还好？"},
    {"type": "消极", "input": "随便你，我走了"},
    {"type": "冷淡", "input": "嗯"},
    {"type": "深入", "input": "你为什么会在冷宫？"},
    {"type": "好奇", "input": "姐姐以前在宫里是什么位份？"},
    {"type": "同情", "input": "这冷宫的生活一定很苦吧"},
    {"type": "试探", "input": "姐姐可曾后悔入宫？"},
    {"type": "关心", "input": "姐姐要注意身体才是"},
    {"type": "追问", "input": "那件事...就是姐姐家族蒙冤的事？"},
    {"type": "坦诚", "input": "实不相瞒，我是来帮姐姐的"},
]
```

## 输出文件

### 有引擎 (run_XX_with_engine)
- test_input.json - 测试输入
- director_output.json - Director输出
- predictor_output.json - Predictor输出
- performer_output.json - Performer输出
- dialogue.json - 完整对话

### 无引擎 (run_XX_without_engine)
- test_input.json
- dialogue.json

## 验证要点

### Director
- beat 必须是 EVOLVE/STALL/HOLD/PIVOT 之一
- 必须有 patch_status 字段
- 必须有 beat_plan（反应拍+演进拍+钩子拍）

### Predictor
- archetype_ref 必须以 ARC_ 开头
- 必须有 trigger_condition
- 必须有 choices 和 impact_delta

### Performer
- 对话必须符合 beat_plan
- 不能偏离角色设定

## 注意事项
- 无引擎调用需确保角色设定正确传入
- 每轮测试需传入上一轮对话历史
- 修复截断问题：director_output 和 npc_context 不能截断
