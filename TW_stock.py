import datetime
import json
import os
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import requests
import yfinance as yf


def get_taiex_snapshot():
    """抓取台指近兩日資料，回傳最新盤中走勢與昨收基準。"""
    ticker = yf.Ticker("^TWII")
    data = ticker.history(period="2d", interval="5m")
    if data.empty:
        raise ValueError("Yahoo Finance 無數據")

    closes = data["Close"].dropna()
    if closes.empty:
        raise ValueError("Yahoo Finance 無收盤數據")

    latest_ts = closes.index[-1]
    session_mask = closes.index.date == latest_ts.date()
    session = closes.loc[session_mask]
    previous = closes.loc[closes.index.date < latest_ts.date()]

    previous_close = None
    if not previous.empty:
        previous_close = float(previous.iloc[-1])

    if previous_close is None:
        fast_info = getattr(ticker, "fast_info", {}) or {}
        previous_close = fast_info.get("previous_close")

    if previous_close is None:
        previous_close = ticker.info.get("previousClose")

    if previous_close is None:
        previous_close = float(session.iloc[0])

    current_price = float(session.iloc[-1])
    change_amount = current_price - previous_close
    change_percent = (change_amount / previous_close) * 100 if previous_close else 0

    return {
        "session": session,
        "session_date": latest_ts.date(),
        "latest_ts": latest_ts,
        "previous_close": float(previous_close),
        "current_price": current_price,
        "change_amount": change_amount,
        "change_percent": change_percent,
    }


def build_taiex_chart(session, previous_close):
    """生成較完整的台指盤中走勢圖。"""
    closes = [float(value) for value in session.tolist()]
    if len(closes) < 2:
        raise ValueError("台指資料點不足，無法生成圖表")

    timestamps = list(session.index)
    latest_price = closes[-1]
    session_high = max(closes)
    session_low = min(closes)
    session_open = closes[0]
    change_amount = latest_price - previous_close
    change_percent = (change_amount / previous_close) * 100 if previous_close else 0
    line_color = "#d64045" if change_amount < 0 else "#138a5c"
    fill_color = "#f6d9dc" if change_amount < 0 else "#d7f0e4"

    fig = plt.figure(figsize=(12.6, 7.2), dpi=160, facecolor="#f3f6fb")
    ax = fig.add_axes([0.07, 0.14, 0.88, 0.68])
    ax.set_facecolor("#ffffff")

    ax.plot(timestamps, closes, color=line_color, linewidth=3.2, solid_capstyle="round", zorder=3)
    ax.fill_between(timestamps, closes, previous_close, color=fill_color, alpha=0.82, zorder=2)
    ax.axhline(previous_close, color="#f4a261", linewidth=1.5, linestyle=(0, (5, 4)), zorder=1)
    ax.scatter(timestamps[-1], closes[-1], s=42, color=line_color, zorder=5)

    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.grid(axis="y", color="#d7dee8", linewidth=0.9, alpha=0.95)
    ax.grid(axis="x", color="#edf1f6", linewidth=0.6, alpha=0.75)
    ax.tick_params(axis="x", labelsize=10, colors="#5c6773", pad=8)
    ax.tick_params(axis="y", labelsize=10, colors="#5c6773")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")

    step = max(1, len(timestamps) // 6)
    tick_positions = timestamps[::step]
    if tick_positions[-1] != timestamps[-1]:
        tick_positions.append(timestamps[-1])
    ax.set_xticks(tick_positions)
    ax.set_xticklabels([tick.strftime("%H:%M") for tick in tick_positions])

    pct_axis = ax.twinx()
    pct_axis.set_ylim(ax.get_ylim())
    pct_axis.spines["left"].set_visible(False)
    pct_axis.spines["right"].set_position(("axes", 1.08))
    pct_axis.spines["right"].set_visible(False)
    pct_axis.tick_params(axis="y", labelsize=9, colors="#8a96a3")
    pct_axis.yaxis.set_major_formatter(
        FuncFormatter(lambda value, _: f"{((value - previous_close) / previous_close) * 100:+.2f}%")
    )

    title = "TAIEX Session Trend"
    subtitle = (
        f"{latest_price:,.0f}  "
        f"{change_amount:+.2f} ({change_percent:+.2f}%)  "
        f"vs Prev Close {previous_close:,.0f}"
    )
    fig.text(0.07, 0.91, title, fontsize=22, fontweight="bold", color="#243447")
    fig.text(0.07, 0.872, subtitle, fontsize=11.5, color="#4f5d6b")

    ax.annotate(
        f"Now {latest_price:,.0f}",
        xy=(timestamps[-1], closes[-1]),
        xytext=(-12, 18),
        textcoords="offset points",
        ha="right",
        fontsize=10.2,
        color="#243447",
        bbox={"boxstyle": "round,pad=0.35", "fc": "#ffffff", "ec": "#d7dee8"},
    )
    ax.annotate(
        f"Prev Close {previous_close:,.0f}",
        xy=(timestamps[-1], previous_close),
        xytext=(-10, -22),
        textcoords="offset points",
        ha="right",
        fontsize=9,
        color="#8a5a14",
    )

    high_idx = closes.index(session_high)
    low_idx = closes.index(session_low)
    ax.annotate(
        f"H {session_high:,.0f}",
        xy=(timestamps[high_idx], session_high),
        xytext=(0, -18),
        textcoords="offset points",
        ha="center",
        fontsize=9,
        color="#243447",
    )
    ax.annotate(
        f"L {session_low:,.0f}",
        xy=(timestamps[low_idx], session_low),
        xytext=(0, 12),
        textcoords="offset points",
        ha="center",
        fontsize=9,
        color="#243447",
    )

    summary_boxes = [
        ("Open", f"{session_open:,.0f}"),
        ("High", f"{session_high:,.0f}"),
        ("Low", f"{session_low:,.0f}"),
        ("Prev Close", f"{previous_close:,.0f}"),
    ]
    start_x = 0.07
    for label, value in summary_boxes:
        fig.text(
            start_x,
            0.82,
            label,
            fontsize=8.8,
            color="#7a8694",
            bbox={"boxstyle": "round,pad=0.28", "fc": "#eef3f8", "ec": "#eef3f8"},
        )
        fig.text(start_x, 0.792, value, fontsize=10.5, color="#243447", fontweight="bold")
        start_x += 0.13

    status_text = "Live Session" if timestamps[-1].date() == datetime.datetime.now(timestamps[-1].tz).date() else "Previous Session"
    status_color = "#d64045" if status_text == "Live Session" else "#607086"
    fig.text(
        0.84,
        0.905,
        status_text,
        fontsize=10,
        color=status_color,
        bbox={"boxstyle": "round,pad=0.35", "fc": "#ffffff", "ec": "#d7dee8"},
    )

    fig.text(
        0.015,
        0.02,
        f"Source: Yahoo Finance ^TWII | Updated {timestamps[-1].strftime('%Y-%m-%d %H:%M')}",
        fontsize=8.5,
        color="#7a8694",
    )

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    temp_file.close()
    fig.savefig(temp_file.name, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return temp_file.name

def get_wantgoo_real_time(symbol):
    """
    獲取實時數據並計算漲跌
    """
    if symbol == "WTXP":
        snapshot = get_taiex_snapshot()
        return (
            snapshot["current_price"],
            snapshot["change_percent"],
            snapshot["change_amount"],
        )

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
    """從 CNN Fear & Greed Index 抓取美股市場情緒"""
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Referer": "https://edition.cnn.com/",
        "Accept": "application/json",
    }

    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()
    data = res.json()

    fear_and_greed = data.get("fear_and_greed")
    if not fear_and_greed:
        raise ValueError("CNN Fear & Greed 無數據")

    value = round(float(fear_and_greed["score"]))
    classification_en = fear_and_greed["rating"]

    classifications = {
        "extreme fear": "極度恐懼",
        "fear": "恐懼",
        "neutral": "中立",
        "greed": "貪婪",
        "extreme greed": "極度貪婪",
    }
    classification = classifications.get(classification_en.lower(), classification_en)
    return value, classification

def send_discord_all():
    webhook_url = "https://discord.com/api/webhooks/1451566651765162036/z7-pOpZ0DKtodgdV8n9pGEFX-NVIohsqlSt4EQAL2LebGsOY9-7eO_Fvgy2zawcTXjc1"
    my_id = "302727629226639360"
    chart_path = None

    try:
        taiex = get_taiex_snapshot()
        tx_p = taiex["current_price"]
        tx_c_percent = taiex["change_percent"]
        tx_c_amount = taiex["change_amount"]
        chart_path = build_taiex_chart(taiex["session"], taiex["previous_close"])

        # 2. 抓取正二 (代號 00675L)
        st_p, st_c_percent, st_c_amount = get_wantgoo_real_time("00675L")
        print(f"富邦正2: {st_p:.2f} ({st_c_amount:+.2f})")  # 調試
        # 3. 抓取情緒
        fg_v, fg_t = get_wantgoo_fg()
        print(f"抓取到的 CNN Fear & Greed: {fg_v} ({fg_t})")  # 調試印出

        payload = {
            "content": f"<@{my_id}> 📈 實時行情報告",
            "embeds": [{
                "title": "台指走勢圖",
                "color": 3066993 if tx_c_amount >= 0 else 15158332,
                "image": {"url": "attachment://taiex_intraday.png"},
                "fields": [
                    {
                        "name": "📉 台指 (預估)", 
                        "value": f"**{tx_p:,.0f}** ({tx_c_amount:+.2f} / {tx_c_percent:+.2f}%)", 
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
        with open(chart_path, "rb") as chart_file:
            response = requests.post(
                webhook_url,
                data={"payload_json": json.dumps(payload)},
                files={"file": ("taiex_intraday.png", chart_file, "image/png")},
                timeout=20,
            )
        response.raise_for_status()
        print("✅ 聯網發送成功！")

    except Exception as e:
        # 如果還是失敗，我們打印出完整的 Error 資訊來排查
        print(f"❌ 聯網抓取失敗: {e}")
    finally:
        if chart_path and os.path.exists(chart_path):
            os.remove(chart_path)

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
