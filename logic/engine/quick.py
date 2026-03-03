print("start")
import urllib.request, json
API_KEY = 'sk-cp-cOK9G2O4ZpSb7TWE9OVx8-Pl1zq2yHzG_UgfzCRZ6JIMDa_O855-mB0U5oEgUe78CmnMDFOYEPcuQpDAAUikvApd509C0S5PGn5dxm4xCAwLWwKR1JYy5ss'
URL = 'https://api.minimaxi.com/v1/text/chatcompletion_v2'
data = json.dumps({'model': 'MiniMax-M2.5', 'messages': [{'role': 'user', 'content': 'hi'}]}).encode()
r = urllib.request.Request(URL, data=data, method='POST')
r.add_header('Authorization', f'Bearer {API_KEY}')
r.add_header('Content-Type', 'application/json')
resp = urllib.request.urlopen(r, timeout=10)
print("got response")
print(resp.read().decode()[:100])
print("done")
