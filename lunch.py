import requests


WEBHOOK_URL = "https://discord.com/api/webhooks/1464214692426940621/yjUB9FOsNDr4s4Gb3YS0xmNQ9dL-sGT94uENJKn_zsG0yDutk7RNZej1evfja_gUNQp3"

USER_ID = "430361418194485250"

def send_notification():
    # 雙重檢查
    if not WEBHOOK_URL:
        print("錯誤：仍然找不到 WEBHOOK_URL")
        return

    data = {
        "content": f"<@{USER_ID}> 那個...襄理 請問午餐吃甚麼?"
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=data)
        response.raise_for_status()
        print("✅ 訊息已發送成功！(目前使用: 本地/備用網址)")
    except Exception as e:
        print(f"❌ 發送失敗: {e}")

if __name__ == "__main__":
    send_notification()