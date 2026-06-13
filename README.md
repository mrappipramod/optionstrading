# ⚡ NiftyEdge Pro — Dhan Options Trading Dashboard

A full-stack live options trading terminal powered by the **Dhan API (DhanHQ v2)**.
Real-time candlestick charts, automatic technical analysis, buy/sell signal detection,
option chain with OI/PCR, and order placement — all in one browser-based dashboard.

---

## 📦 Project Structure

```
dhan_trading/
├── app.py            ← Flask backend (REST proxy + WebSocket relay)
├── ta_engine.py      ← Pure-Python TA: EMA, RSI, MACD, BB, VWAP, ATR, candle patterns
├── requirements.txt  ← Python dependencies
├── .env              ← Your Dhan credentials (never commit this)
├── start.sh          ← One-click startup script
└── templates/
    └── index.html    ← Full trading UI (Chart.js + Socket.IO)
```

---

## 🚀 Quick Start

### 1. Get Dhan API Credentials

1. Log into **[api.dhan.co](https://api.dhan.co)**
2. Go to **My Apps → Create App**
3. Copy your **Client ID** and generate an **Access Token**
4. Subscribe to **DhanHQ Data APIs** (₹499+GST/month) for live market feed

### 2. Set Up Credentials

Edit `.env`:
```
DHAN_CLIENT_ID=1000XXXXXX
DHAN_ACCESS_TOKEN=eyJhbGciOiJIUzUxMiJ9...
```

### 3. Install & Run

**Linux / macOS:**
```bash
# Python 3.9+ required
pip install -r requirements.txt
bash start.sh
```

**Windows:**
```cmd
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:5000** in your browser.

---

## 📡 API Endpoints (Flask Backend)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Trading dashboard UI |
| GET | `/api/analyse?symbol=NIFTY&interval=15` | Candles + full TA + signals |
| GET | `/api/candles?symbol=NIFTY&interval=5` | Raw intraday OHLCV |
| GET | `/api/candles/daily?symbol=NIFTY` | Daily OHLCV |
| GET | `/api/quote?symbols=NIFTY,BANKNIFTY` | Live snapshot quotes |
| GET | `/api/optionchain?symbol=NIFTY&expiry=2024-12-26` | Full OI chain with Greeks |
| GET | `/api/optionchain/expiries?symbol=NIFTY` | Available expiry dates |
| GET | `/api/funds` | Available margin |
| GET | `/api/positions` | Open positions |
| GET | `/api/orders` | Order book |
| POST | `/api/place_order` | Place F&O order |

---

## 📊 Supported Symbols

| Symbol | Segment |
|--------|---------|
| NIFTY | IDX_I |
| BANKNIFTY | IDX_I |
| FINNIFTY | IDX_I |
| SENSEX | IDX_I |
| RELIANCE | NSE_EQ |
| HDFCBANK | NSE_EQ |
| INFY | NSE_EQ |
| TCS | NSE_EQ |
| WIPRO | NSE_EQ |
| ICICIBANK | NSE_EQ |

To add more symbols, add entries to `SECURITY_IDS` in `app.py`.
Security IDs are available at: https://dhanhq.co/docs/v2/instruments/

---

## 📈 Technical Indicators

All computed in `ta_engine.py` (no TA-Lib required):

| Indicator | Parameters |
|-----------|-----------|
| EMA | 9, 21, 50 periods |
| RSI | 14 periods |
| MACD | 12/26/9 |
| Bollinger Bands | 20 period, 2σ |
| VWAP | Session |
| ATR | 14 periods |

## 🕯️ Candle Pattern Detection

- Bullish / Bearish Engulfing
- Hammer & Shooting Star
- Morning Star & Evening Star
- Bullish / Bearish Marubozu
- Doji

## 🚦 Signal Engine (Score-Based)

| Condition | Score |
|-----------|-------|
| EMA Bullish/Bearish Stack | ±25 |
| EMA9 × EMA21 Crossover | ±20 |
| MACD Momentum | ±15 |
| Candle Pattern | ±15 each |
| RSI Zone | ±10 |
| VWAP Position | ±10 |
| Bollinger Band | ±5 |

**Score ≥ +30 → BUY signal | Score ≤ -30 → SELL signal**

---

## ⚡ Live Data Architecture

```
Dhan WebSocket Feed (wss://api-feed.dhan.co)
         │
         ▼
  Flask Background Thread
  (binary packet parser)
         │
         ▼
  Flask-SocketIO Server
         │
         ▼
  Browser (Socket.IO client)
  — Real-time tick updates
  — Sidebar prices
  — Toolbar live price
```

---

## ⚠️ Important Notes

1. **Access Token expires every 24 hours** — regenerate daily via Dhan portal
2. **Market hours**: NSE is open 09:15 – 15:30 IST (Mon–Fri)
3. **Option chain rate limit**: 1 request per 3 seconds (Dhan limitation)
4. **Lot sizes**: NIFTY = 50, BANKNIFTY = 15, FINNIFTY = 40 — update in `app.py`
5. **Paper trade first** before enabling live order placement
6. This software is for educational purposes. Trading involves risk.

---

## 🔧 Customisation

**Add a new symbol:**
```python
# In app.py → SECURITY_IDS
"BAJFINANCE": {"id": "317", "segment": "NSE_EQ"},
```

**Change lot sizes in order form:**
```javascript
// In templates/index.html → placeOrder()
const qty = parseInt(document.getElementById('f-qty').value) * 50; // change 50
```

**Adjust signal sensitivity:**
```python
# In ta_engine.py → analyse()
if score >= 30:   # Lower to 20 for more signals
```

---

## 📄 License

MIT — Free to use and modify for personal trading.
