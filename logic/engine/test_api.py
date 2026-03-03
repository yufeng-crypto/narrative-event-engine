# -*- coding: utf-8 -*-
import urllib.request, json, time, sys
API_KEY = 'sk-cp-cOK9G2O4ZpSb7TWE9OVx8-Pl1zq2yHzG_UgfzCRZ6JIMDa_O855-mB0U5oEgUe78CmnMDFOYEPcuQpDAAUikvApd509C0S5PGn5dxm4xCAwLWwKR1JYy5ss'
URL = 'https://api.minimaxi.com/v1/text/chatcompletion_v2'

sys.stdout.write('Test 1: ')
sys.stdout.flush()
try:
    data = json.dumps({'model': 'MiniMax-M2.5', 'messages': [{'role': 'user', 'content': 'hi'}]}).encode()
    r = urllib.request.Request(URL, data=data, method='POST')
    r.add_header('Authorization', 'Bearer ' + API_KEY)
    r.add_header('Content-Type', 'application/json')
    t1 = time.time()
    resp = urllib.request.urlopen(r, timeout=20)
    result = json.loads(resp.read().decode())
    print('OK %.1fs' % (time.time()-t1))
except Exception as e:
    print('FAIL: %s' % str(e)[:50])

sys.stdout.write('Test 2: ')
sys.stdout.flush()
try:
    data = json.dumps({'model': 'MiniMax-M2.5', 'messages': [{'role': 'user', 'content': 'hello'}]}).encode()
    r = urllib.request.Request(URL, data=data, method='POST')
    r.add_header('Authorization', 'Bearer ' + API_KEY)
    r.add_header('Content-Type', 'application/json')
    t2 = time.time()
    resp = urllib.request.urlopen(r, timeout=20)
    result = json.loads(resp.read().decode())
    print('OK %.1fs' % (time.time()-t2))
except Exception as e:
    print('FAIL: %s' % str(e)[:50])

print('Done')
