import requests
from datetime import datetime, timedelta, timezone

WEBHOOK_URL = "https://discord.com/api/webhooks/1464214692426940621/yjUB9FOsNDr4s4Gb3YS0xmNQ9dL-sGT94uENJKn_zsG0yDutk7RNZej1evfja_gUNQp3"

USER_ID = "430361418194485250"

def is_workday():
    """
    使用 api.pin-yi.me 檢查是否為台灣上班日
    回傳: True (要上班/要發訊息), False (放假)
    """
    # ★ 關鍵：強制轉成台灣時間 (UTC+8)
    # 避免 GitHub 主機時間不同步導致抓錯日期
    tw_tz = timezone(timedelta(hours=8))
    today = datetime.now(tw_tz)
    
    year = today.year
    month = f"{today.month:02d}"
    day = f"{today.day:02d}"
    
    print(f"📅 檢查日期 (台灣時間): {year}-{month}-{day}")

    url = f"https://api.pin-yi.me/taiwan-calendar/{year}/{month}/{day}"

    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()

        if data:
            item = data[0]
            is_holiday = item['isHoliday'] # API 說是不是假日
            description = item.get('description', '無描述') # 節日名稱
            
            # 您的原始邏輯：如果不是假日 且 不是週末 = 上班
            # (注意：這個 API 通常會把補班日標示為 isHoliday: false，所以邏輯是通的)
            if is_holiday:
                print(f"⏸️ 今天是放假日 ({description})，跳過執行。")
                return False
            
            # 雙重確認週末 (雖然 API 的 isHoliday 通常已包含週末，但多檢查無害)
            # weekday: 5=週六, 6=週日
            if today.weekday() >= 5:
                print("⏸️ 今天是週末，跳過執行。")
                return False

            print("✅ 今天是上班日，準備發送！")
            return True
        else:
            print("⚠️ API 回傳空資料，為了保險起見，預設執行。")
            return True

    except Exception as e:
        print(f"⚠️ 檢查上班日失敗 (API 錯誤): {e}。為了不錯過午餐，預設執行。")
        return True

def send_notification():
    # 1. 檢查是否上班
    if not is_workday():
        return

    # 2. 檢查網址
    if not WEBHOOK_URL:
        print("❌ 錯誤：找不到 WEBHOOK_URL")
        return

    # 3. 發送訊息
    data = {
        "content": f"<@{USER_ID}> 那個...襄理  理專回覆了嗎??"
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=data)
        response.raise_for_status()
        print("✅ 訊息已發送成功！")
    except Exception as e:
        print(f"❌ 發送失敗: {e}")

if __name__ == "__main__":
    send_notification()

