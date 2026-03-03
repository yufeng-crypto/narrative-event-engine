import urllib.request, json
API_KEY = 'sk-cp-cOK9G2O4ZpSb7TWE9OVx8-Pl1zq2yHzG_UgfzCRZ6JIMDa_O855-mB0U5oEgUe78CmnMDFOYEPcuQpDAAUikvApd509C0S5PGn5dxm4xCAwLWwKR1JYy5ss'
URL = 'https://api.minimaxi.com/v1/text/chatcompletion_v2'

user = "I am at the restaurant, I called Shen Yuxi"
axes = {"Intimacy": 10, "Rel": 10, "Action": 8}

# Director test
prompt = f"You are Director. Axes={axes}. User said: {user}. Output JSON beat and axis_changes."
data = json.dumps({'model': 'MiniMax-M2.5', 'messages': [{'role': 'user', 'content': prompt}]}).encode()
req = urllib.request.Request(URL, data=data, method='POST')
req.add_header('Authorization', 'Bearer ' + API_KEY)
req.add_header('Content-Type', 'application/json')

print("Calling Director...")
resp = urllib.request.urlopen(req, timeout=20)
result = json.loads(resp.read().decode())
d_out = result['choices'][0]['message']['content']
print("Director:", d_out[:100])

# Performer test
prompt2 = f"You are Performer. NPC is Shen Yuxi (tsundere). User said: {user}. Output dialogue."
data2 = json.dumps({'model': 'MiniMax-M2.5', 'messages': [{'role': 'user', 'content': prompt2}]}).encode()
req2 = urllib.request.Request(URL, data=data2, method='POST')
req2.add_header('Authorization', 'Bearer ' + API_KEY)
req2.add_header('Content-Type', 'application/json')

print("Calling Performer...")
resp2 = urllib.request.urlopen(req2, timeout=20)
result2 = json.loads(resp2.read().decode())
p_out = result2['choices'][0]['message']['content']
print("Performer:", p_out[:100])

print("Done")
