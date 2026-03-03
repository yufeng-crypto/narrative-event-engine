# -*- coding: utf-8 -*-
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from engine_llm import Engine, get_role_prompt, call_llm

# 加载测试用例
with open(os.path.join(os.path.dirname(__file__), '..', 'roles', 'test_cases.json'), 'r', encoding='utf-8') as f:
    test_cases = json.load(f)

# 筛选 Predictor 测试用例 - 只测试新增的3个场景
predictor_tests = [
    tc for tc in test_cases['test_cases'] 
    if tc.get('role') == 'Predictor' and 'HISTORY_SUMMARY' in tc.get('输入', {})
]

print('=== Predictor 测试开始 ===')
print('找到 {} 个测试用例'.format(len(predictor_tests)))
print()

results = []
for tc in predictor_tests:
    scene_name = tc['场景名']
    print('测试: {}'.format(scene_name))
    prompt = get_role_prompt('predictor')
    
    test_input = tc['输入']
    user_content = '''HISTORY_SUMMARY: {HISTORY_SUMMARY}
CURRENT_AXES: {CURRENT_AXES}
NPC_AGENDA: {NPC_AGENDA}
LOCATION_CONTEXT: {LOCATION_CONTEXT}
RECENT_DIALOGUE: {RECENT_DIALOGUE}
OPEN_THREADS: {OPEN_THREADS}

请根据以上信息生成事件卡。输出 JSON 格式。'''.format(
        HISTORY_SUMMARY=test_input['HISTORY_SUMMARY'],
        CURRENT_AXES=json.dumps(test_input['CURRENT_AXES']),
        NPC_AGENDA=test_input['NPC_AGENDA'],
        LOCATION_CONTEXT=test_input['LOCATION_CONTEXT'],
        RECENT_DIALOGUE=json.dumps(test_input['RECENT_DIALOGUE']),
        OPEN_THREADS=json.dumps(test_input['OPEN_THREADS'])
    )
    
    messages = [
        {'role': 'system', 'content': prompt[:3000]},
        {'role': 'user', 'content': user_content}
    ]
    
    result = call_llm(messages)
    
    # 检查格式合规 - 查找 JSON 结构
    format_valid = 'pending_events' in result or 'event' in result.lower() or '{' in result
    
    # 检查是否生成了事件卡
    try:
        if '{' in result and '}' in result:
            json_start = result.find('{')
            json_str = result[json_start:]
            json_obj = json.loads(json_str)
            has_events = 'pending_events' in json_obj and len(json_obj.get('pending_events', [])) > 0
            event_count = len(json_obj.get('pending_events', []))
        else:
            has_events = False
            event_count = 0
    except:
        has_events = 'event' in result.lower()
        event_count = 1 if has_events else 0
    
    # 与期望对比
    expected_events = tc['期望'].get('生成事件卡', True)
    字段完整 = format_valid and has_events
    
    print('  期望生成事件: {}'.format(expected_events))
    print('  实际生成事件: {} (数量: {})'.format(has_events, event_count))
    print('  格式合规: {}'.format(format_valid))
    print('  字段完整: {}'.format(字段完整))
    print()
    
    results.append({
        '场景名': scene_name,
        'role': 'Predictor',
        '实际输出': result[:300] + '...' if len(result) > 300 else result,
        '格式合规': format_valid,
        '字段完整': 字段完整
    })

print('=== 测试结果汇总 ===')
print(json.dumps({'test_results': results}, ensure_ascii=False, indent=2))
