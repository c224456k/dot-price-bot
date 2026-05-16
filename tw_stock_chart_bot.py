import asyncio
import datetime
import json
import os
import re
import tempfile
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import discord
from discord.ext import tasks
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import requests
import yfinance as yf


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TAIFEX_NIGHT_TX_URL = "https://www.taifex.com.tw/cht/3/futDailyMarketExcel?commodity_id=TX&marketCode=1"
YAHOO_NIGHT_TX_URL = "https://tw.stock.yahoo.com/quote/WTX%26"
TAIWAN_TZ = ZoneInfo("Asia/Taipei")
NIGHT_SAMPLE_FILE = "/tmp/taifex_tx_night_samples.jsonl"
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


def is_night_session_query(user_input):
    text = user_input.strip().lower()
    return text in {"夜盤", "台指夜盤", "台指", "tx", "txf", "txf1", "wtxp", "wtxp&"}


def resolve_ticker(user_input):
    text = user_input.strip().upper()
    if not text:
        raise ValueError("請在提及機器人後面加上股票代碼，例如 `2330` 或 `AAPL`。")

    tw_match = re.search(r"\b\d{4,6}[A-Z]?\b", text)
    if tw_match:
        code = tw_match.group(0)
        return code, [f"{code}.TW", f"{code}.TWO"]

    us_match = re.search(r"\b[A-Z]{1,5}(?:[.-][A-Z]{1,2})?\b", text)
    if us_match:
        code = us_match.group(0)
        return code, [code.replace(".", "-"), code]

    raise ValueError(
        "目前支援台股與美股代碼，例如 `2330`、`0050`、`00631L`、`AAPL`、`TSLA`、`VOO`、`BRK.B`。"
    )


def fetch_stock_snapshot(user_input):
    code, candidates = resolve_ticker(user_input)

    for symbol in candidates:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="2d", interval="5m")
        closes = data["Close"].dropna() if not data.empty else None
        if closes is None or closes.empty:
            continue

        latest_ts = closes.index[-1]
        session = closes.loc[closes.index.date == latest_ts.date()]
        if len(session) < 2:
            continue

        previous = closes.loc[closes.index.date < latest_ts.date()]
        previous_close = None
        if not previous.empty:
            previous_close = float(previous.iloc[-1])

        fast_info = getattr(ticker, "fast_info", {}) or {}
        if previous_close is None:
            previous_close = fast_info.get("previous_close")
        if previous_close is None:
            info = ticker.info
            previous_close = info.get("previousClose")
        if previous_close is None:
            previous_close = float(session.iloc[0])

        current_price = float(session.iloc[-1])
        change_amount = current_price - previous_close
        change_percent = (change_amount / previous_close) * 100 if previous_close else 0
        info = ticker.info
        name = info.get("longName") or info.get("shortName") or code

        return {
            "code": code,
            "symbol": symbol,
            "name": name,
            "session": session,
            "latest_ts": latest_ts,
            "previous_close": float(previous_close),
            "current_price": current_price,
            "change_amount": change_amount,
            "change_percent": change_percent,
            "open_price": float(session.iloc[0]),
            "high_price": float(session.max()),
            "low_price": float(session.min()),
        }

    raise ValueError(f"找不到代碼 `{code}` 的盤中資料，請確認代碼是否正確或是否為交易時段。")


def fetch_taifex_night_snapshot():
    response = requests.get(TAIFEX_NIGHT_TX_URL, timeout=20, headers=HTTP_HEADERS)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    red_date = soup.find("p", style=lambda value: value and "color: #cc0000" in value.lower())
    report_date = red_date.get_text(" ", strip=True).replace("日期：", "").strip() if red_date else ""

    session_text = ""
    for text_node in soup.stripped_strings:
        if "15:00~次日05:00" in text_node and "盤後交易時段行情表" in text_node:
            session_text = text_node
            break

    rows = soup.find_all("tr")
    first_tx_cells = None
    for row in rows:
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
        if len(cells) >= 15 and cells[0] == "TX":
            first_tx_cells = cells
            break

    if not first_tx_cells:
        raise ValueError("期交所夜盤資料頁沒有找到 TX 近月資料")

    def parse_number(value):
        clean = value.strip().replace(",", "").replace("%", "")
        clean = clean.replace("▲", "").replace("▼", "")
        if clean == "-":
            return None
        return float(clean)

    return {
        "report_date": report_date,
        "session_text": session_text,
        "contract": first_tx_cells[1],
        "open_price": parse_number(first_tx_cells[2]),
        "high_price": parse_number(first_tx_cells[3]),
        "low_price": parse_number(first_tx_cells[4]),
        "last_price": parse_number(first_tx_cells[5]),
        "change_amount": parse_number(first_tx_cells[6]),
        "change_percent": parse_number(first_tx_cells[7]),
        "volume": parse_number(first_tx_cells[8]),
        "settlement_price": parse_number(first_tx_cells[9]),
        "open_interest": parse_number(first_tx_cells[10]),
        "best_bid": parse_number(first_tx_cells[11]),
        "best_ask": parse_number(first_tx_cells[12]),
    }


def fetch_yahoo_night_snapshot():
    response = requests.get(YAHOO_NIGHT_TX_URL, timeout=20, headers=HTTP_HEADERS)
    response.raise_for_status()
    text = BeautifulSoup(response.text, "html.parser").get_text("\n", strip=True)

    def parse_number(value):
        clean = value.strip().replace(",", "").replace("%", "")
        return float(clean)

    def extract(pattern, label, cast=float, required=True):
        match = re.search(pattern, text, re.MULTILINE)
        if not match:
            if required:
                raise ValueError(f"Yahoo 夜盤頁面缺少欄位: {label}")
            return None
        return cast(match.group(1))

    timestamp_match = re.search(r"資料時間[：:]\s*(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})", text)
    if not timestamp_match:
        timestamp_match = re.search(r"(?:開盤|收盤)\s*\|\s*(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})\s*更新", text)
    if not timestamp_match:
        raise ValueError("Yahoo 夜盤頁面缺少時間戳")

    timestamp_text = timestamp_match.group(1)
    timestamp = datetime.datetime.strptime(timestamp_text, "%Y/%m/%d %H:%M").replace(tzinfo=TAIWAN_TZ)

    return {
        "report_date": timestamp.strftime("%Y/%m/%d"),
        "session_text": "Yahoo WTX& current-day session",
        "contract": "WTX&",
        "open_price": extract(r"開盤\s+([0-9,]+(?:\.[0-9]+)?)", "open", parse_number),
        "high_price": extract(r"最高\s+([0-9,]+(?:\.[0-9]+)?)", "high", parse_number),
        "low_price": extract(r"最低\s+([0-9,]+(?:\.[0-9]+)?)", "low", parse_number),
        "last_price": extract(r"成交\s+([0-9,]+(?:\.[0-9]+)?)", "last", parse_number),
        "change_amount": extract(r"漲跌\s+([+-]?[0-9,]+(?:\.[0-9]+)?)", "change amount", parse_number),
        "change_percent": extract(r"漲跌幅\s+([+-]?[0-9,]+(?:\.[0-9]+)?)%", "change percent", parse_number),
        "volume": extract(r"總量\s+([0-9,]+)", "volume", parse_number),
        "settlement_price": None,
        "open_interest": extract(r"未平倉\s+([0-9,]+)", "open interest", parse_number, required=False),
        "best_bid": extract(r"買價\s+([0-9,]+(?:\.[0-9]+)?)", "best bid", parse_number, required=False),
        "best_ask": extract(r"賣價\s+([0-9,]+(?:\.[0-9]+)?)", "best ask", parse_number, required=False),
        "source_url": YAHOO_NIGHT_TX_URL,
        "updated_at": timestamp,
        "previous_close": extract(r"昨收\s+([0-9,]+(?:\.[0-9]+)?)", "previous close", parse_number),
        "average_price": None,
    }


def fetch_night_snapshot():
    try:
        return fetch_yahoo_night_snapshot()
    except Exception as yahoo_exc:
        print(f"Yahoo 夜盤抓取失敗，改用期交所: {yahoo_exc}")
        snapshot = fetch_taifex_night_snapshot()
        snapshot["source_url"] = TAIFEX_NIGHT_TX_URL
        snapshot["updated_at"] = datetime.datetime.now(TAIWAN_TZ)
        return snapshot


def record_night_sample(snapshot):
    now = datetime.datetime.now(TAIWAN_TZ)
    sample = {
        "ts": now.isoformat(),
        "report_date": snapshot["report_date"],
        "contract": snapshot["contract"],
        "last_price": snapshot["last_price"],
        "volume": snapshot["volume"],
    }
    with open(NIGHT_SAMPLE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(sample, ensure_ascii=True) + "\n")


def load_recent_night_samples():
    if not os.path.exists(NIGHT_SAMPLE_FILE):
        return []

    cutoff = datetime.datetime.now(TAIWAN_TZ) - datetime.timedelta(hours=16)
    samples = []
    with open(NIGHT_SAMPLE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                item["dt"] = datetime.datetime.fromisoformat(item["ts"])
            except Exception:
                continue
            if item["dt"] >= cutoff and item.get("last_price") is not None:
                samples.append(item)

    samples.sort(key=lambda item: item["dt"])
    return samples


def build_night_candles(samples, minutes=5):
    buckets = {}
    for sample in samples:
        dt = sample["dt"]
        rounded_minute = (dt.minute // minutes) * minutes
        bucket_key = dt.replace(minute=rounded_minute, second=0, microsecond=0)
        buckets.setdefault(bucket_key, []).append(sample)

    candles = []
    for bucket_time in sorted(buckets):
        bucket_samples = buckets[bucket_time]
        prices = [float(item["last_price"]) for item in bucket_samples]
        volumes = [item.get("volume") for item in bucket_samples if item.get("volume") is not None]
        volume = None
        if len(volumes) >= 2:
            volume = max(0, int(volumes[-1] - volumes[0]))
        candles.append(
            {
                "time": bucket_time,
                "open": prices[0],
                "high": max(prices),
                "low": min(prices),
                "close": prices[-1],
                "volume": volume,
            }
        )
    return candles


def build_stock_chart(snapshot):
    session = snapshot["session"]
    closes = [float(value) for value in session.tolist()]
    timestamps = list(session.index)
    previous_close = snapshot["previous_close"]
    latest_price = snapshot["current_price"]
    change_amount = snapshot["change_amount"]
    change_percent = snapshot["change_percent"]
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
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.2f}"))
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

    fig.text(0.07, 0.91, f"{snapshot['code']}  {snapshot['name']}", fontsize=22, fontweight="bold", color="#243447")
    fig.text(
        0.07,
        0.872,
        f"{latest_price:,.2f}  {change_amount:+.2f} ({change_percent:+.2f}%)  vs Prev Close {previous_close:,.2f}",
        fontsize=11.5,
        color="#4f5d6b",
    )

    ax.annotate(
        f"Now {latest_price:,.2f}",
        xy=(timestamps[-1], closes[-1]),
        xytext=(-12, 18),
        textcoords="offset points",
        ha="right",
        fontsize=10.2,
        color="#243447",
        bbox={"boxstyle": "round,pad=0.35", "fc": "#ffffff", "ec": "#d7dee8"},
    )
    ax.annotate(
        f"Prev Close {previous_close:,.2f}",
        xy=(timestamps[-1], previous_close),
        xytext=(-10, -22),
        textcoords="offset points",
        ha="right",
        fontsize=9,
        color="#8a5a14",
    )

    high_price = snapshot["high_price"]
    low_price = snapshot["low_price"]
    ax.annotate(
        f"H {high_price:,.2f}",
        xy=(timestamps[closes.index(high_price)], high_price),
        xytext=(0, -18),
        textcoords="offset points",
        ha="center",
        fontsize=9,
        color="#243447",
    )
    ax.annotate(
        f"L {low_price:,.2f}",
        xy=(timestamps[closes.index(low_price)], low_price),
        xytext=(0, 12),
        textcoords="offset points",
        ha="center",
        fontsize=9,
        color="#243447",
    )

    summary_boxes = [
        ("Open", f"{snapshot['open_price']:,.2f}"),
        ("High", f"{high_price:,.2f}"),
        ("Low", f"{low_price:,.2f}"),
        ("Prev Close", f"{previous_close:,.2f}"),
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

    today = datetime.datetime.now(timestamps[-1].tz).date()
    status_text = "Live Session" if timestamps[-1].date() == today else "Previous Session"
    status_color = "#d64045" if status_text == "Live Session" else "#607086"
    fig.text(
        0.82,
        0.905,
        status_text,
        fontsize=10,
        color=status_color,
        bbox={"boxstyle": "round,pad=0.35", "fc": "#ffffff", "ec": "#d7dee8"},
    )

    fig.text(
        0.015,
        0.02,
        f"Source: Yahoo Finance {snapshot['symbol']} | Updated {timestamps[-1].strftime('%Y-%m-%d %H:%M')}",
        fontsize=8.5,
        color="#7a8694",
    )

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    temp_file.close()
    fig.savefig(temp_file.name, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return temp_file.name


def build_taifex_night_chart(snapshot):
    open_price = snapshot["open_price"]
    high_price = snapshot["high_price"]
    low_price = snapshot["low_price"]
    last_price = snapshot["last_price"]
    change_amount = snapshot["change_amount"] or 0.0
    change_percent = snapshot["change_percent"] or 0.0
    color = "#d64045" if change_amount < 0 else "#138a5c"
    fill_color = "#f6d9dc" if change_amount < 0 else "#d7f0e4"

    fig = plt.figure(figsize=(10.8, 6.6), dpi=160, facecolor="#0f1720")
    ax = fig.add_axes([0.08, 0.16, 0.48, 0.68])
    ax.set_facecolor("#15202b")

    padding = max(60, (high_price - low_price) * 0.2)
    ax.set_ylim(low_price - padding, high_price + padding)
    ax.set_xlim(-0.8, 0.8)
    ax.axhline(last_price, color=color, alpha=0.18, linewidth=12, zorder=1)
    ax.vlines(0, low_price, high_price, color="#cfd8e3", linewidth=5, zorder=2)
    candle_bottom = min(open_price, last_price)
    candle_height = max(abs(last_price - open_price), 1)
    ax.bar(0, candle_height, bottom=candle_bottom, width=0.42, color=fill_color, edgecolor=color, linewidth=2.5, zorder=3)
    ax.scatter([0], [last_price], color=color, s=70, zorder=4)

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.tick_params(axis="y", labelsize=10, colors="#d4dee8")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    ax.grid(axis="y", color="#324150", linewidth=0.8, alpha=0.65)

    ax.annotate(f"H {high_price:,.0f}", xy=(0, high_price), xytext=(10, -4), textcoords="offset points", color="#d4dee8", fontsize=9)
    ax.annotate(f"L {low_price:,.0f}", xy=(0, low_price), xytext=(10, -4), textcoords="offset points", color="#d4dee8", fontsize=9)
    ax.annotate(f"Last {last_price:,.0f}", xy=(0, last_price), xytext=(10, 6), textcoords="offset points", color="#ffffff", fontsize=10, fontweight="bold")

    fig.text(0.08, 0.91, "TX Night Session", fontsize=22, fontweight="bold", color="#f8fafc")
    fig.text(
        0.08,
        0.868,
        f"{snapshot['contract']}  {last_price:,.0f}  {change_amount:+.0f} ({change_percent:+.2f}%)",
        fontsize=12,
        color="#d7e0ea",
    )
    session_label = "15:00-05:00 Night Session"
    fig.text(0.08, 0.835, session_label, fontsize=9.5, color="#94a3b8")

    info_lines = [
        ("Open", f"{open_price:,.0f}"),
        ("High", f"{high_price:,.0f}"),
        ("Low", f"{low_price:,.0f}"),
        ("Last", f"{last_price:,.0f}"),
        ("Prev Close", f"{snapshot['previous_close']:,.0f}" if snapshot.get("previous_close") is not None else "-"),
        ("Avg", f"{snapshot['average_price']:,.2f}" if snapshot.get("average_price") is not None else "-"),
        ("Volume", f"{int(snapshot['volume']):,}" if snapshot["volume"] is not None else "-"),
        ("Best Bid", f"{snapshot['best_bid']:,.0f}" if snapshot["best_bid"] is not None else "-"),
        ("Best Ask", f"{snapshot['best_ask']:,.0f}" if snapshot["best_ask"] is not None else "-"),
    ]
    y = 0.74
    for label, value in info_lines:
        fig.text(0.64, y, label, fontsize=10, color="#8ea1b5")
        fig.text(0.64, y - 0.045, value, fontsize=16, fontweight="bold", color="#f8fafc")
        y -= 0.105

    updated_at = snapshot.get("updated_at")
    updated_text = updated_at.strftime("%Y-%m-%d %H:%M") if updated_at else snapshot["report_date"]
    source_url = snapshot.get("source_url", "").lower()
    if "yahoo" in source_url:
        source_label = "Yahoo WTX&"
    elif "wantgoo" in source_url:
        source_label = "WantGoo WTXP&"
    else:
        source_label = "TAIFEX TX night market"
    fig.text(0.08, 0.04, f"Source: {source_label} | Updated {updated_text}", fontsize=8.8, color="#94a3b8")

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    temp_file.close()
    fig.savefig(temp_file.name, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return temp_file.name


def build_taifex_night_candles_chart(snapshot, candles):
    change_amount = snapshot["change_amount"] or 0.0
    change_percent = snapshot["change_percent"] or 0.0
    fig = plt.figure(figsize=(12.8, 7.0), dpi=160, facecolor="#0f1720")
    ax = fig.add_axes([0.07, 0.18, 0.88, 0.64])
    ax.set_facecolor("#15202b")

    highs = [candle["high"] for candle in candles]
    lows = [candle["low"] for candle in candles]
    min_price = min(lows)
    max_price = max(highs)
    padding = max(35, (max_price - min_price) * 0.2)
    ax.set_ylim(min_price - padding, max_price + padding)
    ax.grid(axis="y", color="#324150", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#22303d", linewidth=0.6, alpha=0.45)
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.tick_params(axis="x", labelsize=9, colors="#d4dee8", pad=8)
    ax.tick_params(axis="y", labelsize=10, colors="#d4dee8")
    ax.yaxis.tick_right()
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))

    x_values = list(range(len(candles)))
    for idx, candle in enumerate(candles):
        up = candle["close"] >= candle["open"]
        edge_color = "#22c55e" if up else "#ef4444"
        fill_color = "#d7f0e4" if up else "#f6d9dc"
        ax.vlines(idx, candle["low"], candle["high"], color=edge_color, linewidth=1.6, zorder=2)
        body_bottom = min(candle["open"], candle["close"])
        body_height = max(abs(candle["close"] - candle["open"]), 1)
        ax.bar(idx, body_height, bottom=body_bottom, width=0.62, color=fill_color, edgecolor=edge_color, linewidth=1.5, zorder=3)

    step = max(1, len(candles) // 8)
    tick_positions = x_values[::step]
    if tick_positions[-1] != x_values[-1]:
        tick_positions.append(x_values[-1])
    ax.set_xticks(tick_positions)
    ax.set_xticklabels([candles[idx]["time"].strftime("%H:%M") for idx in tick_positions])

    fig.text(0.07, 0.91, "TX Night Session", fontsize=22, fontweight="bold", color="#f8fafc")
    fig.text(
        0.07,
        0.872,
        f"{snapshot['contract']}  {snapshot['last_price']:,.0f}  {change_amount:+.0f} ({change_percent:+.2f}%)",
        fontsize=12,
        color="#d7e0ea",
    )
    fig.text(0.07, 0.838, f"5-min candles from sampled TAIFEX quotes | bars {len(candles)}", fontsize=9.5, color="#94a3b8")

    info_lines = [
        ("Open", f"{snapshot['open_price']:,.0f}"),
        ("High", f"{snapshot['high_price']:,.0f}"),
        ("Low", f"{snapshot['low_price']:,.0f}"),
        ("Last", f"{snapshot['last_price']:,.0f}"),
        ("Prev Close", f"{snapshot['previous_close']:,.0f}" if snapshot.get("previous_close") is not None else "-"),
        ("Volume", f"{int(snapshot['volume']):,}" if snapshot["volume"] is not None else "-"),
    ]
    y = 0.74
    for label, value in info_lines:
        fig.text(0.80, y, label, fontsize=10, color="#8ea1b5")
        fig.text(0.80, y - 0.042, value, fontsize=15, fontweight="bold", color="#f8fafc")
        y -= 0.10

    updated_at = snapshot.get("updated_at")
    updated_text = updated_at.strftime("%Y-%m-%d %H:%M") if updated_at else snapshot["report_date"]
    source_url = snapshot.get("source_url", "").lower()
    if "yahoo" in source_url:
        source_label = "Yahoo WTX&"
    elif "wantgoo" in source_url:
        source_label = "WantGoo WTXP&"
    else:
        source_label = "TAIFEX TX night market"
    fig.text(0.07, 0.04, f"Source: {source_label} | Updated {updated_text}", fontsize=8.8, color="#94a3b8")

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    temp_file.close()
    fig.savefig(temp_file.name, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return temp_file.name


async def generate_chart_reply(user_input):
    if is_night_session_query(user_input):
        data = await asyncio.to_thread(fetch_night_snapshot)
        await asyncio.to_thread(record_night_sample, data)
        samples = await asyncio.to_thread(load_recent_night_samples)
        candles = await asyncio.to_thread(build_night_candles, samples)
        if len(candles) >= 2:
            image_path = await asyncio.to_thread(build_taifex_night_candles_chart, data, candles)
        else:
            image_path = await asyncio.to_thread(build_taifex_night_chart, data)
        return "night", data, image_path

    data = await asyncio.to_thread(fetch_stock_snapshot, user_input)
    image_path = await asyncio.to_thread(build_stock_chart, data)
    return "stock", data, image_path


@client.event
async def on_ready():
    display_name = "股市小幫手"
    for guild in client.guilds:
        member = guild.me
        if member and member.nick != display_name:
            try:
                await member.edit(nick=display_name)
            except Exception as exc:
                print(f"更新伺服器暱稱失敗: guild={guild.name} error={exc}")
    print(f"{display_name} 已上線，等待股票代碼查詢")
    if not night_sampler.is_running():
        night_sampler.start()


@tasks.loop(minutes=1)
async def night_sampler():
    now = datetime.datetime.now(TAIWAN_TZ)
    minute_of_day = now.hour * 60 + now.minute
    in_night_window = minute_of_day >= 15 * 60 or minute_of_day <= 5 * 60
    if not in_night_window:
        return
    try:
        snapshot = await asyncio.to_thread(fetch_night_snapshot)
        await asyncio.to_thread(record_night_sample, snapshot)
        print(f"夜盤樣本已記錄: {snapshot['contract']} {snapshot['last_price']} @ {now.strftime('%H:%M:%S')}")
    except Exception as exc:
        print(f"夜盤樣本記錄失敗: {exc}")


@client.event
async def on_message(message):
    print(
        "MESSAGE",
        {
            "author": str(message.author),
            "channel": str(message.channel),
            "guild": str(message.guild),
            "content": message.content,
            "mentions_bot": bool(client.user and client.user in message.mentions),
        },
    )

    if message.author == client.user:
        return

    if client.user not in message.mentions:
        return

    user_input = message.content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()
    print(f"收到查詢: raw={message.content!r} parsed={user_input!r}")

    async with message.channel.typing():
        image_path = None
        try:
            reply_type, snapshot, image_path = await generate_chart_reply(user_input)
            if reply_type == "night":
                file_name = "tx_night_session.png"
                source_url = snapshot.get("source_url", "").lower()
                if "yahoo" in source_url:
                    source_label = "Yahoo WTX&"
                elif "wantgoo" in source_url:
                    source_label = "WantGoo WTXP&"
                else:
                    source_label = "TAIFEX 期交所夜盤行情"
                embed = discord.Embed(
                    title=f"TX 夜盤 {snapshot['contract']}",
                    description=(
                        f"最新 `{snapshot['last_price']:,.0f}`  "
                        f"漲跌 `{snapshot['change_amount']:+.0f}`  "
                        f"漲跌幅 `{snapshot['change_percent']:+.2f}%`"
                    ),
                    color=0x138A5C if snapshot["change_amount"] >= 0 else 0xD64045,
                )
                embed.set_footer(text=f"資料來源 {source_label}")
            else:
                file_name = f"{snapshot['code']}_intraday.png"
                embed = discord.Embed(
                    title=f"{snapshot['code']} {snapshot['name']}",
                    description=(
                        f"現價 `{snapshot['current_price']:,.2f}`  "
                        f"漲跌 `{snapshot['change_amount']:+.2f}`  "
                        f"漲跌幅 `{snapshot['change_percent']:+.2f}%`"
                    ),
                    color=0x138A5C if snapshot["change_amount"] >= 0 else 0xD64045,
                )
                embed.set_footer(text=f"資料來源 Yahoo Finance | 代碼 {snapshot['symbol']}")
            embed.set_image(url=f"attachment://{file_name}")

            await message.reply(
                embed=embed,
                file=discord.File(image_path, filename=file_name),
                mention_author=False,
            )
        except Exception as exc:
            await message.reply(f"查詢失敗：{exc}", mention_author=False)
        finally:
            if image_path and os.path.exists(image_path):
                os.remove(image_path)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("缺少 DISCORD_TOKEN 環境變數")
    client.run(DISCORD_TOKEN)
