import os
import requests

def get_dot_data():
    # 使用 CoinGecko API 取得現在價格與 24h 漲跌
    crypto_url = "https://api.coingecko.com/api/v3/simple/price?ids=polkadot&vs_currencies=usd&include_24hr_change=true"
    
    try:
        response = requests.get(crypto_url)
        data = response.json()
        
        current_price = data['polkadot']['usd']
        change_24h_percent = data['polkadot']['usd_24h_change']
        
        # 核心計算：一天前價格
        yesterday_price = current_price / (1 + (change_24h_percent / 100))
        
        return current_price, yesterday_price, change_24h_percent
    except Exception as e:
        print(f"抓取數據失敗: {e}")
        return None, None, None

def send_to_discord(webhook_url, current, yesterday, change):
    # 漲跌顏色判斷
    color = 3066993 if change >= 0 else 15158332 
    
    # 你的 Discord ID
    my_id = "385668017318526989"
    
    payload = {
        # 將標記放在 content，這樣手機才會跳通知
        "content": f"<@{my_id}> DOT 行情更新！", 
        "embeds": [{
            "title": "💰 DOT行情",
            "color": color,
            "fields": [
                {"name": "現在價格", "value": f"${current:.2f}", "inline": True},
                {"name": "一天前價格", "value": f"${yesterday:.2f}", "inline": True},
                {"name": "24h 漲跌變動", "value": f"{'📈' if change >= 0 else '📉'} {change:.2f}%", "inline": True}
            ]
        }]
    }
    
    requests.post(webhook_url, json=payload)

# --- 設定區 ---
if __name__ == "__main__":
    # 如果你在 GitHub Actions 跑，建議用 os.getenv
    # 如果在自己電腦跑，可以直接把網址貼在引號內
    MY_WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://discord.com/api/webhooks/1451566651765162036/z7-pOpZ0DKtodgdV8n9pGEFX-NVIohsqlSt4EQAL2LebGsOY9-7eO_Fvgy2zawcTXjc1"

    # 執行
    cur, yes, chg = get_dot_data()
    if cur is not None:
        send_to_discord(MY_WEBHOOK_URL, cur, yes, chg)
        print(f"成功發送！現在: ${cur:.2f}, 一天前: ${yes:.2f}")
