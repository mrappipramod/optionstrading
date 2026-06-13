"""
NiftyEdge Pro — Streamlit Edition
Dhan-powered Options Trading Dashboard
Credentials entered directly in the browser — no .env needed.
"""

import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from ta_engine import analyse
from strategy_engine import run_all_strategies, consensus, ALL_STRATEGIES

# ─── PAGE CONFIG ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NiftyEdge Pro — Dhan Trading",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── GLOBAL STYLES ───────────────────────────────────────────────────────────
st.markdown("""
<style>
/* hide streamlit chrome */
#MainMenu, footer, header {visibility: hidden;}
.block-container {padding-top: 1rem; padding-bottom: 0.5rem;}

/* metric cards */
[data-testid="metric-container"] {
    background: #0d1525;
    border: 0.5px solid #1e3050;
    border-radius: 8px;
    padding: 8px 14px;
}
[data-testid="stMetricValue"] {font-size: 1.1rem !important; font-weight: 700;}
[data-testid="stMetricDelta"] {font-size: 0.75rem !important;}

/* signal boxes */
.sig-buy   {background:#00d4aa14;border:1.5px solid #00d4aa55;border-radius:10px;padding:14px;text-align:center;}
.sig-sell  {background:#f8717114;border:1.5px solid #f8717155;border-radius:10px;padding:14px;text-align:center;}
.sig-neutral{background:#4a6fa514;border:1.5px solid #4a6fa555;border-radius:10px;padding:14px;text-align:center;}
.sig-label {font-size:1.6rem;font-weight:800;letter-spacing:1px;}
.sig-sub   {font-size:0.8rem;color:#94a3b8;margin-top:4px;}
.sig-score {font-size:0.75rem;color:#4a6fa5;margin-top:3px;}

/* alert items */
.alert-item{display:flex;gap:8px;align-items:flex-start;padding:6px 0;
            border-bottom:0.5px solid #1e3050;font-size:0.8rem;}
.alert-item:last-child{border-bottom:none;}
.adot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-top:4px;}

/* login card */
.login-card{background:#0d1525;border:0.5px solid #1e3050;border-radius:14px;
            padding:2.5rem 2rem;max-width:460px;margin:4rem auto;}
.login-logo{font-size:2.2rem;font-weight:800;color:#00d4aa;text-align:center;margin-bottom:.4rem;}
.login-sub {text-align:center;color:#4a6fa5;font-size:.85rem;margin-bottom:1.8rem;}

/* ind-row */
.ind-row{display:flex;flex-wrap:wrap;gap:12px;background:#0d1525;border:0.5px solid #1e3050;
         border-radius:8px;padding:8px 14px;margin-bottom:6px;}
.ind-chip{font-size:.75rem;color:#4a6fa5;}
.ind-chip span{color:#e2e8f0;font-weight:600;margin-left:3px;}

/* oc rows */
.oc-row{display:grid;grid-template-columns:1fr 60px 1fr;gap:6px;
        font-size:.78rem;margin-bottom:4px;align-items:center;}
.oc-call{text-align:right;color:#00d4aa;font-weight:500;}
.oc-put {color:#f87171;font-weight:500;}
.oc-strike{text-align:center;font-weight:700;color:#e2e8f0;background:#1e3050;
           border-radius:4px;padding:1px 0;}

/* strength meter */
.str-row{display:flex;justify-content:space-between;padding:3px 0;font-size:.8rem;}
.str-name{color:#4a6fa5;}.str-val{font-weight:600;}

/* order form */
.order-card{background:#0d1525;border:0.5px solid #1e3050;border-radius:10px;padding:14px;}
</style>
""", unsafe_allow_html=True)

# ─── SESSION STATE DEFAULTS ───────────────────────────────────────────────────
defaults = {
    "authenticated": False,
    "client_id": "",
    "access_token": "",
    "symbol": "NIFTY",
    "interval": "15",
    "alerts": [],
    "analysis_cache": {},
    "last_fetch": {},
    "active_trades": {},
    "strategy_config": {},
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─── DHAN API HELPERS ─────────────────────────────────────────────────────────
DHAN_BASE = "https://api.dhan.co/v2"

SECURITY_IDS = {
    "NIFTY":     {"id": "13",    "segment": "IDX_I"},
    "BANKNIFTY": {"id": "25",    "segment": "IDX_I"},
    "FINNIFTY":  {"id": "27",    "segment": "IDX_I"},
    "SENSEX":    {"id": "1",     "segment": "IDX_I"},
    "RELIANCE":  {"id": "2885",  "segment": "NSE_EQ"},
    "HDFCBANK":  {"id": "1333",  "segment": "NSE_EQ"},
    "INFY":      {"id": "10604", "segment": "NSE_EQ"},
    "TCS":       {"id": "11536", "segment": "NSE_EQ"},
    "WIPRO":     {"id": "3787",  "segment": "NSE_EQ"},
    "ICICIBANK": {"id": "4963",  "segment": "NSE_EQ"},
}

LOT_SIZES = {"NIFTY": 75, "BANKNIFTY": 30, "FINNIFTY": 65, "SENSEX": 20}

def get_headers():
    return {
        "Content-Type": "application/json",
        "access-token": st.session_state.access_token,
        "client-id":    st.session_state.client_id,
    }

def dhan_post(path, body, timeout=12):
    try:
        r = requests.post(f"{DHAN_BASE}{path}", headers=get_headers(), json=body, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}

def dhan_get(path, timeout=10):
    try:
        r = requests.get(f"{DHAN_BASE}{path}", headers=get_headers(), timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}

def verify_credentials(client_id, access_token):
    """
    Verify Dhan credentials. Returns (ok: bool, debug_msg: str).
    Accepts 200/204/429 as valid; rejects 401/403/5xx.
    """
    headers = {
        "Content-Type": "application/json",
        "access-token": access_token.strip(),
        "client-id":    client_id.strip(),
    }
    try:
        r = requests.get(f"{DHAN_BASE}/funds/balance", headers=headers, timeout=10)
        code = r.status_code
        try:
            body = r.json()
        except Exception:
            body = r.text[:300]

        if code == 200:
            return True, "Connected"
        elif code in (401, 403):
            msg = ""
            if isinstance(body, dict):
                msg = body.get("errorMessage") or body.get("message") or body.get("error") or str(body)
            else:
                msg = str(body)
            return False, f"HTTP {code}: {msg or 'Invalid credentials'}"
        elif code == 429:
            return True, "Rate limited but credentials accepted"
        elif code >= 500:
            return False, f"Dhan server error (HTTP {code}). Try again in a moment."
        else:
            return True, f"Connected (HTTP {code})"
    except requests.exceptions.Timeout:
        return False, "Request timed out — check your internet connection."
    except requests.exceptions.ConnectionError:
        return False, "Could not reach Dhan API — check your internet connection."
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

def fetch_candles(symbol, interval="15"):
    info = SECURITY_IDS.get(symbol)
    if not info:
        return None
    from_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    to_date   = datetime.now().strftime("%Y-%m-%d")
    body = {
        "securityId":      info["id"],
        "exchangeSegment": info["segment"],
        "instrument":      "INDEX" if info["segment"] == "IDX_I" else "EQUITY",
        "interval":        interval,
        "oi":              False,
        "fromDate":        from_date,
        "toDate":          to_date,
    }
    return dhan_post("/charts/intraday", body)

def fetch_quote(symbol):
    info = SECURITY_IDS.get(symbol)
    if not info:
        return None
    body = {info["segment"]: [info["id"]]}
    return dhan_post("/marketfeed/quote", body)

def fetch_option_chain(symbol):
    info = SECURITY_IDS.get(symbol)
    if not info:
        return None, None
    # Get expiries first
    exp_body = {"UnderlyingScrip": int(info["id"]), "UnderlyingSeg": info["segment"]}
    exp_data = dhan_post("/optionchain/expirylist", exp_body)
    expiries = exp_data.get("data", [])
    if not expiries:
        return None, None
    nearest = expiries[0]
    chain_body = {
        "UnderlyingScrip": int(info["id"]),
        "UnderlyingSeg":   info["segment"],
        "Expirydate":      nearest,
    }
    chain = dhan_post("/optionchain", chain_body)
    return chain.get("data") or chain, nearest

def fetch_funds():
    return dhan_get("/funds/balance")

def fetch_positions():
    return dhan_get("/portfolio/positions")

def place_order(security_id, txn, product, qty, price):
    body = {
        "dhanClientId":    st.session_state.client_id,
        "transactionType": txn,
        "exchangeSegment": "NSE_FNO",
        "productType":     product,
        "orderType":       "LIMIT" if price > 0 else "MARKET",
        "validity":        "DAY",
        "securityId":      security_id,
        "quantity":        qty,
        "price":           price,
        "triggerPrice":    0,
        "disclosedQuantity": 0,
        "afterMarketOrder": False,
    }
    return dhan_post("/orders", body)

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def fmt(v, decimals=2):
    if isinstance(v, (int, float)):
        return f"{v:,.{decimals}f}"
    return str(v)

def fmt_oi(v):
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    if v >= 1_000:     return f"{v/1_000:.0f}K"
    return str(int(v))

def add_alert(atype, text):
    now = datetime.now().strftime("%H:%M IST")
    st.session_state.alerts.insert(0, {"type": atype, "text": text, "time": now})
    if len(st.session_state.alerts) > 10:
        st.session_state.alerts.pop()

# ─── CHART BUILDER ───────────────────────────────────────────────────────────
COLORS = {"green": "#00d4aa", "red": "#f87171", "amber": "#f59e0b",
          "blue": "#60a5fa", "purple": "#a78bfa", "gray": "#4a6fa5"}

def build_chart(candles, candle_signals, indicators, show_ema=True, show_vwap=True, show_bb=False):
    if not candles:
        return None

    df = pd.DataFrame(candles)
    df["dt"] = pd.to_datetime(df["t"], unit="s").dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata")

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.65, 0.15, 0.20],
        subplot_titles=("", "Volume", "MACD"),
    )

    # ── Candlesticks ──
    fig.add_trace(go.Candlestick(
        x=df["dt"],
        open=df["o"], high=df["h"], low=df["l"], close=df["c"],
        increasing_line_color=COLORS["green"], decreasing_line_color=COLORS["red"],
        increasing_fillcolor=COLORS["green"]+"66", decreasing_fillcolor=COLORS["red"]+"66",
        name="Price", line_width=1,
    ), row=1, col=1)

    # ── EMA lines ──
    if show_ema and "ema9" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["dt"], y=df["ema9"], name="EMA9",
            line=dict(color=COLORS["purple"], width=1), mode="lines",
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df["dt"], y=df["ema21"], name="EMA21",
            line=dict(color=COLORS["blue"], width=1), mode="lines",
        ), row=1, col=1)

    # ── VWAP ──
    if show_vwap and "vwap" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["dt"], y=df["vwap"], name="VWAP",
            line=dict(color=COLORS["amber"], width=1, dash="dash"), mode="lines",
        ), row=1, col=1)

    # ── Bollinger Bands ──
    if show_bb and indicators:
        for label, val, col in [
            ("BB Upper", indicators["bb_upper"], COLORS["gray"]),
            ("BB Mid",   indicators["bb_mid"],   COLORS["gray"]),
            ("BB Lower", indicators["bb_lower"],  COLORS["gray"]),
        ]:
            fig.add_trace(go.Scatter(
                x=df["dt"], y=[val] * len(df), name=label,
                line=dict(color=col, width=0.8, dash="dot"), mode="lines",
            ), row=1, col=1)

    # ── Buy/Sell signal markers ──
    if candle_signals:
        buys  = [s for s in candle_signals if s["direction"] == "BUY"]
        sells = [s for s in candle_signals if s["direction"] == "SELL"]
        dojs  = [s for s in candle_signals if s["direction"] == "NEUTRAL"]

        def get_dt(idx):
            return df["dt"].iloc[idx] if idx < len(df) else None

        if buys:
            bx = [get_dt(s["index"]) for s in buys if s["index"] < len(df)]
            by = [df["l"].iloc[s["index"]] * 0.999 for s in buys if s["index"] < len(df)]
            fig.add_trace(go.Scatter(
                x=bx, y=by,
                mode="markers+text",
                marker=dict(symbol="triangle-up", size=12, color=COLORS["green"]),
                text=["BUY"] * len(bx), textposition="bottom center",
                textfont=dict(size=8, color=COLORS["green"]),
                name="BUY Signal", showlegend=True,
            ), row=1, col=1)

        if sells:
            sx = [get_dt(s["index"]) for s in sells if s["index"] < len(df)]
            sy = [df["h"].iloc[s["index"]] * 1.001 for s in sells if s["index"] < len(df)]
            fig.add_trace(go.Scatter(
                x=sx, y=sy,
                mode="markers+text",
                marker=dict(symbol="triangle-down", size=12, color=COLORS["red"]),
                text=["SELL"] * len(sx), textposition="top center",
                textfont=dict(size=8, color=COLORS["red"]),
                name="SELL Signal", showlegend=True,
            ), row=1, col=1)

        if dojs:
            dx = [get_dt(s["index"]) for s in dojs if s["index"] < len(df)]
            dy = [df["h"].iloc[s["index"]] * 1.001 for s in dojs if s["index"] < len(df)]
            fig.add_trace(go.Scatter(
                x=dx, y=dy,
                mode="markers",
                marker=dict(symbol="diamond", size=8, color=COLORS["amber"]),
                name="Doji", showlegend=True,
            ), row=1, col=1)

    # ── Volume ──
    vol_colors = [COLORS["green"]+"88" if r["c"] >= r["o"] else COLORS["red"]+"88" for _, r in df.iterrows()]
    fig.add_trace(go.Bar(
        x=df["dt"], y=df["v"],
        marker_color=vol_colors, name="Volume", showlegend=False,
    ), row=2, col=1)

    # ── MACD Histogram ──
    if "macd_hist" in df.columns:
        macd_colors = [COLORS["green"]+"88" if v >= 0 else COLORS["red"]+"88" for v in df["macd_hist"]]
        fig.add_trace(go.Bar(
            x=df["dt"], y=df["macd_hist"],
            marker_color=macd_colors, name="MACD Hist", showlegend=False,
        ), row=3, col=1)

    # ── Layout ──
    fig.update_layout(
        height=520,
        paper_bgcolor="#060b18",
        plot_bgcolor="#0a1020",
        font=dict(color="#94a3b8", size=10),
        xaxis_rangeslider_visible=False,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
            bgcolor="rgba(0,0,0,0)", font=dict(size=10),
        ),
        margin=dict(l=0, r=50, t=10, b=0),
    )
    for row in range(1, 4):
        axis = "yaxis" if row == 1 else f"yaxis{row}"
        fig.update_layout(**{axis: dict(
            gridcolor="#1e3050", gridwidth=0.5,
            zerolinecolor="#1e3050",
            tickfont=dict(color="#4a6fa5", size=9),
        )})
    fig.update_xaxes(
        gridcolor="#1e3050", gridwidth=0.5,
        tickfont=dict(color="#4a6fa5", size=9),
        showticklabels=True,
    )

    return fig

# ═════════════════════════════════════════════════════════════════════════════
#  LOGIN SCREEN
# ═════════════════════════════════════════════════════════════════════════════
def show_login():
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("""
        <div class="login-card">
          <div class="login-logo">⚡ NiftyEdge Pro</div>
          <div class="login-sub">Dhan-powered Options Trading Dashboard<br>
          Enter your DhanHQ API credentials to continue</div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            client_id = st.text_input(
                "Client ID",
                placeholder="Your Dhan Client ID (e.g. 1000XXXXXX)",
                help="Found in DhanHQ → My Profile → Client ID",
            )
            access_token = st.text_input(
                "Access Token",
                type="password",
                placeholder="Paste your Access Token here",
                help="Generate at api.dhan.co → My Apps → Access Token (valid 24h)",
            )
            submitted = st.form_submit_button("🔐 Connect to Dhan", use_container_width=True)

        if submitted:
            if not client_id.strip() or not access_token.strip():
                st.error("Both Client ID and Access Token are required.")
            else:
                # Stash creds in session so bypass button can read them
                st.session_state["_login_cid"] = client_id.strip()
                st.session_state["_login_tok"] = access_token.strip()
                with st.spinner("Verifying credentials with Dhan API..."):
                    ok, debug_msg = verify_credentials(client_id.strip(), access_token.strip())
                if ok:
                    st.session_state.authenticated = True
                    st.session_state.client_id     = client_id.strip()
                    st.session_state.access_token  = access_token.strip()
                    st.success(f"✅ Connected! {debug_msg}. Loading dashboard...")
                    time.sleep(0.8)
                    st.rerun()
                else:
                    st.error(f"❌ Authentication failed — {debug_msg}")
                    with st.expander("🔍 Troubleshooting tips"):
                        st.markdown("""
**Common reasons for failure:**

1. **Wrong Client ID format** — Use only the numeric ID (e.g. `1000123456`), no spaces or dashes
2. **Expired Access Token** — Dhan tokens expire every 24 hours. Generate a fresh one at [api.dhan.co](https://api.dhan.co)
3. **Token not activated** — After generating, wait 1–2 minutes before first use
4. **Extra spaces** — Make sure you didn't accidentally copy a leading/trailing space
5. **Data API not subscribed** — Some endpoints need the ₹499/month Data API subscription

**To get a fresh Access Token:**
- Go to [api.dhan.co](https://api.dhan.co) → My Apps → Select your app → Generate Token
- Copy the full token (it starts with `eyJ...`)
                        """)

        # ── Bypass button (for users whose verification call fails but token works) ──
        st.markdown("<div style='text-align:center;margin-top:10px;font-size:.75rem;color:#4a6fa5;'>Verification failing but you know your credentials are correct?</div>", unsafe_allow_html=True)
        bypass_col1, bypass_col2, bypass_col3 = st.columns([1, 2, 1])
        with bypass_col2:
            if st.button("⚡ Connect anyway (skip check)", use_container_width=True, help="Use this if the API check fails but your credentials are valid — e.g. outside market hours or rate limits."):
                cid = st.session_state.get("_login_cid", "")
                tok = st.session_state.get("_login_tok", "")
                if cid and tok:
                    st.session_state.authenticated = True
                    st.session_state.client_id     = cid
                    st.session_state.access_token  = tok
                    st.rerun()
                else:
                    st.warning("Enter and submit your credentials first, then click this if you get an error.")

        st.markdown("""
        <div style='text-align:center;margin-top:1rem;font-size:.78rem;color:#4a6fa5;'>
        🔒 Your credentials are stored only in your browser session<br>
        and are never saved to disk or sent to any third party.<br><br>
        Get credentials → <a href='https://api.dhan.co' target='_blank' style='color:#00d4aa'>api.dhan.co</a>
        &nbsp;|&nbsp; Requires <a href='https://dhan.co/support/platforms/dhanhq-api/how-can-i-access-live-market-data-through-dhan/' target='_blank' style='color:#00d4aa'>Data API subscription</a>
        </div>
        """, unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
#  MAIN DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════
def show_dashboard():

    # ── SIDEBAR ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"""
        <div style='font-size:1.2rem;font-weight:700;color:#00d4aa;margin-bottom:4px;'>⚡ NiftyEdge Pro</div>
        <div style='font-size:.72rem;color:#4a6fa5;margin-bottom:1rem;'>
        Client: {st.session_state.client_id[:6]}••••••
        </div>
        """, unsafe_allow_html=True)

        # Symbol selector
        st.markdown("**Select Instrument**")
        symbol = st.selectbox(
            "Instrument",
            list(SECURITY_IDS.keys()),
            index=list(SECURITY_IDS.keys()).index(st.session_state.symbol),
            label_visibility="collapsed",
        )
        if symbol != st.session_state.symbol:
            st.session_state.symbol = symbol
            st.rerun()

        # Timeframe
        tf_map = {"1 min": "1", "5 min": "5", "15 min": "15", "25 min": "25", "1 Hour": "60"}
        tf_label = st.selectbox("Timeframe", list(tf_map.keys()), index=2)
        interval = tf_map[tf_label]
        if interval != st.session_state.interval:
            st.session_state.interval = interval

        # Overlay toggles
        st.markdown("**Chart Overlays**")
        show_ema  = st.checkbox("EMA 9 / 21",  value=True)
        show_vwap = st.checkbox("VWAP",         value=True)
        show_bb   = st.checkbox("Bollinger Bands", value=False)

        st.divider()

        # Funds
        st.markdown("**Account**")
        if st.button("Refresh Funds", use_container_width=True):
            funds = fetch_funds()
            if "availabelBalance" in funds:
                st.metric("Available", f"₹{funds['availabelBalance']:,.2f}")
            elif "error" in funds:
                st.error(funds["error"])

        # Positions
        if st.button("View Positions", use_container_width=True):
            pos = fetch_positions()
            if isinstance(pos, list) and pos:
                pf = pd.DataFrame(pos)[["tradingSymbol", "netQty", "buyAvg", "sellAvg", "unrealizedProfit"]]
                pf.columns = ["Symbol", "Qty", "Buy Avg", "Sell Avg", "P&L"]
                st.dataframe(pf, use_container_width=True, hide_index=True)
            elif "error" in (pos or {}):
                st.error(pos["error"])
            else:
                st.info("No open positions")

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            for k in ["authenticated", "client_id", "access_token", "analysis_cache", "last_fetch", "alerts"]:
                st.session_state[k] = defaults[k]
            st.rerun()

    # ── TOP METRICS BAR ──────────────────────────────────────────────────────
    sym = st.session_state.symbol
    now_ist = datetime.now().strftime("%d %b %Y  %H:%M IST")
    st.markdown(f"""
    <div style='display:flex;justify-content:space-between;align-items:center;
         background:#0d1525;border:0.5px solid #1e3050;border-radius:8px;
         padding:8px 16px;margin-bottom:10px;'>
      <span style='font-size:1rem;font-weight:700;color:#00d4aa;'>⚡ NiftyEdge Pro</span>
      <span style='font-size:.8rem;color:#4a6fa5;'>🕐 {now_ist}</span>
    </div>
    """, unsafe_allow_html=True)

    # Fetch live quote for top metrics
    quote_data = fetch_quote(sym)
    ltp, chg, pct = 0.0, 0.0, 0.0
    if quote_data and not quote_data.get("error"):
        seg = SECURITY_IDS[sym]["segment"]
        sid = SECURITY_IDS[sym]["id"]
        q = (quote_data.get(seg) or {}).get(sid, {})
        ltp      = q.get("ltp", 0)
        prev_cls = q.get("previousClosePrice", ltp)
        chg  = ltp - prev_cls
        pct  = (chg / prev_cls * 100) if prev_cls else 0

    mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)
    with mcol1:
        st.metric(sym, f"₹{ltp:,.2f}", f"{chg:+.2f} ({pct:+.2f}%)")
    with mcol2:
        q2 = fetch_quote("NIFTY") if sym != "NIFTY" else quote_data
        n_ltp = 0
        if q2 and not q2.get("error"):
            n_ltp = (q2.get("IDX_I") or {}).get("13", {}).get("ltp", 0)
        st.metric("NIFTY", f"₹{n_ltp:,.2f}")
    with mcol3:
        q3 = fetch_quote("BANKNIFTY") if sym != "BANKNIFTY" else quote_data
        b_ltp = 0
        if q3 and not q3.get("error"):
            b_ltp = (q3.get("IDX_I") or {}).get("25", {}).get("ltp", 0)
        st.metric("BANKNIFTY", f"₹{b_ltp:,.2f}")
    with mcol4:
        st.metric("Market", "OPEN" if 9 <= datetime.now().hour < 16 else "CLOSED",
                  delta_color="off")
    with mcol5:
        st.metric("Interval", tf_label)

    # ── FETCH ANALYSIS ───────────────────────────────────────────────────────
    cache_key = f"{sym}_{interval}"
    last_fetch = st.session_state.last_fetch.get(cache_key, 0)
    cache_ttl  = 120  # seconds

    if time.time() - last_fetch > cache_ttl:
        with st.spinner(f"Fetching {sym} {tf_label} candles from Dhan..."):
            raw = fetch_candles(sym, interval)
        if raw and not raw.get("error") and raw.get("close"):
            result = analyse(raw)
            result["symbol"] = sym
            st.session_state.analysis_cache[cache_key] = result
            st.session_state.last_fetch[cache_key]    = time.time()
            # Add signal alert
            sig = result.get("signal", {})
            if sig.get("type") in ("BUY", "SELL"):
                pats = sig.get("patterns", [])
                pat_str = pats[0]["pattern"] if pats else sig.get("reasons", [""])[0]
                add_alert(sig["type"], f"{sym} — {pat_str} ({tf_label})")
        else:
            err = (raw or {}).get("error", "No data returned")
            st.error(f"⚠️ Could not fetch candles: {err}")
            result = st.session_state.analysis_cache.get(cache_key)
    else:
        result = st.session_state.analysis_cache.get(cache_key)

    # ── TABS ─────────────────────────────────────────────────────────────────
    tab_chart, tab_strategy, tab_settings = st.tabs([
        "📈 Chart & Analysis",
        "🎯 Strategy Signals",
        "⚙️ Strategy Config",
    ])

    # ── LAYOUT: CHART | RIGHT PANEL ──────────────────────────────────────────
    with tab_chart:
     chart_col, right_col = st.columns([3, 1], gap="small")

    with chart_col:
        if result:
            ind = result.get("indicators", {})
            # Indicators bar
            ema9  = fmt(ind.get("ema9", 0))
            ema21 = fmt(ind.get("ema21", 0))
            rsi_v = ind.get("rsi", 0)
            macd_v = ind.get("macd", 0)
            hist_v = ind.get("macd_hist", 0)
            vwap_v = fmt(ind.get("vwap", 0))
            atr_v  = ind.get("atr", 0)
            bb_lo  = fmt(ind.get("bb_lower", 0))
            bb_hi  = fmt(ind.get("bb_upper", 0))

            rsi_col  = "#00d4aa" if 30 < rsi_v < 70 else "#f87171"
            macd_col = "#00d4aa" if macd_v > 0 else "#f87171"
            hist_col = "#00d4aa" if hist_v > 0 else "#f87171"

            st.markdown(f"""
            <div class="ind-row">
              <span class="ind-chip">EMA9 <span>{ema9}</span></span>
              <span class="ind-chip">EMA21 <span>{ema21}</span></span>
              <span class="ind-chip">RSI(14) <span style="color:{rsi_col}">{rsi_v}</span></span>
              <span class="ind-chip">MACD <span style="color:{macd_col}">{macd_v:+.1f}</span></span>
              <span class="ind-chip">Hist <span style="color:{hist_col}">{hist_v:+.1f}</span></span>
              <span class="ind-chip">VWAP <span>{vwap_v}</span></span>
              <span class="ind-chip">ATR <span>{atr_v}</span></span>
              <span class="ind-chip">BB <span>{bb_lo} – {bb_hi}</span></span>
            </div>
            """, unsafe_allow_html=True)

            fig = build_chart(
                result.get("candles"),
                result.get("candle_signals"),
                ind,
                show_ema=show_ema,
                show_vwap=show_vwap,
                show_bb=show_bb,
            )
            if fig:
                st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
        else:
            st.info("Loading chart data...")

    # ── RIGHT PANEL ──────────────────────────────────────────────────────────
    with right_col:

        # Signal Engine
        st.markdown("#### Signal Engine")
        if result:
            sig = result.get("signal", {})
            stype = sig.get("type", "NEUTRAL")
            score = sig.get("score", 0)
            conf  = sig.get("confidence", "")
            pats  = sig.get("patterns", [])
            reas  = sig.get("reasons", [])
            emoji = "🟢" if stype == "BUY" else "🔴" if stype == "SELL" else "🟡"
            pat_str = pats[0]["pattern"] if pats else (reas[0] if reas else "—")
            cls   = "sig-" + stype.lower()

            st.markdown(f"""
            <div class="{cls}">
              <div class="sig-label">{emoji} {stype}</div>
              <div class="sig-sub">{pat_str}</div>
              <div class="sig-score">Score: {score:+d} · {conf}</div>
            </div>
            """, unsafe_allow_html=True)

            # Strength meter
            st.markdown("<br>", unsafe_allow_html=True)
            ind = result.get("indicators", {})
            rsi_v = ind.get("rsi", 50)
            reasons_str = " ".join(sig.get("reasons", []))

            def val_badge(condition, true_txt, false_txt):
                return f'<span style="color:#00d4aa">{true_txt}</span>' if condition else f'<span style="color:#f87171">{false_txt}</span>'

            ema_bull  = "EMA Bullish" in reasons_str
            macd_bull = ind.get("macd_hist", 0) > 0
            vwap_above = "Above VWAP" in reasons_str

            st.markdown(f"""
            <div style='font-size:.78rem;'>
              <div class="str-row"><span class="str-name">EMA Stack</span>
                {val_badge(ema_bull, "🟢 Bullish", "🔴 Bearish")}</div>
              <div class="str-row"><span class="str-name">RSI ({rsi_v})</span>
                {val_badge(30 < rsi_v < 70, "🟢 Neutral", "⚠️ Extreme")}</div>
              <div class="str-row"><span class="str-name">MACD Hist</span>
                {val_badge(macd_bull, "🟢 Bull", "🔴 Bear")}</div>
              <div class="str-row"><span class="str-name">VWAP</span>
                {val_badge(vwap_above, "🟢 Above", "🔴 Below")}</div>
              <div class="str-row"><span class="str-name">Patterns</span>
                <span style='color:#e2e8f0'>{", ".join(p["pattern"] for p in pats) or "—"}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # RSI progress bar
            rsi_pct = int(min(max(rsi_v, 0), 100))
            rsi_bar_col = "#f87171" if rsi_v > 70 or rsi_v < 30 else "#00d4aa"
            st.markdown(f"""
            <div style='margin:8px 0 2px;'>
              <div style='height:6px;border-radius:3px;background:#1e3050;overflow:hidden;'>
                <div style='height:100%;width:{rsi_pct}%;background:{rsi_bar_col};border-radius:3px;'></div>
              </div>
              <div style='display:flex;justify-content:space-between;font-size:9px;color:#4a6fa5;margin-top:2px;'>
                <span>OS 30</span><span>RSI</span><span>OB 70</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.divider()

        # Option Chain
        st.markdown("#### Option Chain — OI")
        with st.spinner("Loading OI..."):
            chain_data, expiry_date = fetch_option_chain(sym)

        if expiry_date:
            st.caption(f"Expiry: {expiry_date}")

        if chain_data and isinstance(chain_data, list) and len(chain_data):
            try:
                sorted_chain = sorted(chain_data, key=lambda x: x.get("strikePrice", 0))
                max_oi = max(
                    max((s.get("callOI", 0) for s in sorted_chain), default=1),
                    max((s.get("putOI",  0) for s in sorted_chain), default=1),
                )
                total_call_oi = sum(s.get("callOI", 0) for s in sorted_chain)
                total_put_oi  = sum(s.get("putOI",  0) for s in sorted_chain)

                # ATM ± 5 strikes
                mid = ltp or sorted_chain[len(sorted_chain)//2].get("strikePrice", 0)
                sorted_chain.sort(key=lambda x: abs(x.get("strikePrice", 0) - mid))
                atm_slice = sorted_chain[:9]
                atm_slice.sort(key=lambda x: x.get("strikePrice", 0))

                st.markdown("""
                <div class="oc-row" style='font-size:.7rem;color:#4a6fa5;border-bottom:0.5px solid #1e3050;padding-bottom:3px;'>
                  <div style='text-align:right'>CALL OI</div><div style='text-align:center'>Strike</div><div>PUT OI</div>
                </div>""", unsafe_allow_html=True)

                for s in atm_slice:
                    sp = s.get("strikePrice", 0)
                    coi = s.get("callOI", 0)
                    poi = s.get("putOI",  0)
                    c_pct = int(coi / max_oi * 100)
                    p_pct = int(poi / max_oi * 100)
                    is_atm = abs(sp - mid) < (atm_slice[1]["strikePrice"] - atm_slice[0]["strikePrice"] if len(atm_slice) > 1 else 100)
                    strike_style = "color:#f59e0b;font-weight:800;" if is_atm else ""
                    st.markdown(f"""
                    <div class="oc-row">
                      <div style='text-align:right'>
                        <span class='oc-call'>{fmt_oi(coi)}</span>
                        <div style='height:3px;border-radius:1px;background:linear-gradient(to left,#f8717188 {c_pct}%,transparent 0);margin-top:2px;'></div>
                      </div>
                      <div class='oc-strike' style='{strike_style}'>{int(sp)}</div>
                      <div>
                        <span class='oc-put'>{fmt_oi(poi)}</span>
                        <div style='height:3px;border-radius:1px;background:linear-gradient(to right,#00d4aa88 {p_pct}%,transparent 0);margin-top:2px;'></div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

                pcr = total_put_oi / total_call_oi if total_call_oi else 0
                pcr_col = "#00d4aa" if pcr > 1.2 else "#f87171" if pcr < 0.8 else "#f59e0b"
                st.markdown(f"""
                <div style='font-size:.75rem;color:#4a6fa5;margin-top:6px;'>
                  PCR: <span style='color:{pcr_col};font-weight:700;'>{pcr:.2f}</span>
                  &nbsp;·&nbsp; Call OI: <span style='color:#f87171'>{fmt_oi(total_call_oi)}</span>
                  &nbsp;·&nbsp; Put OI: <span style='color:#00d4aa'>{fmt_oi(total_put_oi)}</span>
                </div>
                """, unsafe_allow_html=True)
            except Exception as e:
                st.caption(f"OI display error: {e}")
        else:
            st.caption("No option chain data. Check Data API subscription.")

        st.divider()

        # Order Placement
        st.markdown("#### Place F&O Order")
        with st.container():
            sec_id = st.text_input("Security ID (F&O scrip)", placeholder="e.g. 35001", key="order_secid",
                                   help="Find at dhanhq.co/docs/v2/instruments/")
            ocol1, ocol2 = st.columns(2)
            with ocol1:
                txn     = st.selectbox("Side",    ["BUY", "SELL"], key="order_txn")
                qty_lots = st.number_input("Lots", min_value=1, value=1, key="order_qty")
            with ocol2:
                product = st.selectbox("Product", ["INTRADAY", "CNC"], key="order_product")
                price   = st.number_input("Price (0=Market)", min_value=0.0, step=0.05, value=0.0, key="order_price")

            lot_size = LOT_SIZES.get(sym, 50)
            total_qty = qty_lots * lot_size
            st.caption(f"Lot size: {lot_size} · Total qty: {total_qty}")

            b1, b2 = st.columns(2)
            with b1:
                if st.button("🟢 BUY CE", use_container_width=True, type="primary"):
                    if not sec_id:
                        st.error("Enter Security ID")
                    else:
                        res = place_order(sec_id, "BUY", product, total_qty, price)
                        if res.get("orderId") or res.get("status") == "success":
                            oid = res.get("orderId") or "OK"
                            st.success(f"✅ BUY placed — Order ID: {oid}")
                            add_alert("BUY", f"CE BUY {sec_id} × {total_qty} @ {'Market' if price == 0 else price}")
                        else:
                            st.error(res.get("errorMessage") or str(res))
            with b2:
                if st.button("🔴 SELL/PE", use_container_width=True):
                    if not sec_id:
                        st.error("Enter Security ID")
                    else:
                        res = place_order(sec_id, txn, product, total_qty, price)
                        if res.get("orderId") or res.get("status") == "success":
                            oid = res.get("orderId") or "OK"
                            st.success(f"✅ Order placed — {oid}")
                            add_alert("SELL", f"{txn} {sec_id} × {total_qty} @ {'Market' if price == 0 else price}")
                        else:
                            st.error(res.get("errorMessage") or str(res))

        st.divider()

        # Signal Alerts
        st.markdown("#### Signal Alerts")
        alerts = st.session_state.alerts
        if not alerts:
            st.caption("No alerts yet — signals will appear here.")
        else:
            for a in alerts[:8]:
                col_map = {"BUY": "#00d4aa", "SELL": "#f87171", "INFO": "#60a5fa"}
                col = col_map.get(a["type"], "#4a6fa5")
                st.markdown(f"""
                <div class="alert-item">
                  <div class="adot" style="background:{col};"></div>
                  <div>
                    <span style='color:{col};font-weight:700;font-size:.78rem;'>{a["type"]}</span>
                    <span style='color:#94a3b8;font-size:.78rem;'> {a["text"]}</span>
                    <div style='font-size:.68rem;color:#4a6fa5;'>{a["time"]}</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

        # Auto-refresh during market hours
        mhour = datetime.now().hour
        if 9 <= mhour < 16:
            time.sleep(0.1)
            st.markdown("""
            <div style='font-size:.68rem;color:#4a6fa5;text-align:center;margin-top:8px;'>
            🔄 Auto-refresh every 2 min during market hours
            </div>""", unsafe_allow_html=True)

    # ═══ TAB 2: STRATEGY SIGNALS ═══════════════════════════════════════════
    with tab_strategy:
        show_strategy_tab(result, sym, tf_label)

    # ═══ TAB 3: STRATEGY CONFIG ═════════════════════════════════════════════
    with tab_settings:
        show_strategy_config_tab()


# ─── STRATEGY SIGNALS TAB ────────────────────────────────────────────────────
def show_strategy_tab(result, sym, tf_label):
    if not result:
        st.info("Load chart data first (Chart & Analysis tab).")
        return

    config      = st.session_state.get("strategy_config", {})
    active_trades = st.session_state.get("active_trades", {})

    # Run all strategies
    setups = run_all_strategies(result, config, active_trades)
    con    = consensus(setups)

    # ── CONSENSUS BANNER ──────────────────────────────────────────────────
    con_dir = con["consensus"]
    con_col = ("#00d4aa" if "BUY" in con_dir else
               "#f87171" if "SELL" in con_dir else
               "#f59e0b" if con_dir in ("STOP_LOSS","EXIT") else "#4a6fa5")
    con_bg  = con_col + "18"
    con_emoji = ("🟢" if "BUY" in con_dir else "🔴" if "SELL" in con_dir else
                 "⚠️" if con_dir in ("STOP_LOSS","EXIT") else "⏸️")

    st.markdown(f"""
    <div style='background:{con_bg};border:1.5px solid {con_col}55;border-radius:12px;
         padding:16px 20px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center;'>
      <div>
        <div style='font-size:.72rem;color:#4a6fa5;margin-bottom:2px;'>STRATEGY CONSENSUS — {sym} ({tf_label})</div>
        <div style='font-size:1.7rem;font-weight:800;color:{con_col};letter-spacing:1px;'>{con_emoji} {con_dir}</div>
      </div>
      <div style='text-align:right;font-size:.78rem;'>
        <span style='color:#00d4aa;'>▲ Bull: {con["bull_count"]}</span> &nbsp;
        <span style='color:#f87171;'>▼ Bear: {con["bear_count"]}</span> &nbsp;
        <span style='color:#f59e0b;'>⏸ Hold: {con["hold_count"]}</span> &nbsp;
        <span style='color:#4a6fa5;'>⏳ Wait: {con["wait_count"]}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── STRATEGY CARDS ────────────────────────────────────────────────────
    for strat_name, setup in setups.items():
        action = setup.action
        col_map = {
            "ENTER_LONG":  ("#00d4aa", "🟢 ENTER LONG  —  BUY CE"),
            "ENTER_SHORT": ("#f87171", "🔴 ENTER SHORT  —  BUY PE"),
            "HOLD":        ("#f59e0b", "⏸️ HOLD"),
            "EXIT_LONG":   ("#60a5fa", "🔵 EXIT LONG"),
            "EXIT_SHORT":  ("#60a5fa", "🔵 EXIT SHORT"),
            "STOP_LOSS":   ("#ef4444", "🚨 STOP LOSS HIT"),
            "WAIT":        ("#4a6fa5", "⏳ WAIT / NO SIGNAL"),
        }
        col, label = col_map.get(action, ("#4a6fa5", action))
        conf_badge = {
            "HIGH":   "🔥 HIGH confidence",
            "MEDIUM": "⚡ MEDIUM confidence",
            "LOW":    "🌀 LOW confidence",
        }.get(setup.confidence, "")

        with st.expander(f"{label}   ·   **{strat_name}**   {conf_badge}", expanded=(action not in ("WAIT",))):
            strategy_obj = ALL_STRATEGIES.get(strat_name)
            if strategy_obj:
                st.caption(strategy_obj.description)

            # Main action display
            if action in ("ENTER_LONG", "ENTER_SHORT"):
                direction = "LONG" if action == "ENTER_LONG" else "SHORT"
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Entry",    f"₹{setup.entry_price:,.2f}")
                c2.metric("Stop Loss",f"₹{setup.stop_loss:,.2f}",
                          delta=f"-{setup.sl_pct:.1f}%",
                          delta_color="inverse")
                c3.metric("Target 1", f"₹{setup.target_1:,.2f}")
                c4.metric("Target 2", f"₹{setup.target_2:,.2f}")

                c5, c6, c7, c8 = st.columns(4)
                c5.metric("Target 3", f"₹{setup.target_3:,.2f}")
                c6.metric("R:R Ratio", f"1 : {setup.rr_ratio:.1f}")
                c7.metric("Risk/Lot",  f"₹{setup.risk_per_lot:,.0f}")
                c8.metric("Option",    f"{setup.option_type} @ {setup.suggested_strike:.0f}")

                # Risk bar
                pct_sl  = setup.sl_pct
                pct_t1  = round(abs(setup.target_1 - setup.entry_price) / setup.entry_price * 100, 2) if setup.entry_price else 0
                pct_t2  = round(abs(setup.target_2 - setup.entry_price) / setup.entry_price * 100, 2) if setup.entry_price else 0
                st.markdown(f"""
                <div style='margin:10px 0 4px;font-size:.75rem;color:#4a6fa5;'>Risk vs Reward</div>
                <div style='display:flex;gap:4px;height:10px;border-radius:5px;overflow:hidden;'>
                  <div style='width:{pct_sl * 10}%;background:#f87171;border-radius:5px 0 0 5px;' title='SL {pct_sl}%'></div>
                  <div style='width:{pct_t1 * 8}%;background:#f59e0b;' title='T1 +{pct_t1}%'></div>
                  <div style='width:{pct_t2 * 6}%;background:#00d4aa;border-radius:0 5px 5px 0;' title='T2 +{pct_t2}%'></div>
                </div>
                <div style='display:flex;justify-content:space-between;font-size:.68rem;color:#4a6fa5;margin-top:2px;'>
                  <span>SL -{pct_sl:.1f}%</span><span>T1 +{pct_t1:.1f}%</span><span>T2 +{pct_t2:.1f}%</span>
                </div>
                """, unsafe_allow_html=True)

                # Reasons
                if setup.reasons:
                    st.markdown("**Entry reasons:**")
                    for r in setup.reasons:
                        st.markdown(f"✅ {r}")
                if setup.warnings:
                    for w in setup.warnings:
                        st.warning(f"⚠️ {w}")

                # Trade activation button
                st.markdown("---")
                btn_col1, btn_col2 = st.columns([1,2])
                with btn_col1:
                    if st.button(f"✅ Mark as Active Trade", key=f"activate_{strat_name}"):
                        st.session_state.active_trades[strat_name] = {
                            "strategy":    strat_name,
                            "direction":   direction,
                            "entry_price": setup.entry_price,
                            "stop_loss":   setup.stop_loss,
                            "trailing_sl": setup.stop_loss,
                            "target_1":    setup.target_1,
                            "target_2":    setup.target_2,
                            "target_3":    setup.target_3,
                            "option_type": setup.option_type,
                            "entry_time":  datetime.now().strftime("%H:%M IST"),
                        }
                        add_alert(action.split("_")[0],
                                  f"{strat_name}: {direction} @ {setup.entry_price:.0f} SL {setup.stop_loss:.0f} T2 {setup.target_2:.0f}")
                        st.success(f"Trade activated! Monitoring for exit/SL signals.")
                        st.rerun()

            elif action == "HOLD":
                if setup.in_trade:
                    pnl = setup.current_pnl_pct
                    pnl_col = "#00d4aa" if pnl >= 0 else "#f87171"
                    mile = setup.milestone_hit

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Entry",     f"₹{active_trades.get(strat_name, {}).get('entry_price', 0):,.0f}")
                    c2.metric("Curr P&L",  f"{pnl:+.2f}%",
                              delta=f"{'🎯 ' + mile.replace('_',' ') if mile else ''}",
                              delta_color="normal" if pnl >= 0 else "inverse")
                    c3.metric("Stop Loss", f"₹{setup.stop_loss:,.0f}")
                    c4.metric("Trail SL",  f"₹{setup.trailing_sl:,.0f}" if setup.trailing_sl else "—")

                    t_col1, t_col2, t_col3 = st.columns(3)
                    t_col1.metric("T1", f"₹{setup.target_1:,.0f}")
                    t_col2.metric("T2", f"₹{setup.target_2:,.0f}")
                    t_col3.metric("T3", f"₹{setup.target_3:,.0f}")

                    if mile:
                        mile_col = "#00d4aa" if "T3" in mile else "#f59e0b" if "T2" in mile else "#60a5fa"
                        st.markdown(f"""
                        <div style='background:{mile_col}22;border:1px solid {mile_col}55;border-radius:7px;
                             padding:8px 14px;margin:8px 0;font-size:.82rem;color:{mile_col};font-weight:700;'>
                          🎯 {mile.replace("_", " ")} — {'Consider partial exit / move SL to entry' if mile == 'T1_HIT' else 'Activate trailing SL' if mile == 'T2_HIT' else 'Full exit recommended'}
                        </div>
                        """, unsafe_allow_html=True)

                for r in (setup.hold_reasons or []):
                    st.markdown(f"⏸ {r}")

                if setup.in_trade:
                    if st.button(f"🚪 Close Trade (Manual Exit)", key=f"close_{strat_name}"):
                        at = st.session_state.active_trades.pop(strat_name, {})
                        add_alert("INFO", f"{strat_name}: Manual exit @ entry {at.get('entry_price',0):.0f}")
                        st.success("Trade closed.")
                        st.rerun()

            elif action in ("EXIT_LONG", "EXIT_SHORT"):
                direction = "LONG" if action == "EXIT_LONG" else "SHORT"
                pnl = setup.current_pnl_pct
                pnl_col = "#00d4aa" if pnl >= 0 else "#f87171"

                st.markdown(f"""
                <div style='background:#60a5fa18;border:1px solid #60a5fa55;border-radius:8px;
                     padding:12px;margin-bottom:8px;'>
                  <span style='font-size:1.1rem;font-weight:700;color:#60a5fa;'>EXIT {direction}</span>
                  <span style='font-size:.9rem;color:{pnl_col};margin-left:12px;'>P&L: {pnl:+.2f}%</span>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("**Exit reasons:**")
                for r in (setup.exit_reasons or []):
                    st.markdown(f"🔵 {r}")

                if st.button(f"✅ Confirm Exit", key=f"exit_{strat_name}"):
                    at = st.session_state.active_trades.pop(strat_name, {})
                    add_alert("INFO", f"{strat_name}: EXIT {direction} — P&L {pnl:+.2f}%")
                    st.success(f"Trade exited. P&L: {pnl:+.2f}%")
                    st.rerun()

            elif action == "STOP_LOSS":
                pnl = setup.current_pnl_pct
                st.markdown(f"""
                <div style='background:#ef444422;border:2px solid #ef4444;border-radius:8px;
                     padding:14px;margin-bottom:8px;'>
                  <div style='font-size:1.3rem;font-weight:800;color:#ef4444;'>🚨 STOP LOSS HIT</div>
                  <div style='font-size:.85rem;color:#f87171;margin-top:4px;'>Loss: {pnl:+.2f}% — Exit immediately to limit further damage</div>
                </div>
                """, unsafe_allow_html=True)

                for r in (setup.sl_reasons or []):
                    st.error(r)

                if st.button(f"🚨 Confirm SL Exit", key=f"sl_{strat_name}",
                             type="primary"):
                    at = st.session_state.active_trades.pop(strat_name, {})
                    add_alert("SELL", f"{strat_name}: STOP LOSS — Loss {pnl:+.2f}%")
                    st.error(f"SL exit confirmed. Loss: {pnl:+.2f}%")
                    st.rerun()

            else:  # WAIT
                for r in (setup.hold_reasons or ["No setup forming — stand aside"]):
                    st.caption(f"⏳ {r}")

    # ── ACTIVE TRADES SUMMARY ─────────────────────────────────────────────
    if active_trades:
        st.divider()
        st.markdown("### 🗂️ Active Trades")
        for strat, trade in list(active_trades.items()):
            close = result.get("candles", [{}])[-1].get("c", 0) if result else 0
            entry = trade.get("entry_price", close)
            direction = trade.get("direction", "LONG")
            pnl = ((close - entry) / entry * 100) if direction == "LONG" and entry else ((entry - close) / entry * 100) if entry else 0
            pnl_col = "#00d4aa" if pnl >= 0 else "#f87171"
            st.markdown(f"""
            <div style='background:#0d1525;border:0.5px solid #1e3050;border-radius:8px;
                 padding:10px 14px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;'>
              <div>
                <span style='font-weight:700;color:#e2e8f0;'>{strat}</span>
                <span style='color:#4a6fa5;font-size:.75rem;margin-left:8px;'>{direction} · Entry {entry:.0f} · SL {trade.get("stop_loss",0):.0f}</span>
              </div>
              <div style='font-weight:700;font-size:1rem;color:{pnl_col};'>{pnl:+.2f}%</div>
            </div>
            """, unsafe_allow_html=True)


# ─── STRATEGY CONFIG TAB ─────────────────────────────────────────────────────
def show_strategy_config_tab():
    st.markdown("### ⚙️ Strategy Configuration")
    st.caption("Customise parameters for each strategy. Changes apply immediately on next signal check.")

    config = st.session_state.get("strategy_config", {})

    with st.expander("🔧 Global Risk Settings", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            sl_atr = st.slider("SL ATR Multiplier", 0.5, 3.0,
                                float(config.get("sl_atr_mult", 1.5)), 0.1,
                                help="Stop Loss = entry ± (ATR × this value). Higher = wider SL, fewer stops.")
        with c2:
            t2_rr = st.slider("Target 2 RR", 1.5, 5.0,
                               float(config.get("t2_rr", 2.5)), 0.5,
                               help="Risk:Reward for Target 2. 2.5 means gain = 2.5× your risk.")
        with c3:
            t3_rr = st.slider("Target 3 RR", 2.0, 8.0,
                               float(config.get("t3_rr", 4.0)), 0.5,
                               help="Risk:Reward for Target 3 (runner / trail).")
        config["sl_atr_mult"] = sl_atr
        config["t2_rr"]       = t2_rr
        config["t3_rr"]       = t3_rr
        config["t1_rr"]       = round(t2_rr * 0.6, 1)

    with st.expander("📊 EMA Trend Follow Settings"):
        c1, c2 = st.columns(2)
        with c1:
            min_score = st.slider("Min Signal Score to Enter", 20, 70,
                                   int(config.get("min_score", 30)), 5,
                                   help="Higher = stricter entry filter, fewer but better signals.")
        with c2:
            st.markdown(f"""
            <div style='background:#0d1525;border-radius:6px;padding:10px;margin-top:4px;font-size:.8rem;'>
            <b style='color:#00d4aa;'>Entry rule:</b><br>
            EMA9 × EMA21 cross OR score ≥ {min_score}<br>
            + MACD histogram positive<br>
            + Price above VWAP
            </div>""", unsafe_allow_html=True)
        config["min_score"] = min_score

    with st.expander("📉 RSI Mean Reversion Settings"):
        c1, c2 = st.columns(2)
        with c1:
            rsi_os = st.slider("RSI Oversold threshold", 20, 40,
                                int(config.get("rsi_os", 30)), 1,
                                help="Buy signal fires when RSI drops below this.")
        with c2:
            rsi_ob = st.slider("RSI Overbought threshold", 60, 80,
                                int(config.get("rsi_ob", 70)), 1,
                                help="Sell signal fires when RSI rises above this.")
        config["rsi_os"] = rsi_os
        config["rsi_ob"] = rsi_ob

    with st.expander("🎯 Multi-Confluence Settings"):
        min_conf = st.slider("Minimum Confluences Required", 2, 6,
                              int(config.get("min_confluences", 4)), 1,
                              help="How many independent signals must agree before entering. Higher = rarer but higher quality trades.")
        config["min_confluences"] = min_conf
        st.caption(f"Currently requires **{min_conf} out of 6** signals to align: EMA Stack, MACD, RSI, VWAP, BB, Candle Pattern")

    # Save button
    if st.button("💾 Save Configuration", type="primary", use_container_width=True):
        st.session_state.strategy_config = config
        st.success("✅ Configuration saved! Will apply on next signal refresh.")

    st.divider()

    # Strategy cheatsheet
    st.markdown("### 📚 Strategy Guide")
    guide = {
        "EMA Trend Follow": {
            "best_for": "Trending markets (strong up or down move)",
            "avoid":    "Sideways / range-bound days",
            "signal":   "EMA9 × EMA21 cross + MACD + VWAP",
            "sl_style": "ATR-based below swing low",
        },
        "RSI Mean Reversion": {
            "best_for": "Range-bound, consolidating markets",
            "avoid":    "Strong trending days (RSI stays extreme)",
            "signal":   "RSI oversold/overbought + BB band touch + reversal candle",
            "sl_style": "Below/above the candle low/high that triggered",
        },
        "MACD Momentum": {
            "best_for": "Breakout days, high volatility",
            "avoid":    "Low volume, choppy markets",
            "signal":   "MACD line × signal line cross + histogram expansion",
            "sl_style": "Wide ATR SL — momentum trades need room",
        },
        "VWAP Reversal": {
            "best_for": "Intraday scalps around VWAP level",
            "avoid":    "Pre-market / first 15 min (VWAP unreliable)",
            "signal":   "Price reclaims or rejects VWAP + volume + candle",
            "sl_style": "Tight — just beyond VWAP level",
        },
        "Multi-Confluence": {
            "best_for": "Any market — highest accuracy, fewest signals",
            "avoid":    "When impatient — may wait all day for a setup",
            "signal":   "4+ of: EMA, RSI, MACD, VWAP, BB, Pattern all agree",
            "sl_style": "ATR × 1.8 — widest, for highest conviction trades",
        },
    }
    for name, g in guide.items():
        with st.expander(f"📖 {name}"):
            gc1, gc2 = st.columns(2)
            with gc1:
                st.markdown(f"✅ **Best for:** {g['best_for']}")
                st.markdown(f"❌ **Avoid when:** {g['avoid']}")
            with gc2:
                st.markdown(f"⚡ **Signal:** {g['signal']}")
                st.markdown(f"🛑 **Stop Loss:** {g['sl_style']}")

    st.divider()
    st.markdown("### 🗑️ Clear Active Trades")
    if st.button("Clear All Active Trades", type="secondary"):
        st.session_state.active_trades = {}
        st.success("All active trades cleared.")
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════
if st.session_state.authenticated:
    show_dashboard()
else:
    show_login()
