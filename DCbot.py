import requests

def get_dot_data():
    # 使用 CoinGecko API 取得現在價格與 24h 漲跌
    crypto_url = "https://api.coingecko.com/api/v3/simple/price?ids=polkadot&vs_currencies=usd&include_24hr_change=true"
    
    try:
        response = requests.get(crypto_url)
        data = response.json()
        
        # 取得現在價格與漲跌幅 (%)
        current_price = data['polkadot']['usd']
        change_24h_percent = data['polkadot']['usd_24h_change']
        
        # 核心計算：一天前價格 = 現在價格 / (1 + 漲跌幅百分比)
        # 例如漲了 5%, 則是 現在價格 / 1.05
        yesterday_price = current_price / (1 + (change_24h_percent / 100))
        
        return current_price, yesterday_price, change_24h_percent
    except Exception as e:
        print(f"抓取數據失敗: {e}")
        return None, None, None

def send_to_discord(webhook_url, current, yesterday, change):
    # 漲跌顏色判斷
    color = 3066993 if change >= 0 else 15158332 
    
    payload = {
        "embeds": [{
            "title": "💰 DOT行情",
            "color": color,
            "fields": [
                # 第一行：兩個價格並排
                {"name": "現在價格", "value": f"${current:.2f}", "inline": True},
                {"name": "一天前價格", "value": f"${yesterday:.2f}", "inline": True},
                # 第二行：漲跌幅 (inline 設為 False 會強制換行)
                {"name": "24h 漲跌變動", "value": f"{'📈' if change >= 0 else '📉'} {change:.2f}%", "inline": True}
            ]
        }]
    }
    
    requests.post(webhook_url, json=payload)

# --- 設定區 ---
MY_WEBHOOK_URL = "https://discord.com/api/webhooks/1331621312405176372/t-u1AXN1WtUYGCqP9XjaiB_aHsL1AyTxTdz9OKGRPDxM48WYRcd9B0S7Dz3aaMGx5VLy"

# 執行
cur, yes, chg = get_dot_data()
if cur is not None:
    send_to_discord(MY_WEBHOOK_URL, cur, yes, chg)

    print(f"成功發送！現在: ${cur:.2f}, 一天前: ${yes:.2f}")

