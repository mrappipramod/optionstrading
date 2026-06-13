# ⚡ NiftyEdge Pro — Streamlit Edition

Dhan-powered options trading dashboard that runs entirely in your browser.
**No `.env` file needed** — enter your Dhan credentials on the login screen.

---

## 🚀 Deploy to Streamlit Cloud (Free)

### Step 1 — Upload to GitHub
1. Create a new **private** GitHub repository
2. Upload all files from this folder to it

### Step 2 — Deploy on Streamlit Cloud
1. Go to **[share.streamlit.io](https://share.streamlit.io)**
2. Sign in with GitHub
3. Click **New app**
4. Select your repository, branch `main`, file `app.py`
5. Click **Deploy**

Your app will be live at `https://yourname-niftyedge-xxxx.streamlit.app`

### Step 3 — Log In
Open the app URL, enter your Dhan credentials on the login screen, and trade!

---

## 🖥️ Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```
Open **http://localhost:8501**

---

## 🔐 Credential Security

- Credentials are stored only in **Streamlit session state** (browser memory)
- They are **never written to disk**, logged, or sent anywhere except Dhan's servers
- Each browser session is independent
- Refreshing the page logs you out (by design — keep credentials safe)

---

## 📦 File Structure

```
dhan_streamlit/
├── app.py              ← Main Streamlit app (login + dashboard)
├── ta_engine.py        ← Technical analysis engine (EMA, RSI, MACD, signals)
├── requirements.txt    ← Python dependencies
└── .streamlit/
    └── config.toml     ← Dark theme + layout config
```

---

## 📊 Features

| Feature | Details |
|---------|---------|
| Login screen | Client ID + Access Token entered in browser |
| Live candlestick chart | Plotly — interactive, zoomable |
| Timeframes | 1m, 5m, 15m, 25m, 1H |
| Indicators | EMA 9/21, VWAP, BB, RSI, MACD histogram |
| Signal engine | Score-based BUY/SELL/NEUTRAL with pattern name |
| Candle patterns | Engulfing, Hammer, Star, Marubozu, Doji |
| Option chain | OI bars, PCR ratio, ATM ±4 strikes |
| Order placement | BUY/SELL with lot size auto-calculation |
| Account data | Funds balance, open positions |
| Signal alerts | Log of recent signals with timestamps |

---

## ⚠️ Notes

1. **Access Token expires every 24 hours** — log out and log in again daily
2. **Data API subscription required** — ₹499+GST/month from Dhan
3. Market hours: 09:15–15:30 IST (Mon–Fri)
4. Paper trade first before using live orders

---

## 📄 License

MIT — Free for personal use.
