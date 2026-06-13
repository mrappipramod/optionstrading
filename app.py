"""
NiftyEdge Pro — Dhan-powered Options Trading Dashboard
Flask backend: REST proxy for Dhan APIs + WebSocket relay
"""

import os
import json
import struct
import asyncio
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import requests
import websocket
from ta_engine import analyse

# ─── CONFIG ──────────────────────────────────────────────────────────────────
DHAN_CLIENT_ID  = os.environ.get("DHAN_CLIENT_ID",  "YOUR_CLIENT_ID")
DHAN_ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN", "YOUR_ACCESS_TOKEN")

DHAN_BASE_URL   = "https://api.dhan.co/v2"
DHAN_WS_URL     = (
    f"wss://api-feed.dhan.co"
    f"?version=2&token={DHAN_ACCESS_TOKEN}"
    f"&clientId={DHAN_CLIENT_ID}&authType=2"
)

HEADERS = {
    "Content-Type": "application/json",
    "access-token": DHAN_ACCESS_TOKEN,
    "client-id": DHAN_CLIENT_ID,
}

# NSE Security IDs for key indices / stocks
SECURITY_IDS = {
    "NIFTY":      {"id": "13",    "segment": "IDX_I"},
    "BANKNIFTY":  {"id": "25",    "segment": "IDX_I"},
    "FINNIFTY":   {"id": "27",    "segment": "IDX_I"},
    "SENSEX":     {"id": "1",     "segment": "IDX_I"},
    "RELIANCE":   {"id": "2885",  "segment": "NSE_EQ"},
    "HDFCBANK":   {"id": "1333",  "segment": "NSE_EQ"},
    "INFY":       {"id": "10604", "segment": "NSE_EQ"},
    "TCS":        {"id": "11536", "segment": "NSE_EQ"},
    "WIPRO":      {"id": "3787",  "segment": "NSE_EQ"},
    "ICICIBANK":  {"id": "4963",  "segment": "NSE_EQ"},
}

# ─── APP SETUP ───────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "niftyedge-secret-2024"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Global live tick cache
live_ticks = {}

# ─── DHAN REST HELPERS ───────────────────────────────────────────────────────
def dhan_get(path, params=None):
    try:
        r = requests.get(f"{DHAN_BASE_URL}{path}", headers=HEADERS, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def dhan_post(path, body):
    try:
        r = requests.post(f"{DHAN_BASE_URL}{path}", headers=HEADERS, json=body, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ─── FLASK ROUTES ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/quote")
def quote():
    """Snapshot quote for given securities (ticker / quote / full mode)."""
    symbols = request.args.get("symbols", "NIFTY,BANKNIFTY").split(",")
    body = {
        "NSE_EQ": [],
        "IDX_I": [],
        "NSE_FNO": [],
    }
    for sym in symbols:
        sym = sym.strip().upper()
        if sym in SECURITY_IDS:
            seg = SECURITY_IDS[sym]["segment"]
            body.setdefault(seg, []).append(SECURITY_IDS[sym]["id"])

    # Remove empty segments
    body = {k: v for k, v in body.items() if v}

    # Quote mode — gives LTP, OHLC, volume, OI etc.
    data = dhan_post("/marketfeed/quote", body)
    return jsonify(data)


@app.route("/api/candles")
def candles():
    """
    Intraday candle data for charting.
    Query params: symbol, interval (1/5/15/25/60), fromDate, toDate
    """
    symbol   = request.args.get("symbol", "NIFTY").upper()
    interval = request.args.get("interval", "15")
    from_date = request.args.get("fromDate", (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"))
    to_date   = request.args.get("toDate",   datetime.now().strftime("%Y-%m-%d"))

    info = SECURITY_IDS.get(symbol)
    if not info:
        return jsonify({"error": f"Unknown symbol: {symbol}"}), 400

    body = {
        "securityId":      info["id"],
        "exchangeSegment": info["segment"],
        "instrument":      "INDEX" if info["segment"] == "IDX_I" else "EQUITY",
        "interval":        interval,
        "oi":              False,
        "fromDate":        from_date,
        "toDate":          to_date,
    }
    data = dhan_post("/charts/intraday", body)
    return jsonify(data)


@app.route("/api/candles/daily")
def candles_daily():
    """Daily OHLCV candles."""
    symbol    = request.args.get("symbol", "NIFTY").upper()
    from_date = request.args.get("fromDate", (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d"))
    to_date   = request.args.get("toDate",   datetime.now().strftime("%Y-%m-%d"))

    info = SECURITY_IDS.get(symbol)
    if not info:
        return jsonify({"error": f"Unknown symbol: {symbol}"}), 400

    body = {
        "securityId":      info["id"],
        "exchangeSegment": info["segment"],
        "instrument":      "INDEX" if info["segment"] == "IDX_I" else "EQUITY",
        "expiryCode":      0,
        "oi":              False,
        "fromDate":        from_date,
        "toDate":          to_date,
    }
    data = dhan_post("/charts/historical", body)
    return jsonify(data)


@app.route("/api/optionchain")
def option_chain():
    """
    Full option chain with OI, greeks, IV for any underlying.
    Query params: symbol, expiry (YYYY-MM-DD)
    """
    symbol = request.args.get("symbol", "NIFTY").upper()
    expiry = request.args.get("expiry", "")   # e.g. "2024-12-26"

    info = SECURITY_IDS.get(symbol)
    if not info:
        return jsonify({"error": f"Unknown symbol: {symbol}"}), 400

    body = {
        "UnderlyingScrip": int(info["id"]),
        "UnderlyingSeg":   info["segment"],
        "Expirydate":      expiry,
    }
    data = dhan_post("/optionchain", body)
    return jsonify(data)


@app.route("/api/optionchain/expiries")
def option_expiries():
    """Get list of available expiry dates."""
    symbol = request.args.get("symbol", "NIFTY").upper()
    info = SECURITY_IDS.get(symbol)
    if not info:
        return jsonify({"error": f"Unknown symbol: {symbol}"}), 400

    body = {
        "UnderlyingScrip": int(info["id"]),
        "UnderlyingSeg":   info["segment"],
    }
    data = dhan_post("/optionchain/expirylist", body)
    return jsonify(data)


@app.route("/api/analyse")
def analyse_route():
    """
    Fetch intraday candles from Dhan and run TA + signal engine.
    Query params: symbol, interval
    """
    symbol   = request.args.get("symbol", "NIFTY").upper()
    interval = request.args.get("interval", "15")
    from_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    to_date   = datetime.now().strftime("%Y-%m-%d")

    info = SECURITY_IDS.get(symbol)
    if not info:
        return jsonify({"error": f"Unknown symbol: {symbol}"}), 400

    body = {
        "securityId":      info["id"],
        "exchangeSegment": info["segment"],
        "instrument":      "INDEX" if info["segment"] == "IDX_I" else "EQUITY",
        "interval":        interval,
        "oi":              False,
        "fromDate":        from_date,
        "toDate":          to_date,
    }
    raw = dhan_post("/charts/intraday", body)
    if "error" in raw:
        return jsonify(raw), 500

    result = analyse(raw)
    result["symbol"] = symbol
    result["interval"] = interval
    return jsonify(result)


def funds():
    """Available margin / funds."""
    return jsonify(dhan_get("/funds/balance"))


@app.route("/api/portfolio")
def portfolio():
    """Current holdings."""
    return jsonify(dhan_get("/portfolio/holdings"))


@app.route("/api/positions")
def positions():
    """Open positions."""
    return jsonify(dhan_get("/portfolio/positions"))


@app.route("/api/orders")
def orders():
    """Order book."""
    return jsonify(dhan_get("/orders"))


@app.route("/api/place_order", methods=["POST"])
def place_order():
    """
    Place an options order.
    Body: { securityId, quantity, price, transactionType (BUY/SELL),
            orderType (LIMIT/MARKET), productType (INTRADAY/CNC) }
    """
    data = request.json
    body = {
        "dhanClientId":    DHAN_CLIENT_ID,
        "transactionType": data.get("transactionType", "BUY"),
        "exchangeSegment": "NSE_FNO",
        "productType":     data.get("productType", "INTRADAY"),
        "orderType":       data.get("orderType", "LIMIT"),
        "validity":        "DAY",
        "securityId":      data.get("securityId"),
        "quantity":        data.get("quantity", 50),
        "price":           data.get("price", 0),
        "triggerPrice":    data.get("triggerPrice", 0),
        "disclosedQuantity": 0,
        "afterMarketOrder": False,
    }
    result = dhan_post("/orders", body)
    return jsonify(result)


# ─── WEBSOCKET RELAY (Dhan → SocketIO → Browser) ─────────────────────────────
def parse_ticker_packet(data: bytes) -> dict | None:
    """Parse Dhan binary ticker packet (17 bytes)."""
    if len(data) < 17:
        return None
    try:
        response_code = data[0]
        # msg_length  = struct.unpack_from('<H', data, 1)[0]
        # exchange    = data[3]
        security_id = struct.unpack_from('<I', data, 4)[0]
        ltp         = struct.unpack_from('<f', data, 8)[0]
        ltt         = struct.unpack_from('<I', data, 12)[0]
        return {
            "type":        "ticker",
            "responseCode": response_code,
            "securityId":  security_id,
            "ltp":         round(ltp, 2),
            "ltt":         ltt,
        }
    except Exception:
        return None


def parse_quote_packet(data: bytes) -> dict | None:
    """Parse Dhan binary quote packet (83 bytes)."""
    if len(data) < 83:
        return None
    try:
        security_id = struct.unpack_from('<I', data, 4)[0]
        ltp         = struct.unpack_from('<f', data, 8)[0]
        ltt         = struct.unpack_from('<I', data, 12)[0]
        avg_price   = struct.unpack_from('<f', data, 16)[0]
        volume      = struct.unpack_from('<I', data, 20)[0]
        sell_qty    = struct.unpack_from('<I', data, 24)[0]
        buy_qty     = struct.unpack_from('<I', data, 28)[0]
        open_price  = struct.unpack_from('<f', data, 32)[0]
        close_price = struct.unpack_from('<f', data, 36)[0]
        high_price  = struct.unpack_from('<f', data, 40)[0]
        low_price   = struct.unpack_from('<f', data, 44)[0]
        return {
            "type":       "quote",
            "securityId": security_id,
            "ltp":        round(ltp, 2),
            "ltt":        ltt,
            "avgPrice":   round(avg_price, 2),
            "volume":     volume,
            "sellQty":    sell_qty,
            "buyQty":     buy_qty,
            "open":       round(open_price, 2),
            "close":      round(close_price, 2),
            "high":       round(high_price, 2),
            "low":        round(low_price, 2),
        }
    except Exception:
        return None


def dhan_ws_thread():
    """Background thread: connects to Dhan WebSocket and relays ticks to browser via SocketIO."""

    def on_open(ws):
        print("[WS] Connected to Dhan Market Feed")
        # Subscribe to major indices + stocks in QUOTE mode (RequestCode=17)
        instruments = []
        for sym, info in SECURITY_IDS.items():
            instruments.append({
                "ExchangeSegment": info["segment"],
                "SecurityId":      info["id"],
            })

        # Dhan allows max 100 per message — send in chunks
        chunk_size = 100
        for i in range(0, len(instruments), chunk_size):
            chunk = instruments[i:i + chunk_size]
            msg = json.dumps({
                "RequestCode":      17,            # Quote mode
                "InstrumentCount":  len(chunk),
                "InstrumentList":   chunk,
            })
            ws.send(msg)
        print(f"[WS] Subscribed {len(instruments)} instruments")

    def on_message(ws, message):
        if isinstance(message, bytes):
            pkt = None
            if len(message) >= 83:
                pkt = parse_quote_packet(message)
            elif len(message) >= 17:
                pkt = parse_ticker_packet(message)

            if pkt:
                sid = str(pkt["securityId"])
                live_ticks[sid] = pkt
                # Map security ID back to symbol name
                for sym, info in SECURITY_IDS.items():
                    if info["id"] == sid:
                        pkt["symbol"] = sym
                        break
                socketio.emit("tick", pkt)

    def on_error(ws, error):
        print(f"[WS] Error: {error}")

    def on_close(ws, code, msg):
        print(f"[WS] Connection closed ({code}): {msg}")
        # Reconnect after 5 seconds
        time.sleep(5)
        print("[WS] Reconnecting...")
        dhan_ws_thread()

    ws = websocket.WebSocketApp(
        DHAN_WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever(ping_interval=30, ping_timeout=10)


# ─── SOCKETIO EVENTS ─────────────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    print("[SocketIO] Browser connected")
    # Send current cached ticks immediately
    emit("ticks_snapshot", live_ticks)


@socketio.on("subscribe")
def on_subscribe(data):
    """Browser requests subscription to extra instruments."""
    print(f"[SocketIO] Subscribe request: {data}")


# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Start Dhan WebSocket relay in background thread
    ws_thread = threading.Thread(target=dhan_ws_thread, daemon=True)
    ws_thread.start()

    print("=" * 60)
    print("  NiftyEdge Pro — Dhan Options Trading Dashboard")
    print("  Running at http://127.0.0.1:5000")
    print("=" * 60)

    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
