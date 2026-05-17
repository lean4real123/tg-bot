"""
Прямая проверка через Telegram API без aiogram
Запусти и посмотри что приходит
"""
import urllib.request
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import BOT_TOKEN

BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

def api(method, **params):
    url = f"{BASE}/{method}"
    data = json.dumps(params).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

# Устанавливаем allowed_updates явно
print("Устанавливаем allowed_updates...")
result = api("getUpdates",
    allowed_updates=[
        "message",
        "business_connection",
        "business_message",
        "edited_business_message",
        "deleted_business_messages",
    ],
    timeout=0,
    offset=-1
)
print("getUpdates result:", json.dumps(result, ensure_ascii=False, indent=2)[:300])

# Проверяем webhook
wh = api("getWebhookInfo")
print("\nWebhook info:", json.dumps(wh, ensure_ascii=False, indent=2))

# Проверяем getMe
me = api("getMe")
print("\nBot info:", json.dumps(me, ensure_ascii=False, indent=2))
print("\ncan_connect_to_business:", me["result"].get("can_connect_to_business"))
