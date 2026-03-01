import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("❌ Установи BOT_TOKEN и WEBHOOK_URL в переменных окружения")

# 1️⃣ Проверка доступности URL
url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
try:
    r = requests.get(url)
    print(f"GET {url} → Status: {r.status_code}")
except Exception as e:
    print(f"Ошибка при запросе webhook: {e}")

# 2️⃣ Проверка webhook у Telegram
tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
try:
    r = requests.get(tg_url).json()
    if r.get("ok"):
        info = r.get("result", {})
        print("✅ Telegram webhook info:")
        print(f"URL: {info.get('url')}")
        print(f"Last error message: {info.get('last_error_message')}")
        print(f"Pending updates: {info.get('pending_update_count')}")
    else:
        print("❌ Не удалось получить webhook info у Telegram:", r)
except Exception as e:
    print(f"Ошибка запроса к Telegram API: {e}")