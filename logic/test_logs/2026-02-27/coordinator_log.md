# 测试协调日志 - 2026-02-27

## 修复内容
1. engine_llm.py - Performer 接收完整 director_output（不再截断）
2. engine_llm.py - Director 接收完整 npc_context（不再截断）

## 重新测试
- 角色: 沈氏 (character_palace.json)
- 目录: ab_test_001
- 状态: 进行中

## 待验证
- Performer 是否按 beat_plan 执行
- 上下文是否正确传递（1-10轮不丢失）
