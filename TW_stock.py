import requests
import yfinance as yf
import datetime

def get_wantgoo_real_time(symbol):
    """
    獲取實時數據並計算漲跌
    """
    if symbol == "WTXP":
        # 台指期部分維持原樣 (使用 yfinance 近似值)
        ticker = yf.Ticker("^TWII")
        data = ticker.history(period="1d", interval="1m")
        if not data.empty:
            current_price = data['Close'].iloc[-1]
            prev_close = ticker.info.get('previousClose', data['Open'].iloc[0])
            change_percent = ((current_price - prev_close) / prev_close) * 100
            change_amount = current_price - prev_close
            return current_price, change_percent, change_amount
        else:
            raise ValueError("Yahoo Finance 無數據")

    elif symbol == "00675L":
        # 證交所 API
        url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_00675L.tw"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()

        if data['msgArray']:
            item = data['msgArray'][0]
            # z 是當前成交價, y 是昨收價 (比 pz 更穩定)
            price_str = item.get('z', '-')
            prev_str = item.get('y', '-') 

            if price_str == '-' or prev_str == '-':
                # 如果盤後 z 變成 '-'，嘗試抓取最近一次成交價 'tv' 或 'o'
                price_str = item.get('o', prev_str) 

            price = float(price_str)
            prev = float(prev_str)
            
            change_amount = price - prev
            change_percent = (change_amount / prev) * 100 if prev != 0 else 0
            
            return price, change_percent, change_amount
    
    raise ValueError(f"無法獲取 {symbol} 的數據")

def get_wantgoo_fg():
    """從 CNN 的 Fear and Greed Index API 抓取數據 (via alternative.me)"""
    url = "https://api.alternative.me/fng/?limit=1"
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    data = res.json()
    if data['data']:
        item = data['data'][0]
        value = int(item['value'])
        classification_en = item['value_classification']
        # 映射到中文
        classifications = {
            "Extreme Fear": "極度恐懼",
            "Fear": "恐懼",
            "Neutral": "中立",
            "Greed": "貪婪",
            "Extreme Greed": "極度貪婪"
        }
        classification = classifications.get(classification_en, classification_en)
        return value, classification
    else:
        raise ValueError("No data available")

def send_discord_all():
    webhook_url = "https://discord.com/api/webhooks/1331621312405176372/t-u1AXN1WtUYGCqP9XjaiB_aHsL1AyTxTdz9OKGRPDxM48WYRcd9B0S7Dz3aaMGx5VLy"
    my_id = "302727629226639360"

    try:
        # 1. 抓取台指期夜盤 (代號 WTXP)
        tx_p, tx_c_percent, tx_c_amount = get_wantgoo_real_time("WTXP") 
        # 2. 抓取正二 (代號 00675L)
        st_p, st_c_percent, st_c_amount = get_wantgoo_real_time("00675L")
        print(f"富邦正2: {st_p:.2f} ({st_c_amount:+.2f})")  # 調試
        # 3. 抓取情緒
        fg_v, fg_t = get_wantgoo_fg()
        print(f"抓取到的恐懼與貪婪: {fg_v} ({fg_t})")  # 調試印出

        payload = {
            "content": f"<@{my_id}> 📈 實時行情報告",
            "embeds": [{
                "color": 15158332,
                "fields": [
                    {
                        "name": "📉 台指 (預估)", 
                        "value": f"**{tx_p:,.0f}** ({tx_c_amount:+.2f})", 
                        "inline": True
                    },
                    {
                        "name": "📈 富邦正2 (00675L)", 
                        "value": f"**{st_p:.2f}** ({st_c_amount:+.2f} / {st_c_percent:+.2f}%)", 
                        "inline": True
                    },
                    {
                        "name": f"🌡️ 恐懼與貪婪 {fg_v} ({fg_t})", 
                        "value": "市場情緒同步中", 
                        "inline": False
                    }
                ]
            }]
        }
        requests.post(webhook_url, json=payload)
        print("✅ 聯網發送成功！")

    except Exception as e:
        # 如果還是失敗，我們打印出完整的 Error 資訊來排查
        print(f"❌ 聯網抓取失敗: {e}")

if __name__ == "__main__":
    # 檢查今天是不是上班日
    today = datetime.date.today()
    year = today.year
    month = f"{today.month:02d}"
    day = f"{today.day:02d}"
    url = f"https://api.pin-yi.me/taiwan-calendar/{year}/{month}/{day}"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data:
            item = data[0]
            is_holiday = item['isHoliday']
            week = item['week']
            if not is_holiday and week not in ['Saturday', 'Sunday']:
                print("今天是上班日，執行程式")
                send_discord_all()
            else:
                print("今天不是上班日，跳過執行")
        else:
            print("無法獲取行事曆數據，預設執行")
            send_discord_all()
    except Exception as e:
        print(f"檢查上班日失敗: {e}，預設執行")
        send_discord_all()