# -*- coding: utf-8 -*-
import urllib.request, json, time, sys
API_KEY = 'sk-cp-cOK9G2O4ZpSb7TWE9OVx8-Pl1zq2yHzG_UgfzCRZ6JIMDa_O855-mB0U5oEgUe78CmnMDFOYEPcuQpDAAUikvApd509C0S5PGn5dxm4xCAwLWwKR1JYy5ss'
URL = 'https://api.minimaxi.com/v1/text/chatcompletion_v2'

def call(p):
    data = json.dumps({'model': 'MiniMax-M2.5', 'messages': [{'role': 'user', 'content': p}], 'max_completion_tokens': 200}).encode()
    r = urllib.request.Request(URL, data=data, method='POST')
    r.add_header('Authorization', 'Bearer ' + API_KEY)
    r.add_header('Content-Type', 'application/json')
    resp = urllib.request.urlopen(r, timeout=25)
    return json.loads(resp.read().decode())['choices'][0]['message']['content']

# 状态
axes = {'Intimacy': 2, 'Risk': 3, 'Info': 4, 'Action': 5, 'Rel': 1, 'Growth': 7}
user = '我给你刷个火箭'

print('[Engine] 初始化完成')
print('[Round 1] 用户: %s' % user)

# Director
print('[Director] ', end=''); sys.stdout.flush()
d = call('六轴=%s，用户：%s。输出JSON：beat和axis_changes' % (axes, user))
print(d[:100])

# Performer
print('[Performer] ', end=''); sys.stdout.flush()
p = call('你是沈予曦，傲娇主播。用户：%s。用傲娇语气回复。' % user)
print(p)

print('[Done]')
