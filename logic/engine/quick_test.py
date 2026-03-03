import urllib.request, json
API_KEY = 'sk-cp-cOK9G2O4ZpSb7TWE9OVx8-Pl1zq2yHzG_UgfzCRZ6JIMDa_O855-mB0U5oEgUe78CmnMDFOYEPcuQpDAAUikvApd509C0S5PGn5dxm4xCAwLWwKR1JYy5ss'
URL = 'https://api.minimaxi.com/v1/text/chatcompletion_v2'

data = json.dumps({'model': 'MiniMax-M2.5', 'messages': [{'role': 'user', 'content': 'hi'}]}).encode()
req = urllib.request.Request(URL, data=data, method='POST')
req.add_header('Authorization', 'Bearer ' + API_KEY)
req.add_header('Content-Type', 'application/json')

try:
    resp = urllib.request.urlopen(req, timeout=20)
    result = json.loads(resp.read().decode())
    print('OK:', result['choices'][0]['message']['content'][:50])
except Exception as e:
    print('FAIL:', str(e)[:50])
