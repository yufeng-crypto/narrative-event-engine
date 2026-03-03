# -*- coding: utf-8 -*-
import json
import urllib.request

API_KEY = "sk-cp-cOK9G2O4ZpSb7TWE9OVx8-Pl1zq2yHzG_UgfzCRZ6JIMDa_O855-mB0U5oEgUe78CmnMDFOYEPcuQpDAAUikvApd509C0S5PGn5dxm4xCAwLWwKR1JYy5ss"
URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"

# 直接问 MiniMax
messages = [{"role": "user", "content": "MiniMax API 调用时，如果传入多个 role=system 的 messages，会返回错误 \"invalid chat setting\"。请问如何解决？"}]

payload = {"model": "MiniMax-M2.5", "messages": messages}
data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(URL, data=data, method="POST")
req.add_header("Authorization", f"Bearer {API_KEY}")
req.add_header("Content-Type", "application/json")

resp = urllib.request.urlopen(req, timeout=30)
result = json.loads(resp.read().decode("utf-8"))
print(result["choices"][0]["message"]["content"])
