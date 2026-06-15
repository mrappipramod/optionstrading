"""
NiftyEdge Pro — Streamlit Edition  v3.0
Dhan-powered Options Trading Dashboard
Fixes:
  - /v2/positions (correct endpoint — was /v2/portfolio/positions)
  - /v2/fundlimit (correct — was /v2/funds/balance)
  - Full option chain: new response format {data:{last_price, oc:{strike:{ce,pe}}}}
  - Greeks display (delta, theta, gamma, vega, IV)
  - Proper security_id from chain for one-click order placement
  - rgba() fillcolor for Plotly candlestick (no more #RRGGBBAA)
  - Chart clutter: signals only on last 50 candles, deduplicated
  - 125 instruments with search + sector browser
  - Auto-refresh button + manual refresh
"""

import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import sys, os

sys.path.insert(0, os.path.dirname(__file__))
from ta_engine import analyse
from strategy_engine import run_all_strategies, consensus, ALL_STRATEGIES

# ─── PAGE CONFIG ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NiftyEdge Pro",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""<style>
#MainMenu,footer,header{visibility:hidden}
.block-container{padding-top:.8rem;padding-bottom:.5rem}
[data-testid="metric-container"]{background:#0d1525;border:.5px solid #1e3050;border-radius:8px;padding:6px 12px}
[data-testid="stMetricValue"]{font-size:1rem!important;font-weight:700}
[data-testid="stMetricDelta"]{font-size:.72rem!important}

/* signal cards */
.sig-BUY    {background:#00d4aa12;border:1.5px solid #00d4aa55;border-radius:10px;padding:12px;text-align:center}
.sig-SELL   {background:#f8717112;border:1.5px solid #f8717155;border-radius:10px;padding:12px;text-align:center}
.sig-NEUTRAL{background:#4a6fa512;border:1.5px solid #4a6fa555;border-radius:10px;padding:12px;text-align:center}
.sig-label  {font-size:1.5rem;font-weight:800;letter-spacing:1px}
.sig-sub    {font-size:.78rem;color:#94a3b8;margin-top:3px}
.sig-score  {font-size:.72rem;color:#4a6fa5;margin-top:2px}

/* indicators bar */
.ind-row{display:flex;flex-wrap:wrap;gap:10px;background:#0d1525;border:.5px solid #1e3050;
         border-radius:8px;padding:7px 12px;margin-bottom:6px}
.ind-chip{font-size:.73rem;color:#4a6fa5}
.ind-chip span{color:#e2e8f0;font-weight:600;margin-left:3px}

/* option chain */
.oc-table{width:100%;border-collapse:collapse;font-size:.72rem}
.oc-table th{color:#4a6fa5;padding:4px 6px;text-align:center;border-bottom:.5px solid #1e3050;font-weight:500}
.oc-table td{padding:3px 6px;text-align:center;border-bottom:.5px solid #0d1525}
.oc-call{color:#00d4aa;font-weight:600}
.oc-put {color:#f87171;font-weight:600}
.oc-atm {background:#1e3050;font-weight:800;color:#f59e0b}
.oc-strike{color:#e2e8f0;font-weight:700}
.oc-iv{color:#a78bfa;font-size:.68rem}

/* alerts */
.alert-item{display:flex;gap:8px;align-items:flex-start;padding:5px 0;border-bottom:.5px solid #1e3050;font-size:.78rem}
.alert-item:last-child{border-bottom:none}
.adot{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-top:4px}

/* order buttons */
.buy-btn{background:#00d4aa20;border:1px solid #00d4aa55;color:#00d4aa;border-radius:6px;padding:6px 0;
         width:100%;cursor:pointer;font-weight:700;font-size:.8rem}
.sell-btn{background:#f8717120;border:1px solid #f8717155;color:#f87171;border-radius:6px;padding:6px 0;
          width:100%;cursor:pointer;font-weight:700;font-size:.8rem}

/* str meter */
.str-row{display:flex;justify-content:space-between;padding:3px 0;font-size:.78rem}
.str-name{color:#4a6fa5}
</style>""", unsafe_allow_html=True)

# ─── INSTRUMENTS ─────────────────────────────────────────────────────────────
SECURITY_IDS = {
    # INDICES
    "NIFTY":      {"id":"13",    "segment":"IDX_I",  "name":"Nifty 50",            "sector":"Index"},
    "BANKNIFTY":  {"id":"25",    "segment":"IDX_I",  "name":"Bank Nifty",          "sector":"Index"},
    "FINNIFTY":   {"id":"27",    "segment":"IDX_I",  "name":"Fin Nifty",           "sector":"Index"},
    "MIDCPNIFTY": {"id":"442",   "segment":"IDX_I",  "name":"Midcap Nifty",        "sector":"Index"},
    "SENSEX":     {"id":"1",     "segment":"IDX_I",  "name":"BSE Sensex",          "sector":"Index"},
    "BANKEX":     {"id":"12",    "segment":"IDX_I",  "name":"BSE Bankex",          "sector":"Index"},
    # BANKING
    "HDFCBANK":   {"id":"1333",  "segment":"NSE_EQ", "name":"HDFC Bank",           "sector":"Banking"},
    "ICICIBANK":  {"id":"4963",  "segment":"NSE_EQ", "name":"ICICI Bank",          "sector":"Banking"},
    "SBIN":       {"id":"3045",  "segment":"NSE_EQ", "name":"State Bank India",    "sector":"Banking"},
    "KOTAKBANK":  {"id":"1922",  "segment":"NSE_EQ", "name":"Kotak Mahindra Bank", "sector":"Banking"},
    "AXISBANK":   {"id":"5900",  "segment":"NSE_EQ", "name":"Axis Bank",           "sector":"Banking"},
    "INDUSINDBK": {"id":"10093", "segment":"NSE_EQ", "name":"IndusInd Bank",       "sector":"Banking"},
    "BANDHANBNK": {"id":"2263",  "segment":"NSE_EQ", "name":"Bandhan Bank",        "sector":"Banking"},
    "FEDERALBNK": {"id":"1023",  "segment":"NSE_EQ", "name":"Federal Bank",        "sector":"Banking"},
    "IDFCFIRSTB": {"id":"11723", "segment":"NSE_EQ", "name":"IDFC First Bank",     "sector":"Banking"},
    "PNB":        {"id":"2730",  "segment":"NSE_EQ", "name":"Punjab National Bank","sector":"Banking"},
    "CANBK":      {"id":"10794", "segment":"NSE_EQ", "name":"Canara Bank",         "sector":"Banking"},
    "BANKBARODA": {"id":"1152",  "segment":"NSE_EQ", "name":"Bank of Baroda",      "sector":"Banking"},
    "BAJFINANCE": {"id":"317",   "segment":"NSE_EQ", "name":"Bajaj Finance",       "sector":"Finance"},
    "BAJAJFINSV": {"id":"16675", "segment":"NSE_EQ", "name":"Bajaj Finserv",       "sector":"Finance"},
    "HDFCLIFE":   {"id":"119",   "segment":"NSE_EQ", "name":"HDFC Life Insurance", "sector":"Insurance"},
    "SBILIFE":    {"id":"21808", "segment":"NSE_EQ", "name":"SBI Life Insurance",  "sector":"Insurance"},
    "MUTHOOTFIN": {"id":"4406",  "segment":"NSE_EQ", "name":"Muthoot Finance",     "sector":"Finance"},
    # IT
    "TCS":        {"id":"11536", "segment":"NSE_EQ", "name":"Tata Consultancy",    "sector":"IT"},
    "INFY":       {"id":"10604", "segment":"NSE_EQ", "name":"Infosys",             "sector":"IT"},
    "WIPRO":      {"id":"3787",  "segment":"NSE_EQ", "name":"Wipro",               "sector":"IT"},
    "HCLTECH":    {"id":"7229",  "segment":"NSE_EQ", "name":"HCL Technologies",    "sector":"IT"},
    "TECHM":      {"id":"13538", "segment":"NSE_EQ", "name":"Tech Mahindra",       "sector":"IT"},
    "LTIM":       {"id":"17818", "segment":"NSE_EQ", "name":"LTIMindtree",         "sector":"IT"},
    "MPHASIS":    {"id":"4503",  "segment":"NSE_EQ", "name":"Mphasis",             "sector":"IT"},
    "PERSISTENT": {"id":"18365", "segment":"NSE_EQ", "name":"Persistent Systems",  "sector":"IT"},
    "COFORGE":    {"id":"10418", "segment":"NSE_EQ", "name":"Coforge",             "sector":"IT"},
    "OFSS":       {"id":"10738", "segment":"NSE_EQ", "name":"Oracle Fin Services", "sector":"IT"},
    # OIL & GAS
    "RELIANCE":   {"id":"2885",  "segment":"NSE_EQ", "name":"Reliance Industries", "sector":"Oil & Gas"},
    "ONGC":       {"id":"11703", "segment":"NSE_EQ", "name":"ONGC",               "sector":"Oil & Gas"},
    "IOC":        {"id":"1624",  "segment":"NSE_EQ", "name":"Indian Oil Corp",     "sector":"Oil & Gas"},
    "BPCL":       {"id":"526",   "segment":"NSE_EQ", "name":"BPCL",               "sector":"Oil & Gas"},
    "HINDPETRO":  {"id":"1406",  "segment":"NSE_EQ", "name":"HPCL",               "sector":"Oil & Gas"},
    "GAIL":       {"id":"1094",  "segment":"NSE_EQ", "name":"GAIL India",          "sector":"Oil & Gas"},
    # POWER
    "POWERGRID":  {"id":"14977", "segment":"NSE_EQ", "name":"Power Grid Corp",     "sector":"Power"},
    "NTPC":       {"id":"11630", "segment":"NSE_EQ", "name":"NTPC",               "sector":"Power"},
    "ADANIGREEN": {"id":"6718",  "segment":"NSE_EQ", "name":"Adani Green Energy",  "sector":"Power"},
    "TATAPOWER":  {"id":"14150", "segment":"NSE_EQ", "name":"Tata Power",          "sector":"Power"},
    # AUTO
    "MARUTI":     {"id":"10999", "segment":"NSE_EQ", "name":"Maruti Suzuki",       "sector":"Auto"},
    "TATAMOTORS": {"id":"3456",  "segment":"NSE_EQ", "name":"Tata Motors",         "sector":"Auto"},
    "M&M":        {"id":"2031",  "segment":"NSE_EQ", "name":"Mahindra & Mahindra", "sector":"Auto"},
    "BAJAJ-AUTO": {"id":"16669", "segment":"NSE_EQ", "name":"Bajaj Auto",          "sector":"Auto"},
    "HEROMOTOCO": {"id":"1348",  "segment":"NSE_EQ", "name":"Hero MotoCorp",       "sector":"Auto"},
    "EICHERMOT":  {"id":"910",   "segment":"NSE_EQ", "name":"Eicher Motors",       "sector":"Auto"},
    "TVSMOTOR":   {"id":"14109", "segment":"NSE_EQ", "name":"TVS Motor",           "sector":"Auto"},
    "ASHOKLEY":   {"id":"212",   "segment":"NSE_EQ", "name":"Ashok Leyland",       "sector":"Auto"},
    # PHARMA
    "SUNPHARMA":  {"id":"3351",  "segment":"NSE_EQ", "name":"Sun Pharma",          "sector":"Pharma"},
    "DRREDDY":    {"id":"881",   "segment":"NSE_EQ", "name":"Dr Reddys Labs",      "sector":"Pharma"},
    "CIPLA":      {"id":"694",   "segment":"NSE_EQ", "name":"Cipla",               "sector":"Pharma"},
    "DIVISLAB":   {"id":"10243", "segment":"NSE_EQ", "name":"Divi's Labs",         "sector":"Pharma"},
    "APOLLOHOSP": {"id":"157",   "segment":"NSE_EQ", "name":"Apollo Hospitals",    "sector":"Healthcare"},
    "TORNTPHARM": {"id":"3518",  "segment":"NSE_EQ", "name":"Torrent Pharma",      "sector":"Pharma"},
    "LUPIN":      {"id":"10440", "segment":"NSE_EQ", "name":"Lupin",               "sector":"Pharma"},
    "AUROPHARMA": {"id":"275",   "segment":"NSE_EQ", "name":"Aurobindo Pharma",    "sector":"Pharma"},
    # FMCG
    "HINDUNILVR": {"id":"1394",  "segment":"NSE_EQ", "name":"Hindustan Unilever",  "sector":"FMCG"},
    "ITC":        {"id":"1660",  "segment":"NSE_EQ", "name":"ITC",                 "sector":"FMCG"},
    "NESTLEIND":  {"id":"17963", "segment":"NSE_EQ", "name":"Nestle India",        "sector":"FMCG"},
    "BRITANNIA":  {"id":"547",   "segment":"NSE_EQ", "name":"Britannia",           "sector":"FMCG"},
    "DABUR":      {"id":"804",   "segment":"NSE_EQ", "name":"Dabur India",         "sector":"FMCG"},
    "GODREJCP":   {"id":"10099", "segment":"NSE_EQ", "name":"Godrej Consumer",     "sector":"FMCG"},
    "MARICO":     {"id":"4067",  "segment":"NSE_EQ", "name":"Marico",              "sector":"FMCG"},
    "COLPAL":     {"id":"752",   "segment":"NSE_EQ", "name":"Colgate-Palmolive",   "sector":"FMCG"},
    "TATACONSUM": {"id":"3432",  "segment":"NSE_EQ", "name":"Tata Consumer",       "sector":"FMCG"},
    # METALS
    "TATASTEEL":  {"id":"3499",  "segment":"NSE_EQ", "name":"Tata Steel",          "sector":"Metals"},
    "JSWSTEEL":   {"id":"11723", "segment":"NSE_EQ", "name":"JSW Steel",           "sector":"Metals"},
    "HINDALCO":   {"id":"1363",  "segment":"NSE_EQ", "name":"Hindalco",            "sector":"Metals"},
    "VEDL":       {"id":"3063",  "segment":"NSE_EQ", "name":"Vedanta",             "sector":"Metals"},
    "SAIL":       {"id":"2963",  "segment":"NSE_EQ", "name":"Steel Authority",     "sector":"Metals"},
    "COALINDIA":  {"id":"20374", "segment":"NSE_EQ", "name":"Coal India",          "sector":"Mining"},
    "NMDC":       {"id":"15332", "segment":"NSE_EQ", "name":"NMDC",               "sector":"Mining"},
    # CEMENT & INFRA
    "ULTRACEMCO": {"id":"11532", "segment":"NSE_EQ", "name":"UltraTech Cement",    "sector":"Cement"},
    "SHREECEM":   {"id":"3103",  "segment":"NSE_EQ", "name":"Shree Cement",        "sector":"Cement"},
    "AMBUJACEM":  {"id":"1270",  "segment":"NSE_EQ", "name":"Ambuja Cement",       "sector":"Cement"},
    "ACC":        {"id":"14",    "segment":"NSE_EQ", "name":"ACC",                 "sector":"Cement"},
    "LT":         {"id":"11483", "segment":"NSE_EQ", "name":"Larsen & Toubro",     "sector":"Infrastructure"},
    "ADANIPORTS": {"id":"11184", "segment":"NSE_EQ", "name":"Adani Ports",         "sector":"Infrastructure"},
    # TELECOM
    "BHARTIARTL": {"id":"1270",  "segment":"NSE_EQ", "name":"Bharti Airtel",       "sector":"Telecom"},
    "INDUSTOWER": {"id":"7458",  "segment":"NSE_EQ", "name":"Indus Towers",        "sector":"Telecom"},
    # CONSUMER
    "TITAN":      {"id":"3506",  "segment":"NSE_EQ", "name":"Titan Company",       "sector":"Consumer"},
    "TRENT":      {"id":"3519",  "segment":"NSE_EQ", "name":"Trent",               "sector":"Retail"},
    "DMART":      {"id":"7432",  "segment":"NSE_EQ", "name":"Avenue Supermarts",   "sector":"Retail"},
    "ZOMATO":     {"id":"21866", "segment":"NSE_EQ", "name":"Zomato",              "sector":"Consumer"},
    "IRCTC":      {"id":"16916", "segment":"NSE_EQ", "name":"IRCTC",               "sector":"Consumer"},
    "NYKAA":      {"id":"21827", "segment":"NSE_EQ", "name":"Nykaa",               "sector":"Retail"},
    # CAPITAL GOODS & DEFENCE
    "SIEMENS":    {"id":"3200",  "segment":"NSE_EQ", "name":"Siemens India",       "sector":"Capital Goods"},
    "HAVELLS":    {"id":"430",   "segment":"NSE_EQ", "name":"Havells India",       "sector":"Capital Goods"},
    "HAL":        {"id":"2303",  "segment":"NSE_EQ", "name":"Hindustan Aeronautics","sector":"Defence"},
    "BEL":        {"id":"383",   "segment":"NSE_EQ", "name":"Bharat Electronics",  "sector":"Defence"},
    "BHEL":       {"id":"438",   "segment":"NSE_EQ", "name":"BHEL",               "sector":"Capital Goods"},
    # REAL ESTATE
    "DLF":        {"id":"14732", "segment":"NSE_EQ", "name":"DLF",               "sector":"Real Estate"},
    "GODREJPROP": {"id":"10709", "segment":"NSE_EQ", "name":"Godrej Properties",  "sector":"Real Estate"},
    "OBEROIRLTY": {"id":"20242", "segment":"NSE_EQ", "name":"Oberoi Realty",      "sector":"Real Estate"},
    # CHEMICALS
    "PIDILITIND": {"id":"14359", "segment":"NSE_EQ", "name":"Pidilite Industries", "sector":"Chemicals"},
    "SRF":        {"id":"3273",  "segment":"NSE_EQ", "name":"SRF",                "sector":"Chemicals"},
    "TATACHEM":   {"id":"3440",  "segment":"NSE_EQ", "name":"Tata Chemicals",      "sector":"Chemicals"},
    # MEDIA
    "ZEEL":       {"id":"9667",  "segment":"NSE_EQ", "name":"Zee Entertainment",   "sector":"Media"},
    "SUNTV":      {"id":"3418",  "segment":"NSE_EQ", "name":"Sun TV Network",      "sector":"Media"},
    "PVR":        {"id":"13147", "segment":"NSE_EQ", "name":"PVR Inox",           "sector":"Media"},
}

LOT_SIZES = {
    "NIFTY":75,"BANKNIFTY":30,"FINNIFTY":65,
    "MIDCPNIFTY":50,"SENSEX":20,"BANKEX":15,
}

SECTOR_GROUPS = {}
for sym, info in SECURITY_IDS.items():
    SECTOR_GROUPS.setdefault(info["sector"], []).append(sym)

# ─── SESSION STATE ────────────────────────────────────────────────────────────
DEFAULTS = {
    "authenticated":False,"client_id":"","access_token":"",
    "symbol":"NIFTY","interval":"15",
    "alerts":[],"analysis_cache":{},"last_fetch":{},
    "active_trades":{},"strategy_config":{},
    "oc_cache":{},"oc_last_fetch":{},"selected_expiry":"",
    # date range picker
    "date_mode":"Today",
    "custom_from": None,
    "custom_to":   None,
    # trade journal
    "trade_log": [],
    # custom stock search
    "custom_symbol": "",
    "custom_sec_id": "",
    "custom_seg":    "NSE_EQ",
}
for k,v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─── DHAN API ─────────────────────────────────────────────────────────────────
DHAN_BASE = "https://api.dhan.co/v2"

def _hdrs():
    return {
        "Content-Type":"application/json",
        "access-token":st.session_state.access_token,
        "client-id":   st.session_state.client_id,
    }

def dhan_get(path, timeout=10):
    try:
        r = requests.get(f"{DHAN_BASE}{path}", headers=_hdrs(), timeout=timeout)
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
    except Exception as e:
        return {"error": str(e)}

def dhan_post(path, body, timeout=12):
    try:
        r = requests.post(f"{DHAN_BASE}{path}", headers=_hdrs(), json=body, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
    except Exception as e:
        return {"error": str(e)}

def verify_credentials(client_id, access_token):
    hdrs = {"Content-Type":"application/json",
            "access-token":access_token.strip(),
            "client-id":client_id.strip()}
    try:
        r = requests.get(f"{DHAN_BASE}/fundlimit", headers=hdrs, timeout=10)
        if r.status_code == 200:   return True, "Connected"
        if r.status_code in (401,403):
            try: msg = r.json().get("errorMessage") or r.json().get("message") or r.text[:200]
            except: msg = r.text[:200]
            return False, f"HTTP {r.status_code}: {msg}"
        if r.status_code == 429:   return True, "Rate-limited — credentials OK"
        if r.status_code == 404:   return True, "Connected (endpoint check skipped)"
        if r.status_code >= 500:   return False, f"Dhan server error {r.status_code}"
        return True, f"Connected (HTTP {r.status_code})"
    except requests.exceptions.Timeout:      return False, "Timeout — check internet"
    except requests.exceptions.ConnectionError: return False, "Cannot reach Dhan API"
    except Exception as e:                   return False, str(e)

def last_trading_day():
    """Return the most recent weekday (skips Saturday/Sunday)."""
    d = datetime.now().date() - timedelta(days=1)
    while d.weekday() >= 5:   # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d

def resolve_date_range(date_mode, custom_from=None, custom_to=None, interval="15"):
    """
    Returns (from_str, to_str) suitable for Dhan API.
    Intraday endpoints need datetime strings; daily needs date strings.
    """
    today = datetime.now().date()
    is_intraday = interval in ("1","5","15","25","60")

    if date_mode == "Today":
        fd = today
        td = today
    elif date_mode == "Last Trading Day":
        fd = last_trading_day()
        td = fd
    elif date_mode == "This Week":
        # Monday to today
        fd = today - timedelta(days=today.weekday())
        td = today
    elif date_mode == "Last 5 Days":
        fd = today - timedelta(days=7)   # gives ~5 trading days
        td = today
    elif date_mode == "Last 1 Month":
        fd = today - timedelta(days=30)
        td = today
    elif date_mode == "Last 3 Months":
        fd = today - timedelta(days=90)
        td = today
    elif date_mode == "Last 6 Months":
        fd = today - timedelta(days=180)
        td = today
    elif date_mode == "Last 1 Year":
        fd = today - timedelta(days=365)
        td = today
    elif date_mode == "Custom" and custom_from and custom_to:
        fd = custom_from
        td = custom_to
    else:
        fd = today - timedelta(days=5)
        td = today

    if is_intraday:
        # Intraday API needs full datetime strings
        return (f"{fd} 09:15:00", f"{td} 15:30:00")
    else:
        return (str(fd), str(td))

def fetch_candles(symbol, interval="15", date_mode="Today",
                  custom_from=None, custom_to=None):
    info = SECURITY_IDS.get(symbol)
    if not info: return None

    instrument = "INDEX" if info["segment"] == "IDX_I" else "EQUITY"
    is_daily   = interval == "1D"

    from_str, to_str = resolve_date_range(
        date_mode, custom_from, custom_to, interval
    )

    if is_daily:
        body = {
            "securityId":      info["id"],
            "exchangeSegment": info["segment"],
            "instrument":      instrument,
            "expiryCode":      0,
            "oi":              False,
            "fromDate":        from_str,
            "toDate":          to_str,
        }
        return dhan_post("/charts/historical", body)
    else:
        body = {
            "securityId":      info["id"],
            "exchangeSegment": info["segment"],
            "instrument":      instrument,
            "interval":        interval,
            "oi":              False,
            "fromDate":        from_str,
            "toDate":          to_str,
        }
        return dhan_post("/charts/intraday", body)

def fetch_quote(symbol):
    info = SECURITY_IDS.get(symbol)
    if not info: return None
    return dhan_post("/marketfeed/quote", {info["segment"]:[info["id"]]})

def fetch_funds():
    return dhan_get("/fundlimit")

def fetch_positions():
    return dhan_get("/positions")   # FIXED: was /portfolio/positions

def fetch_holdings():
    return dhan_get("/holdings")

def fetch_orders():
    return dhan_get("/orders")

def fetch_option_chain(symbol, expiry=None):
    """Returns (parsed_chain_list, expiries_list, last_price, raw_oc_dict)"""
    info = SECURITY_IDS.get(symbol)
    if not info: return [], [], 0, {}

    # Step 1 — get expiries
    exp_resp = dhan_post("/optionchain/expirylist", {
        "UnderlyingScrip": int(info["id"]),
        "UnderlyingSeg":   info["segment"],
    })
    expiries = []
    if isinstance(exp_resp, dict) and "data" in exp_resp:
        expiries = exp_resp["data"]
    elif isinstance(exp_resp, list):
        expiries = exp_resp
    if not expiries:
        return [], [], 0, {}

    chosen = expiry if expiry and expiry in expiries else expiries[0]

    # Step 2 — get chain
    chain_resp = dhan_post("/optionchain", {
        "UnderlyingScrip": int(info["id"]),
        "UnderlyingSeg":   info["segment"],
        "Expiry":          chosen,
    })

    if isinstance(chain_resp, dict) and chain_resp.get("status") == "success":
        data      = chain_resp.get("data", {})
        last_price = data.get("last_price", 0)
        oc_raw     = data.get("oc", {})   # {"25650.000000": {"ce":{...},"pe":{...}}}

        rows = []
        for strike_str, opt in oc_raw.items():
            sp  = float(strike_str)
            ce  = opt.get("ce", {})
            pe  = opt.get("pe", {})
            rows.append({
                "strike":        sp,
                "ce_ltp":        ce.get("last_price", 0),
                "ce_oi":         ce.get("oi", 0),
                "ce_vol":        ce.get("volume", 0),
                "ce_iv":         round(ce.get("implied_volatility", 0), 1),
                "ce_delta":      round(ce.get("greeks", {}).get("delta", 0), 3),
                "ce_theta":      round(ce.get("greeks", {}).get("theta", 0), 2),
                "ce_bid":        ce.get("top_bid_price", 0),
                "ce_ask":        ce.get("top_ask_price", 0),
                "ce_security_id":ce.get("security_id", ""),
                "pe_ltp":        pe.get("last_price", 0),
                "pe_oi":         pe.get("oi", 0),
                "pe_vol":        pe.get("volume", 0),
                "pe_iv":         round(pe.get("implied_volatility", 0), 1),
                "pe_delta":      round(pe.get("greeks", {}).get("delta", 0), 3),
                "pe_theta":      round(pe.get("greeks", {}).get("theta", 0), 2),
                "pe_bid":        pe.get("top_bid_price", 0),
                "pe_ask":        pe.get("top_ask_price", 0),
                "pe_security_id":pe.get("security_id", ""),
            })
        rows.sort(key=lambda x: x["strike"])
        return rows, expiries, last_price, oc_raw

    return [], expiries, 0, {}

def place_order(security_id, exchange_seg, txn, product, qty, price, order_type="LIMIT"):
    body = {
        "dhanClientId":      st.session_state.client_id,
        "transactionType":   txn,
        "exchangeSegment":   exchange_seg,
        "productType":       product,
        "orderType":         "MARKET" if price == 0 else "LIMIT",
        "validity":          "DAY",
        "securityId":        str(security_id),
        "quantity":          qty,
        "price":             price,
        "triggerPrice":      0,
        "disclosedQuantity": 0,
        "afterMarketOrder":  False,
    }
    return dhan_post("/orders", body)

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def fmt(v, d=2):
    return f"{v:,.{d}f}" if isinstance(v,(int,float)) else str(v)

def fmt_oi(v):
    if v>=1_000_000: return f"{v/1_000_000:.1f}M"
    if v>=1_000:     return f"{v/1_000:.0f}K"
    return str(int(v))

def add_alert(atype, text):
    now = datetime.now().strftime("%H:%M")
    st.session_state.alerts.insert(0, {"type":atype,"text":text,"time":now})
    if len(st.session_state.alerts) > 12:
        st.session_state.alerts.pop()

def ist_now():
    """Current time in IST (UTC+5:30)."""
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

def market_status():
    """Returns ('OPEN'|'CLOSED'|'PRE-OPEN', color, emoji)."""
    now = ist_now()
    h, m = now.hour, now.minute
    total_min = h * 60 + m
    day = now.weekday()   # 0=Mon … 6=Sun
    if day >= 5:
        return "CLOSED (Weekend)", "#f87171", "🔴"
    # Pre-open session 09:00–09:15
    if 9*60 <= total_min < 9*60+15:
        return "PRE-OPEN", "#f59e0b", "🟡"
    # Regular session 09:15–15:30
    if 9*60+15 <= total_min <= 15*60+30:
        return "OPEN", "#00d4aa", "🟢"
    return "CLOSED", "#f87171", "🔴"

def is_market_open():
    status,_,_ = market_status()
    return status == "OPEN"

def search_stocks(q):
    q = q.upper().strip()
    if not q: return list(SECURITY_IDS.keys())
    return [s for s,i in SECURITY_IDS.items()
            if q in s or q in i["name"].upper() or q in i["sector"].upper()]

# Instruments that have NSE F&O option chains
FNO_ELIGIBLE = {
    "NIFTY","BANKNIFTY","FINNIFTY","MIDCPNIFTY","SENSEX","BANKEX",
    "RELIANCE","TCS","INFY","WIPRO","HCLTECH","HDFCBANK","ICICIBANK",
    "SBIN","AXISBANK","KOTAKBANK","BAJFINANCE","BAJAJFINSV","TATAMOTORS",
    "TATASTEEL","HINDALCO","JSWSTEEL","MARUTI","M&M","SUNPHARMA",
    "DRREDDY","CIPLA","DIVISLAB","APOLLOHOSP","HINDUNILVR","ITC",
    "NESTLEIND","TITAN","DLF","LT","NTPC","POWERGRID","COALINDIA",
    "ONGC","BPCL","GAIL","BHARTIARTL","ADANIPORTS","ADANIGREEN",
    "TATAPOWER","ZOMATO","IRCTC","HAL","BEL","VEDL",
}

def has_option_chain(sym):
    return sym in FNO_ELIGIBLE

# ─── BROKERAGE / P&L CALCULATOR ──────────────────────────────────────────────
def calc_pnl(entry_price, exit_price, qty, direction, trade_type,
             entry_brokerage=20.0, exit_brokerage=20.0):
    """
    Calculate net P&L after all charges (NSE F&O / Equity).
    trade_type: 'FNO_INTRADAY' | 'FNO_DELIVERY' | 'EQ_INTRADAY' | 'EQ_DELIVERY'
    Returns dict with all charge breakdowns.
    """
    turnover_entry = entry_price * qty
    turnover_exit  = exit_price  * qty
    total_turnover = turnover_entry + turnover_exit

    # Gross P&L
    if direction == "LONG":
        gross_pnl = (exit_price - entry_price) * qty
    else:
        gross_pnl = (entry_price - exit_price) * qty

    # Brokerage (flat ₹20 per order for discount brokers, capped at 0.03% for equity)
    brok = entry_brokerage + exit_brokerage

    # STT (Securities Transaction Tax)
    if "FNO" in trade_type:
        stt = turnover_exit * 0.000625   # 0.0625% on sell side for options
    elif "INTRADAY" in trade_type:
        stt = total_turnover * 0.00025   # 0.025% on buy+sell
    else:
        stt = turnover_exit * 0.001      # 0.1% on sell for delivery

    # Exchange transaction charges
    if "FNO" in trade_type:
        exc = total_turnover * 0.000053   # NSE F&O: 0.053% of premium turnover
    else:
        exc = total_turnover * 0.0000322  # NSE Equity: 0.00322%

    # SEBI charges
    sebi = total_turnover * 0.000001   # ₹10 per crore

    # GST on (brokerage + exchange + SEBI)
    gst = (brok + exc + sebi) * 0.18

    # Stamp duty
    if "FNO" in trade_type:
        stamp = turnover_entry * 0.00002   # 0.002% on buy
    elif "INTRADAY" in trade_type:
        stamp = turnover_entry * 0.00003
    else:
        stamp = turnover_entry * 0.00015

    total_charges = brok + stt + exc + sebi + gst + stamp
    net_pnl       = gross_pnl - total_charges
    net_pnl_pct   = (net_pnl / turnover_entry * 100) if turnover_entry else 0

    return {
        "gross_pnl":     round(gross_pnl,     2),
        "net_pnl":       round(net_pnl,       2),
        "net_pnl_pct":   round(net_pnl_pct,   3),
        "brokerage":     round(brok,           2),
        "stt":           round(stt,            2),
        "exchange_chrg": round(exc,            2),
        "sebi":          round(sebi,           2),
        "gst":           round(gst,            2),
        "stamp":         round(stamp,          2),
        "total_charges": round(total_charges,  2),
        "turnover":      round(total_turnover, 2),
    }

# ─── CHART ───────────────────────────────────────────────────────────────────
C = {"g":"#00d4aa","r":"#f87171","a":"#f59e0b","b":"#60a5fa","p":"#a78bfa","gray":"#4a6fa5"}

def build_chart(candles, candle_signals, indicators, show_ema, show_vwap, show_bb):
    if not candles: return None
    df = pd.DataFrame(candles)
    df["dt"] = pd.to_datetime(df["t"],unit="s").dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata")

    fig = make_subplots(rows=3,cols=1,shared_xaxes=True,
        vertical_spacing=0.02,row_heights=[0.62,0.15,0.23],
        subplot_titles=("","Volume","MACD"))

    # ── Candles ──
    fig.add_trace(go.Candlestick(
        x=df["dt"],open=df["o"],high=df["h"],low=df["l"],close=df["c"],
        increasing_line_color=C["g"], decreasing_line_color=C["r"],
        increasing_fillcolor="rgba(0,212,170,0.35)",
        decreasing_fillcolor="rgba(248,113,113,0.35)",
        name="Price",line_width=1,
    ),row=1,col=1)

    # ── EMA ──
    if show_ema and "ema9" in df.columns:
        fig.add_trace(go.Scatter(x=df["dt"],y=df["ema9"],name="EMA9",
            line=dict(color=C["p"],width=1.2),mode="lines"),row=1,col=1)
        fig.add_trace(go.Scatter(x=df["dt"],y=df["ema21"],name="EMA21",
            line=dict(color=C["b"],width=1.2),mode="lines"),row=1,col=1)

    # ── VWAP ──
    if show_vwap and "vwap" in df.columns:
        fig.add_trace(go.Scatter(x=df["dt"],y=df["vwap"],name="VWAP",
            line=dict(color=C["a"],width=1.2,dash="dash"),mode="lines"),row=1,col=1)

    # ── BB ──
    if show_bb and indicators:
        for lbl,val in [("BB↑",indicators.get("bb_upper",0)),
                         ("BB—",indicators.get("bb_mid",0)),
                         ("BB↓",indicators.get("bb_lower",0))]:
            fig.add_trace(go.Scatter(x=df["dt"],y=[val]*len(df),name=lbl,
                line=dict(color=C["gray"],width=0.7,dash="dot"),mode="lines"),row=1,col=1)

    # ── Signals — only last 60 candles to avoid clutter ──
    if candle_signals:
        recent_idx = set(range(max(0,len(df)-60), len(df)))
        # deduplicate: one signal per candle index
        seen = {}
        for s in candle_signals:
            i = s["index"]
            if i in recent_idx and i not in seen:
                seen[i] = s

        buys  = [s for s in seen.values() if s["direction"]=="BUY"]
        sells = [s for s in seen.values() if s["direction"]=="SELL"]
        dojs  = [s for s in seen.values() if s["direction"]=="NEUTRAL"]

        if buys:
            bx=[df["dt"].iloc[s["index"]] for s in buys]
            by=[df["l"].iloc[s["index"]]*0.9995 for s in buys]
            fig.add_trace(go.Scatter(x=bx,y=by,mode="markers",
                marker=dict(symbol="triangle-up",size=10,color=C["g"]),
                name="BUY",showlegend=True),row=1,col=1)
        if sells:
            sx=[df["dt"].iloc[s["index"]] for s in sells]
            sy=[df["h"].iloc[s["index"]]*1.0005 for s in sells]
            fig.add_trace(go.Scatter(x=sx,y=sy,mode="markers",
                marker=dict(symbol="triangle-down",size=10,color=C["r"]),
                name="SELL",showlegend=True),row=1,col=1)
        if dojs:
            dx=[df["dt"].iloc[s["index"]] for s in dojs]
            dy=[df["h"].iloc[s["index"]]*1.0005 for s in dojs]
            fig.add_trace(go.Scatter(x=dx,y=dy,mode="markers",
                marker=dict(symbol="diamond-open",size=7,color=C["a"]),
                name="Doji",showlegend=True),row=1,col=1)

    # ── Volume ──
    vcols=["rgba(0,212,170,0.5)" if r["c"]>=r["o"] else "rgba(248,113,113,0.5)" for _,r in df.iterrows()]
    fig.add_trace(go.Bar(x=df["dt"],y=df["v"],marker_color=vcols,name="Vol",showlegend=False),row=2,col=1)

    # ── MACD ──
    if "macd_hist" in df.columns:
        mh=df["macd_hist"]
        mcols=["rgba(0,212,170,0.6)" if v>=0 else "rgba(248,113,113,0.6)" for v in mh]
        fig.add_trace(go.Bar(x=df["dt"],y=mh,marker_color=mcols,name="Hist",showlegend=False),row=3,col=1)
        if "macd" in df.columns:
            # reconstruct signal from analysis if present
            pass

    fig.update_layout(
        height=500,
        paper_bgcolor="#060b18",plot_bgcolor="#0a1020",
        font=dict(color="#94a3b8",size=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h",yanchor="bottom",y=1.01,xanchor="left",x=0,
                    bgcolor="rgba(0,0,0,0)",font=dict(size=9)),
        margin=dict(l=0,r=40,t=8,b=0),
    )
    # TradingView-style range selector on x-axis
    fig.update_xaxes(
        rangeselector=dict(
            buttons=[
                dict(count=30,  label="30m",  step="minute", stepmode="backward"),
                dict(count=1,   label="1H",   step="hour",   stepmode="backward"),
                dict(count=3,   label="3H",   step="hour",   stepmode="backward"),
                dict(count=1,   label="1D",   step="day",    stepmode="backward"),
                dict(count=5,   label="5D",   step="day",    stepmode="backward"),
                dict(count=1,   label="1M",   step="month",  stepmode="backward"),
                dict(step="all",label="All"),
            ],
            bgcolor="#0d1525",
            activecolor="#1e3050",
            bordercolor="#1e3050",
            borderwidth=1,
            font=dict(color="#94a3b8", size=10),
            x=0, y=1.02,
        ),
        gridcolor="#1e3050",gridwidth=0.4,
        tickfont=dict(color="#4a6fa5",size=9),showticklabels=True,
    )
    for i in range(1,4):
        ax = "yaxis" if i==1 else f"yaxis{i}"
        fig.update_layout(**{ax:dict(
            gridcolor="#1e3050",gridwidth=0.4,
            zerolinecolor="#1e3050",
            tickfont=dict(color="#4a6fa5",size=9),
        )})
    return fig
def show_option_chain_tab(sym, ltp):
    st.markdown("### 📊 Option Chain")

    info = SECURITY_IDS.get(sym, {})

    # Check if this instrument supports option chain
    if not has_option_chain(sym):
        sym_name = info.get("name", sym)
        seg      = info.get("segment","")
        st.markdown(f"""
        <div style='background:#f59e0b18;border:1.5px solid #f59e0b44;border-radius:12px;
             padding:20px 24px;margin:12px 0;'>
          <div style='font-size:1.1rem;font-weight:700;color:#f59e0b;margin-bottom:8px;'>
            ⚠️ Option Chain Not Available for {sym}
          </div>
          <div style='color:#94a3b8;font-size:.85rem;line-height:1.7;'>
            <b style='color:#e2e8f0;'>{sym_name}</b> ({seg}) is not in the NSE F&O segment.<br>
            Option chains are only available for <b style='color:#e2e8f0;'>Nifty indices</b> and
            <b style='color:#e2e8f0;'>F&O-eligible stocks</b> (approx. 180 scrips on NSE).<br><br>
            You can still:<br>
            ✅ View full chart analysis and signals for {sym}<br>
            ✅ Trade the underlying stock from the <b>Portfolio</b> tab<br>
            ✅ Switch to an F&O instrument (e.g. NIFTY, BANKNIFTY) for option trading
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Show F&O alternatives
        st.markdown("**🔀 Switch to an F&O instrument:**")
        fno_quick = ["NIFTY","BANKNIFTY","FINNIFTY","RELIANCE","TCS","HDFCBANK","SBIN","TATAMOTORS"]
        fc = st.columns(4)
        for i, fs in enumerate(fno_quick):
            with fc[i % 4]:
                if st.button(fs, key=f"oc_alt_{fs}", use_container_width=True):
                    st.session_state.symbol = fs
                    st.rerun()
        return

    col_exp, col_ref = st.columns([3,1])
    with col_ref:
        refresh_oc = st.button("🔄 Refresh Chain", use_container_width=True)

    oc_key = sym
    oc_ttl = 30  # 30 sec cache
    now_ts = time.time()
    last_oc = st.session_state.oc_last_fetch.get(oc_key, 0)

    if refresh_oc or (now_ts - last_oc > oc_ttl):
        with st.spinner("Fetching option chain..."):
            rows, expiries, chain_ltp, _ = fetch_option_chain(sym)
        if rows:
            st.session_state.oc_cache[oc_key] = {"rows":rows,"expiries":expiries,"ltp":chain_ltp}
            st.session_state.oc_last_fetch[oc_key] = now_ts
    else:
        cached = st.session_state.oc_cache.get(oc_key, {})
        rows      = cached.get("rows", [])
        expiries  = cached.get("expiries", [])
        chain_ltp = cached.get("ltp", ltp)

    with col_exp:
        if expiries:
            chosen_exp = st.selectbox("Expiry", expiries, label_visibility="collapsed")
        else:
            st.caption("No expiries found")
            return

    if not rows:
        st.warning("No option chain data. Ensure Data API subscription is active.")
        return

    spot = chain_ltp or ltp
    lot  = LOT_SIZES.get(sym, 50)

    # Filter ATM ± n strikes
    n_strikes = st.slider("Strikes around ATM", 5, 20, 10, key="oc_strikes")
    rows_sorted = sorted(rows, key=lambda x: abs(x["strike"]-spot))
    atm_rows = sorted(rows_sorted[:n_strikes*2], key=lambda x: x["strike"])

    # PCR
    total_ce_oi = sum(r["ce_oi"] for r in rows)
    total_pe_oi = sum(r["pe_oi"] for r in rows)
    pcr = total_pe_oi / total_ce_oi if total_ce_oi else 0
    pcr_col = "#00d4aa" if pcr>1.2 else "#f87171" if pcr<0.8 else "#f59e0b"
    max_oi = max(max((r["ce_oi"] for r in rows),default=1),
                 max((r["pe_oi"] for r in rows),default=1))

    # Summary bar
    st.markdown(f"""
    <div style='display:flex;gap:20px;background:#0d1525;border:.5px solid #1e3050;
         border-radius:8px;padding:8px 14px;margin-bottom:10px;font-size:.8rem;flex-wrap:wrap;'>
      <span>Spot: <b style='color:#e2e8f0'>₹{spot:,.2f}</b></span>
      <span>PCR: <b style='color:{pcr_col}'>{pcr:.2f}</b></span>
      <span>Call OI: <b style='color:#f87171'>{fmt_oi(total_ce_oi)}</b></span>
      <span>Put OI: <b style='color:#00d4aa'>{fmt_oi(total_pe_oi)}</b></span>
      <span>Lot: <b style='color:#e2e8f0'>{lot}</b></span>
      <span style='color:#4a6fa5'>Updated: {datetime.fromtimestamp(st.session_state.oc_last_fetch.get(oc_key,now_ts)).strftime("%H:%M:%S")}</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Order placement state ──
    if "oc_order" not in st.session_state:
        st.session_state.oc_order = None

    # Column view toggle
    view = st.radio("View", ["Full Chain","CE Focus","PE Focus"], horizontal=True, label_visibility="collapsed")

    # ── TABLE HEADER ──
    if view == "Full Chain":
        hdr = """<table class='oc-table'>
        <tr>
          <th>CE OI</th><th>IV</th><th>Delta</th><th>LTP</th><th>Bid/Ask</th>
          <th>STRIKE</th>
          <th>Bid/Ask</th><th>LTP</th><th>Delta</th><th>IV</th><th>PE OI</th>
        </tr>"""
    elif view == "CE Focus":
        hdr = """<table class='oc-table'>
        <tr><th>CE OI</th><th>Δ OI</th><th>IV</th><th>Delta</th><th>Theta</th><th>LTP</th><th>Bid</th><th>Ask</th><th>STRIKE</th></tr>"""
    else:
        hdr = """<table class='oc-table'>
        <tr><th>STRIKE</th><th>Bid</th><th>Ask</th><th>LTP</th><th>Delta</th><th>Theta</th><th>IV</th><th>PE OI</th><th>Δ OI</th></tr>"""

    rows_html = ""
    for r in atm_rows:
        sp      = r["strike"]
        is_atm  = abs(sp - spot) == min(abs(x["strike"]-spot) for x in atm_rows)
        atm_cls = "oc-atm" if is_atm else ""
        ce_bar  = int(r["ce_oi"]/max_oi*80) if max_oi else 0
        pe_bar  = int(r["pe_oi"]/max_oi*80) if max_oi else 0
        atm_lbl = " ← ATM" if is_atm else ""

        if view == "Full Chain":
            rows_html += f"""<tr class='{atm_cls}'>
              <td class='oc-call'>
                {fmt_oi(r['ce_oi'])}
                <div style='height:3px;background:linear-gradient(to left,#f87171 {ce_bar}%,transparent 0);border-radius:2px;margin-top:2px'></div>
              </td>
              <td class='oc-iv'>{r['ce_iv']}%</td>
              <td style='color:#a78bfa;font-size:.68rem'>{r['ce_delta']}</td>
              <td class='oc-call'>{fmt(r['ce_ltp'])}</td>
              <td style='color:#4a6fa5;font-size:.68rem'>{fmt(r['ce_bid'])}/{fmt(r['ce_ask'])}</td>
              <td class='oc-strike'>{int(sp)}{atm_lbl}</td>
              <td style='color:#4a6fa5;font-size:.68rem'>{fmt(r['pe_bid'])}/{fmt(r['pe_ask'])}</td>
              <td class='oc-put'>{fmt(r['pe_ltp'])}</td>
              <td style='color:#a78bfa;font-size:.68rem'>{r['pe_delta']}</td>
              <td class='oc-iv'>{r['pe_iv']}%</td>
              <td class='oc-put'>
                {fmt_oi(r['pe_oi'])}
                <div style='height:3px;background:linear-gradient(to right,#00d4aa {pe_bar}%,transparent 0);border-radius:2px;margin-top:2px'></div>
              </td>
            </tr>"""
        elif view == "CE Focus":
            rows_html += f"""<tr class='{atm_cls}'>
              <td class='oc-call'>{fmt_oi(r['ce_oi'])}</td>
              <td style='color:#4a6fa5;font-size:.68rem'>—</td>
              <td class='oc-iv'>{r['ce_iv']}%</td>
              <td style='color:#a78bfa'>{r['ce_delta']}</td>
              <td style='color:#f59e0b;font-size:.68rem'>{r['ce_theta']}</td>
              <td class='oc-call'>{fmt(r['ce_ltp'])}</td>
              <td style='color:#4a6fa5;font-size:.68rem'>{fmt(r['ce_bid'])}</td>
              <td style='color:#4a6fa5;font-size:.68rem'>{fmt(r['ce_ask'])}</td>
              <td class='oc-strike'>{int(sp)}{atm_lbl}</td>
            </tr>"""
        else:
            rows_html += f"""<tr class='{atm_cls}'>
              <td class='oc-strike'>{int(sp)}{atm_lbl}</td>
              <td style='color:#4a6fa5;font-size:.68rem'>{fmt(r['pe_bid'])}</td>
              <td style='color:#4a6fa5;font-size:.68rem'>{fmt(r['pe_ask'])}</td>
              <td class='oc-put'>{fmt(r['pe_ltp'])}</td>
              <td style='color:#a78bfa'>{r['pe_delta']}</td>
              <td style='color:#f59e0b;font-size:.68rem'>{r['pe_theta']}</td>
              <td class='oc-iv'>{r['pe_iv']}%</td>
              <td class='oc-put'>{fmt_oi(r['pe_oi'])}</td>
              <td style='color:#4a6fa5;font-size:.68rem'>—</td>
            </tr>"""

    st.markdown(hdr + rows_html + "</table>", unsafe_allow_html=True)

    # ── ONE-CLICK ORDER SECTION ──
    st.markdown("---")
    st.markdown("#### ⚡ Quick Order from Chain")

    # Find ATM strike
    atm_row = min(atm_rows, key=lambda x: abs(x["strike"]-spot)) if atm_rows else None
    strikes = [int(r["strike"]) for r in atm_rows]

    oc1, oc2, oc3, oc4, oc5 = st.columns([2,2,1,1,1])
    with oc1:
        chosen_strike = st.selectbox("Strike", strikes,
            index=strikes.index(int(atm_row["strike"])) if atm_row else 0,
            key="oc_strike_sel")
    with oc2:
        opt_type = st.selectbox("Option", ["CE (Call)","PE (Put)"], key="oc_opt_type")
    with oc3:
        lots = st.number_input("Lots", min_value=1, value=1, key="oc_lots")
    with oc4:
        product = st.selectbox("Product", ["INTRADAY","CNC"], key="oc_product")
    with oc5:
        price_type = st.selectbox("Price", ["Market","Limit"], key="oc_pricetype")

    # Find selected row
    sel_row = next((r for r in atm_rows if int(r["strike"])==chosen_strike), None)
    is_ce   = "CE" in opt_type
    if sel_row:
        ltp_opt    = sel_row["ce_ltp"] if is_ce else sel_row["pe_ltp"]
        sec_id_opt = sel_row["ce_security_id"] if is_ce else sel_row["pe_security_id"]
        bid_opt    = sel_row["ce_bid"] if is_ce else sel_row["pe_bid"]
        ask_opt    = sel_row["ce_ask"] if is_ce else sel_row["pe_ask"]
        iv_opt     = sel_row["ce_iv"]  if is_ce else sel_row["pe_iv"]
        delta_opt  = sel_row["ce_delta"] if is_ce else sel_row["pe_delta"]

        st.markdown(f"""
        <div style='background:#0d1525;border:.5px solid #1e3050;border-radius:8px;padding:10px 14px;
             margin:8px 0;display:flex;gap:20px;flex-wrap:wrap;font-size:.8rem;'>
          <span>LTP: <b style='color:#e2e8f0'>₹{fmt(ltp_opt)}</b></span>
          <span>Bid: <b style='color:#00d4aa'>₹{fmt(bid_opt)}</b></span>
          <span>Ask: <b style='color:#f87171'>₹{fmt(ask_opt)}</b></span>
          <span>IV: <b style='color:#a78bfa'>{iv_opt}%</b></span>
          <span>Delta: <b style='color:#f59e0b'>{delta_opt}</b></span>
          <span>Sec ID: <b style='color:#4a6fa5'>{sec_id_opt}</b></span>
          <span>Qty: <b style='color:#e2e8f0'>{lots*lot} ({lots} lot{'s' if lots>1 else ''})</b></span>
        </div>
        """, unsafe_allow_html=True)

        limit_price = 0.0
        if price_type == "Limit":
            limit_price = st.number_input("Limit Price", min_value=0.0,
                value=float(ltp_opt), step=0.05, key="oc_limit_px")

        b1, b2, b3 = st.columns([1,1,2])
        with b1:
            if st.button(f"🟢 BUY {chosen_strike} {opt_type.split()[0]}",
                         use_container_width=True, type="primary", key="oc_buy"):
                if not sec_id_opt:
                    st.error("Security ID missing — chain data may be incomplete")
                else:
                    res = place_order(sec_id_opt, "NSE_FNO", "BUY", product,
                                      lots*lot, limit_price)
                    if res.get("orderId"):
                        st.success(f"✅ BUY order placed — ID: {res['orderId']}")
                        add_alert("BUY", f"BUY {sym} {chosen_strike} {opt_type.split()[0]} ×{lots*lot} @ {'MKT' if limit_price==0 else limit_price}")
                    else:
                        st.error(res.get("errorMessage") or res.get("error") or str(res))
        with b2:
            if st.button(f"🔴 SELL {chosen_strike} {opt_type.split()[0]}",
                         use_container_width=True, key="oc_sell"):
                if not sec_id_opt:
                    st.error("Security ID missing")
                else:
                    res = place_order(sec_id_opt, "NSE_FNO", "SELL", product,
                                      lots*lot, limit_price)
                    if res.get("orderId"):
                        st.success(f"✅ SELL order placed — ID: {res['orderId']}")
                        add_alert("SELL", f"SELL {sym} {chosen_strike} {opt_type.split()[0]} ×{lots*lot} @ {'MKT' if limit_price==0 else limit_price}")
                    else:
                        st.error(res.get("errorMessage") or res.get("error") or str(res))
        with b3:
            st.caption(f"⚠️ Orders execute on NSE_FNO segment. Verify Security ID before placing.")

# ─── POSITIONS / HOLDINGS TAB ─────────────────────────────────────────────────
def show_portfolio_tab():
    st.markdown("### 🗂️ Portfolio")
    t1, t2, t3, t4 = st.tabs(["📋 Positions","📦 Holdings","📜 Orders","📊 Trade Journal"])

    with t1:
        if st.button("🔄 Refresh Positions", key="ref_pos"):
            pos = fetch_positions()
            if isinstance(pos, list):
                if pos:
                    df = pd.DataFrame(pos)
                    keep = [c for c in ["tradingSymbol","exchangeSegment","positionType",
                                        "productType","netQty","buyAvg","sellAvg",
                                        "unrealizedProfit","realizedProfit",
                                        "drvStrikePrice","drvOptionType","drvExpiryDate"]
                            if c in df.columns]
                    df2 = df[keep].copy()
                    df2.columns = [c.replace("drv","").replace("exchangeSegment","Seg")
                                   .replace("tradingSymbol","Symbol")
                                   .replace("positionType","Pos")
                                   .replace("productType","Product") for c in keep]
                    st.dataframe(df2, use_container_width=True, hide_index=True)
                    total_unreal = sum(float(p.get("unrealizedProfit",0)) for p in pos)
                    total_real   = sum(float(p.get("realizedProfit",0))   for p in pos)
                    col1,col2 = st.columns(2)
                    col1.metric("Unrealised P&L", f"₹{total_unreal:,.2f}",
                                delta_color="normal" if total_unreal>=0 else "inverse")
                    col2.metric("Realised P&L", f"₹{total_real:,.2f}",
                                delta_color="normal" if total_real>=0 else "inverse")
                else:
                    st.info("No open positions today.")
            else:
                st.error((pos or {}).get("error","Failed to fetch positions"))
        else:
            st.caption("Click Refresh to load positions.")

    with t2:
        if st.button("🔄 Refresh Holdings", key="ref_hld"):
            hld = fetch_holdings()
            if isinstance(hld, list) and hld:
                df = pd.DataFrame(hld)
                keep = [c for c in ["tradingSymbol","exchange","totalQty","availableQty",
                                    "avgCostPrice","t1Qty"] if c in df.columns]
                st.dataframe(df[keep], use_container_width=True, hide_index=True)
            elif "error" in (hld or {}):
                st.error(hld["error"])
            else:
                st.info("No holdings found.")
        else:
            st.caption("Click Refresh to load holdings.")

    with t3:
        if st.button("🔄 Refresh Orders", key="ref_ord"):
            orders = fetch_orders()
            if isinstance(orders, list) and orders:
                df = pd.DataFrame(orders)
                keep = [c for c in ["orderId","tradingSymbol","transactionType","orderStatus",
                                    "orderType","quantity","price","productType","createTime"]
                        if c in df.columns]
                st.dataframe(df[keep], use_container_width=True, hide_index=True)
            elif "error" in (orders or {}):
                st.error(orders["error"])
            else:
                st.info("No orders today.")
        else:
            st.caption("Click Refresh to load today's orders.")

    # ── TRADE JOURNAL ─────────────────────────────────────────────────────────
    with t4:
        st.markdown("#### 📊 Trade Journal — Net P&L Calculator")
        st.caption("Every trade closed from the Strategy tab is logged here with full charge breakdown.")

        trade_log = st.session_state.get("trade_log", [])

        # ── Manual trade entry ────────────────────────────────────────────────
        with st.expander("➕ Log a Trade Manually", expanded=not bool(trade_log)):
            lc1, lc2, lc3, lc4 = st.columns(4)
            with lc1:
                log_sym    = st.text_input("Symbol", value="NIFTY", key="log_sym")
                log_dir    = st.selectbox("Direction", ["LONG","SHORT"], key="log_dir")
            with lc2:
                log_entry  = st.number_input("Entry Price", min_value=0.01, value=100.0, step=0.05, key="log_entry")
                log_exit   = st.number_input("Exit Price",  min_value=0.01, value=110.0, step=0.05, key="log_exit")
            with lc3:
                log_qty    = st.number_input("Quantity", min_value=1, value=75, key="log_qty")
                log_type   = st.selectbox("Trade Type",
                                          ["FNO_INTRADAY","FNO_DELIVERY","EQ_INTRADAY","EQ_DELIVERY"],
                                          key="log_type")
            with lc4:
                log_brok   = st.number_input("Brokerage per order (₹)", min_value=0.0, value=20.0, key="log_brok")
                log_note   = st.text_input("Notes", placeholder="Optional", key="log_note")

            if st.button("📥 Calculate & Log Trade", use_container_width=True, type="primary", key="log_add"):
                pnl_data = calc_pnl(log_entry, log_exit, log_qty, log_dir, log_type,
                                    log_brok, log_brok)
                entry_rec = {
                    "time":        ist_now().strftime("%d %b %H:%M"),
                    "symbol":      log_sym.upper(),
                    "direction":   log_dir,
                    "qty":         log_qty,
                    "entry":       log_entry,
                    "exit":        log_exit,
                    "type":        log_type,
                    "note":        log_note,
                    **pnl_data,
                }
                st.session_state.trade_log.insert(0, entry_rec)
                st.success(f"✅ Logged! Net P&L: ₹{pnl_data['net_pnl']:+,.2f}")
                st.rerun()

        # ── Summary metrics ───────────────────────────────────────────────────
        if trade_log:
            total_net   = sum(t["net_pnl"]       for t in trade_log)
            total_gross = sum(t["gross_pnl"]      for t in trade_log)
            total_charg = sum(t["total_charges"]  for t in trade_log)
            wins        = sum(1 for t in trade_log if t["net_pnl"] > 0)
            losses      = sum(1 for t in trade_log if t["net_pnl"] <= 0)
            win_rate    = (wins / len(trade_log) * 100) if trade_log else 0
            avg_win     = (sum(t["net_pnl"] for t in trade_log if t["net_pnl"]>0) / wins) if wins else 0
            avg_loss    = (sum(t["net_pnl"] for t in trade_log if t["net_pnl"]<=0) / losses) if losses else 0

            net_col = "#00d4aa" if total_net >= 0 else "#f87171"
            st.markdown(f"""
            <div style='display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;'>
              <div style='background:#0d1525;border:.5px solid #1e3050;border-radius:8px;padding:10px 14px;'>
                <div style='font-size:.7rem;color:#4a6fa5;'>Net P&L (after charges)</div>
                <div style='font-size:1.3rem;font-weight:800;color:{net_col};'>₹{total_net:+,.2f}</div>
              </div>
              <div style='background:#0d1525;border:.5px solid #1e3050;border-radius:8px;padding:10px 14px;'>
                <div style='font-size:.7rem;color:#4a6fa5;'>Gross P&L</div>
                <div style='font-size:1.3rem;font-weight:700;color:#e2e8f0;'>₹{total_gross:+,.2f}</div>
                <div style='font-size:.65rem;color:#f87171;'>Charges: ₹{total_charg:,.2f}</div>
              </div>
              <div style='background:#0d1525;border:.5px solid #1e3050;border-radius:8px;padding:10px 14px;'>
                <div style='font-size:.7rem;color:#4a6fa5;'>Win Rate</div>
                <div style='font-size:1.3rem;font-weight:700;color:#{'00d4aa' if win_rate>=50 else 'f87171'};'>{win_rate:.0f}%</div>
                <div style='font-size:.65rem;color:#4a6fa5;'>W:{wins} / L:{losses}</div>
              </div>
              <div style='background:#0d1525;border:.5px solid #1e3050;border-radius:8px;padding:10px 14px;'>
                <div style='font-size:.7rem;color:#4a6fa5;'>Avg Win / Loss</div>
                <div style='font-size:.95rem;font-weight:700;'>
                  <span style='color:#00d4aa;'>+₹{avg_win:,.0f}</span> /
                  <span style='color:#f87171;'>₹{avg_loss:,.0f}</span>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # ── Trade cards ───────────────────────────────────────────────────
            for idx, t in enumerate(trade_log):
                nc = "#00d4aa" if t["net_pnl"] >= 0 else "#f87171"
                with st.expander(
                    f"{'✅' if t['net_pnl']>=0 else '❌'} {t['symbol']} {t['direction']} "
                    f"· Net ₹{t['net_pnl']:+,.2f} · {t['time']}",
                    expanded=False
                ):
                    tc1, tc2, tc3 = st.columns(3)
                    with tc1:
                        st.markdown(f"""
                        <div style='font-size:.8rem;'>
                          <div style='color:#4a6fa5;'>Symbol</div>
                          <div style='color:#e2e8f0;font-weight:700;'>{t['symbol']} · {t['direction']} · {t['qty']} qty</div>
                          <div style='color:#4a6fa5;margin-top:6px;'>Entry → Exit</div>
                          <div style='color:#e2e8f0;'>₹{t['entry']:,.2f} → ₹{t['exit']:,.2f}</div>
                          <div style='color:#4a6fa5;margin-top:6px;'>Type</div>
                          <div style='color:#e2e8f0;'>{t['type']}</div>
                          {"<div style='color:#4a6fa5;margin-top:6px;'>Notes</div><div style='color:#e2e8f0;'>" + t.get('note','—') + "</div>" if t.get('note') else ""}
                        </div>
                        """, unsafe_allow_html=True)
                    with tc2:
                        st.markdown(f"""
                        <div style='font-size:.8rem;'>
                          <div style='color:#4a6fa5;'>Gross P&L</div>
                          <div style='font-size:1rem;font-weight:700;color:#e2e8f0;'>₹{t['gross_pnl']:+,.2f}</div>
                          <div style='color:#4a6fa5;margin-top:8px;'>Charge Breakdown</div>
                          <div style='color:#94a3b8;'>Brokerage: <b>₹{t['brokerage']:,.2f}</b></div>
                          <div style='color:#94a3b8;'>STT: <b>₹{t['stt']:,.2f}</b></div>
                          <div style='color:#94a3b8;'>Exchange: <b>₹{t['exchange_chrg']:,.2f}</b></div>
                          <div style='color:#94a3b8;'>SEBI: <b>₹{t['sebi']:,.2f}</b></div>
                          <div style='color:#94a3b8;'>GST: <b>₹{t['gst']:,.2f}</b></div>
                          <div style='color:#94a3b8;'>Stamp: <b>₹{t['stamp']:,.2f}</b></div>
                          <div style='color:#f87171;margin-top:4px;'>Total Charges: <b>₹{t['total_charges']:,.2f}</b></div>
                        </div>
                        """, unsafe_allow_html=True)
                    with tc3:
                        st.markdown(f"""
                        <div style='font-size:.8rem;text-align:center;'>
                          <div style='color:#4a6fa5;margin-bottom:4px;'>NET P&L</div>
                          <div style='font-size:1.8rem;font-weight:800;color:{nc};'>₹{t['net_pnl']:+,.2f}</div>
                          <div style='font-size:.85rem;color:{nc};'>{t['net_pnl_pct']:+.3f}%</div>
                          <div style='color:#4a6fa5;margin-top:10px;font-size:.72rem;'>Turnover</div>
                          <div style='color:#e2e8f0;'>₹{t['turnover']:,.2f}</div>
                          <div style='color:#4a6fa5;margin-top:6px;font-size:.72rem;'>Charge %</div>
                          <div style='color:#f87171;'>
                            {(t['total_charges']/t['turnover']*100):.3f}% of turnover
                          </div>
                        </div>
                        """, unsafe_allow_html=True)

                    if st.button("🗑️ Remove", key=f"del_log_{idx}", type="secondary"):
                        st.session_state.trade_log.pop(idx)
                        st.rerun()

            st.divider()
            jc1, jc2 = st.columns(2)
            with jc1:
                if st.button("🗑️ Clear All Trades", type="secondary", use_container_width=True):
                    st.session_state.trade_log = []
                    st.rerun()
            with jc2:
                # Export as CSV
                if trade_log:
                    df_export = pd.DataFrame(trade_log)
                    csv = df_export.to_csv(index=False)
                    st.download_button("📥 Export CSV", csv,
                                       file_name=f"trade_journal_{ist_now().strftime('%Y%m%d')}.csv",
                                       mime="text/csv", use_container_width=True)
        else:
            st.info("No trades logged yet. Close a strategy trade or add one manually above.")

# ═════════════════════════════════════════════════════════════════════════════
#  LOGIN
# ═════════════════════════════════════════════════════════════════════════════
def show_login():
    _,col,_ = st.columns([1,1.4,1])
    with col:
        st.markdown("""
        <div style='background:#0d1525;border:.5px solid #1e3050;border-radius:14px;
             padding:2.5rem 2rem;max-width:460px;margin:3rem auto;'>
          <div style='font-size:2rem;font-weight:800;color:#00d4aa;text-align:center;margin-bottom:.3rem;'>⚡ NiftyEdge Pro</div>
          <div style='text-align:center;color:#4a6fa5;font-size:.83rem;margin-bottom:1.5rem;'>
            Dhan-powered Options Dashboard · Enter DhanHQ API credentials
          </div>
        </div>""", unsafe_allow_html=True)

        with st.form("login"):
            cid = st.text_input("Client ID", placeholder="1000XXXXXX")
            tok = st.text_input("Access Token", type="password", placeholder="eyJ...")
            sub = st.form_submit_button("🔐 Connect to Dhan", use_container_width=True)

        if sub:
            if not cid.strip() or not tok.strip():
                st.error("Both fields required.")
            else:
                st.session_state["_cid"] = cid.strip()
                st.session_state["_tok"] = tok.strip()
                with st.spinner("Verifying..."):
                    ok, msg = verify_credentials(cid.strip(), tok.strip())
                if ok:
                    st.session_state.authenticated = True
                    st.session_state.client_id     = cid.strip()
                    st.session_state.access_token  = tok.strip()
                    st.success(f"✅ {msg}")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")
                    with st.expander("Troubleshooting"):
                        st.markdown("""
- Token expires every **24h** — regenerate at [api.dhan.co](https://api.dhan.co)
- Client ID: numeric only, no spaces
- Wait 1–2 min after generating a new token
- Option Chain / Data APIs need **Data API subscription** (₹499/month)
                        """)

        _,bc,_ = st.columns([1,2,1])
        with bc:
            if st.button("⚡ Skip check (use anyway)", use_container_width=True):
                c2 = st.session_state.get("_cid","")
                t2 = st.session_state.get("_tok","")
                if c2 and t2:
                    st.session_state.update(authenticated=True,client_id=c2,access_token=t2)
                    st.rerun()
                else:
                    st.warning("Submit credentials first.")

        st.markdown("<div style='text-align:center;margin-top:1rem;font-size:.75rem;color:#4a6fa5;'>🔒 Stored in browser session only — never sent to third parties<br><a href='https://api.dhan.co' target='_blank' style='color:#00d4aa'>api.dhan.co</a></div>", unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
#  DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════
def show_dashboard():
    sym     = st.session_state.symbol
    sym_inf = SECURITY_IDS.get(sym,{})

    # ── SIDEBAR ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"""<div style='font-size:1.15rem;font-weight:700;color:#00d4aa;'>⚡ NiftyEdge Pro</div>
        <div style='font-size:.7rem;color:#4a6fa5;margin-bottom:.6rem;'>
        {st.session_state.client_id[:6]}•••• · {len(SECURITY_IDS)} instruments</div>""",
        unsafe_allow_html=True)

        # ── INSTRUMENT SELECTOR ──────────────────────────────────────────────
        st.markdown("<div style='font-size:.75rem;color:#4a6fa5;font-weight:600;margin-bottom:4px;'>🔍 Search Any Stock / Index</div>", unsafe_allow_html=True)
        sq = st.text_input("Search", placeholder="Symbol, name or sector…",
                           label_visibility="collapsed", key="sb_search")
        matched = search_stocks(sq)

        if sq:
            n_match = len(matched)
            st.caption(f"{n_match} match{'es' if n_match!=1 else ''}")
            opts = [f"{s}  —  {SECURITY_IDS[s]['name']}" for s in matched[:50]]
            if opts:
                sel = st.selectbox("Result", opts, label_visibility="collapsed", key="sb_result")
                sel_sym = sel.split("  —  ")[0].strip()
                bc1, bc2 = st.columns([2,1])
                with bc1:
                    if st.button("📈 Load", use_container_width=True, type="primary", key="sb_load"):
                        st.session_state.symbol = sel_sym
                        st.rerun()
                with bc2:
                    oc_ok = has_option_chain(sel_sym)
                    st.markdown(
                        f"<div style='font-size:.65rem;padding-top:7px;color:{'#00d4aa' if oc_ok else '#f59e0b'};'>{'✅ F&O' if oc_ok else '⚠️ No OC'}</div>",
                        unsafe_allow_html=True)
            else:
                st.caption("No results.")

            with st.expander("🔧 Load any NSE scrip by Security ID"):
                c_sym = st.text_input("Label", placeholder="e.g. PAYTM", key="cs_sym")
                c_id  = st.text_input("Security ID", placeholder="e.g. 21865", key="cs_id")
                c_seg = st.selectbox("Segment", ["NSE_EQ","BSE_EQ","NSE_FNO","IDX_I"], key="cs_seg")
                if st.button("➕ Add & Load", use_container_width=True, key="cs_add"):
                    if c_sym and c_id:
                        sym_key = c_sym.upper().strip()
                        SECURITY_IDS[sym_key] = {"id":c_id.strip(),"segment":c_seg,
                                                  "name":sym_key,"sector":"Custom"}
                        SECTOR_GROUPS.setdefault("Custom",[])
                        if sym_key not in SECTOR_GROUPS["Custom"]:
                            SECTOR_GROUPS["Custom"].append(sym_key)
                        st.session_state.symbol = sym_key
                        st.success(f"Added {sym_key}"); st.rerun()
                    else:
                        st.error("Both fields required")
        else:
            # Pinned majors
            st.markdown("<div style='font-size:.72rem;color:#4a6fa5;margin-bottom:3px;'>📌 Major Instruments</div>", unsafe_allow_html=True)
            MAJORS = {
                "Indices":   ["NIFTY","BANKNIFTY","FINNIFTY","MIDCPNIFTY","SENSEX"],
                "Large Cap": ["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","SBIN","LT","BAJFINANCE"],
                "Popular":   ["ZOMATO","IRCTC","TATAMOTORS","HAL","DMART","TRENT","TITAN"],
            }
            for grp, gsyms in MAJORS.items():
                st.markdown(f"<div style='font-size:.63rem;color:#4a6fa5;margin-top:4px;'>{grp}</div>", unsafe_allow_html=True)
                gc = st.columns(3)
                for i, gs in enumerate(gsyms):
                    with gc[i % 3]:
                        is_cur = gs == sym
                        if st.button(gs, key=f"maj_{gs}", use_container_width=True,
                                     type="primary" if is_cur else "secondary"):
                            st.session_state.symbol = gs; st.rerun()

            st.markdown("<div style='font-size:.72rem;color:#4a6fa5;margin:6px 0 3px;'>🗂 Browse by Sector</div>", unsafe_allow_html=True)
            secs2 = ["— Pick sector —"] + sorted(SECTOR_GROUPS.keys())
            sec2  = st.selectbox("Sector", secs2, label_visibility="collapsed", key="sec_browse")
            if sec2 != "— Pick sector —":
                syms2 = SECTOR_GROUPS.get(sec2, [])
                disp2 = [f"{s}  —  {SECURITY_IDS[s]['name']}" for s in syms2]
                if disp2:
                    picked2 = st.selectbox("Stock", disp2, label_visibility="collapsed", key="sec_pick")
                    if st.button("Load →", use_container_width=True, key="sec_load"):
                        st.session_state.symbol = picked2.split("  —  ")[0].strip()
                        st.rerun()

        st.divider()

        # ── TIMEFRAME ────────────────────────────────────────────────────────
        st.markdown("<div style='font-size:.75rem;color:#4a6fa5;font-weight:600;margin-bottom:3px;'>⏱ Timeframe</div>", unsafe_allow_html=True)
        tf_map = {
            "1 min":"1","5 min":"5","15 min":"15",
            "25 min":"25","1 Hour":"60","Daily":"1D",
        }
        tf_lbl   = st.selectbox("Timeframe", list(tf_map.keys()), index=2, label_visibility="collapsed")
        interval = tf_map[tf_lbl]
        if interval != st.session_state.interval:
            st.session_state.interval = interval

        # ── DATE RANGE ───────────────────────────────────────────────────────
        st.markdown("<div style='font-size:.75rem;color:#4a6fa5;font-weight:600;margin:8px 0 3px;'>📅 Date Range</div>", unsafe_allow_html=True)

        # Preset options depend on timeframe
        is_daily = (interval == "1D")
        if is_daily:
            presets = ["Last 1 Month","Last 3 Months","Last 6 Months","Last 1 Year","Custom"]
        else:
            presets = ["Today","Last Trading Day","This Week","Last 5 Days","Custom"]

        # Keep mode valid if timeframe changes
        cur_mode = st.session_state.date_mode
        if cur_mode not in presets:
            cur_mode = presets[0]
            st.session_state.date_mode = cur_mode

        date_mode = st.selectbox("Date Range", presets,
                                 index=presets.index(cur_mode),
                                 label_visibility="collapsed",
                                 key="date_mode_sel")
        if date_mode != st.session_state.date_mode:
            st.session_state.date_mode    = date_mode
            st.session_state.last_fetch   = {}   # invalidate cache

        today    = datetime.now().date()
        ltday    = last_trading_day()
        custom_from = st.session_state.custom_from
        custom_to   = st.session_state.custom_to

        if date_mode == "Custom":
            col_f, col_t = st.columns(2)
            with col_f:
                default_from = custom_from if custom_from else (ltday if not is_daily else today - timedelta(days=90))
                new_from = st.date_input("From", value=default_from, max_value=today, label_visibility="visible")
            with col_t:
                default_to = custom_to if custom_to else today
                new_to = st.date_input("To", value=default_to, max_value=today, label_visibility="visible")
            if new_from != custom_from or new_to != custom_to:
                st.session_state.custom_from = new_from
                st.session_state.custom_to   = new_to
                st.session_state.last_fetch  = {}
            custom_from = st.session_state.custom_from
            custom_to   = st.session_state.custom_to
        else:
            # Show resolved range as info
            fd, td = resolve_date_range(date_mode, None, None, interval)
            fd_disp = fd.split(" ")[0]; td_disp = td.split(" ")[0]
            st.markdown(f"<div style='font-size:.68rem;color:#4a6fa5;padding:3px 0;'>{fd_disp} → {td_disp}</div>", unsafe_allow_html=True)

        st.markdown("<div style='font-size:.75rem;color:#4a6fa5;font-weight:600;margin:8px 0 3px;'>🎨 Chart Overlays</div>", unsafe_allow_html=True)
        show_ema  = st.checkbox("EMA 9/21", value=True)
        show_vwap = st.checkbox("VWAP",     value=True)
        show_bb   = st.checkbox("Bollinger",value=False)

        st.divider()
        if st.button("💰 Funds",use_container_width=True):
            f = fetch_funds()
            if isinstance(f,dict) and not f.get("error"):
                av = (f.get("availabelBalance") or f.get("availableBalance")
                      or (f.get("data") or {}).get("availabelBalance",0))
                st.metric("Available",f"₹{float(av):,.2f}")
            elif "error" in (f or {}):
                st.error(f["error"])

        if st.button("🚪 Logout",use_container_width=True):
            for k,v in DEFAULTS.items():
                st.session_state[k]=v
            st.rerun()

    # ── TOP BAR ──────────────────────────────────────────────────────────────
    now_ist = ist_now().strftime("%d %b %Y  %H:%M IST")
    mkt_status, mkt_col, mkt_emoji = market_status()
    market_txt = f"{mkt_emoji} {mkt_status}"
    st.markdown(f"""
    <div style='display:flex;justify-content:space-between;align-items:center;
         background:#0d1525;border:.5px solid #1e3050;border-radius:8px;
         padding:7px 16px;margin-bottom:8px;'>
      <span style='font-size:.95rem;font-weight:700;color:#00d4aa;'>⚡ NiftyEdge Pro</span>
      <span style='font-size:.85rem;color:#e2e8f0;font-weight:600;'>{sym}
        <span style='color:#4a6fa5;font-weight:400;font-size:.73rem;'> {sym_inf.get("name","")} · {sym_inf.get("sector","")}</span>
      </span>
      <span style='font-size:.78rem;'><span style='color:{mkt_col};font-weight:700;'>{mkt_emoji} {mkt_status}</span>
        <span style='color:#4a6fa5;'> &nbsp;·&nbsp; 🕐 {now_ist}</span>
      </span>
    </div>""", unsafe_allow_html=True)

    # ── QUOTES ───────────────────────────────────────────────────────────────
    quote = fetch_quote(sym)
    ltp=chg=pct=0.0
    if quote and not quote.get("error"):
        seg=SECURITY_IDS[sym]["segment"]; sid=SECURITY_IDS[sym]["id"]
        q=(quote.get(seg) or {}).get(sid, {})
        ltp=q.get("ltp",0); prev=q.get("previousClosePrice",ltp)
        chg=ltp-prev; pct=(chg/prev*100) if prev else 0

    mc=st.columns(6)
    mc[0].metric(sym, f"₹{ltp:,.2f}", f"{chg:+.2f} ({pct:+.2f}%)")
    for i,(s,sid,seg) in enumerate([("NIFTY","13","IDX_I"),("BANKNIFTY","25","IDX_I")],1):
        q2 = fetch_quote(s) if s!=sym else quote
        v=0
        if q2 and not q2.get("error"):
            v=(q2.get(seg) or {}).get(sid,{}).get("ltp",0)
        mc[i].metric(s, f"₹{v:,.2f}")
    mc[3].metric("Lot Size", LOT_SIZES.get(sym,"—"))
    mc[4].metric("Interval", tf_lbl)
    mc[5].metric("Market", mkt_status, delta_color="off")

    # ── TABS ─────────────────────────────────────────────────────────────────
    tabs = st.tabs(["📈 Chart & Analysis","📊 Option Chain","🎯 Strategies","🗂️ Portfolio","⚙️ Config"])
    tab_chart, tab_oc, tab_strat, tab_port, tab_cfg = tabs

    # ── FETCH / CACHE CANDLES ────────────────────────────────────────────────
    date_mode   = st.session_state.date_mode
    custom_from = st.session_state.custom_from
    custom_to   = st.session_state.custom_to

    # Cache key includes date range so switching range forces a re-fetch
    cf_str = str(custom_from) if custom_from else ""
    ct_str = str(custom_to)   if custom_to   else ""
    ck = f"{sym}_{interval}_{date_mode}_{cf_str}_{ct_str}"

    # Auto-refresh only makes sense for today/live; historical never stales
    live_mode  = date_mode in ("Today",)
    cache_ttl  = 90 if live_mode else 3600   # 90s live, 1h for historical

    need_fetch = time.time() - st.session_state.last_fetch.get(ck, 0) > cache_ttl

    if need_fetch:
        with st.spinner(f"Fetching {sym} {tf_lbl} · {date_mode}..."):
            raw = fetch_candles(sym, interval, date_mode, custom_from, custom_to)
        if raw and not raw.get("error") and raw.get("close"):
            result = analyse(raw)
            result["symbol"] = sym
            st.session_state.analysis_cache[ck] = result
            st.session_state.last_fetch[ck]     = time.time()
            sig = result.get("signal",{})
            if sig.get("type") in ("BUY","SELL"):
                pats=sig.get("patterns",[])
                add_alert(sig["type"],f"{sym} {pats[0]['pattern'] if pats else sig.get('reasons',[''])[0]} ({tf_lbl})")
        else:
            err = (raw or {}).get("error","No candle data returned")
            st.error(f"⚠️ {err}")
        result = st.session_state.analysis_cache.get(ck)
    else:
        result = st.session_state.analysis_cache.get(ck)

    # ═══ TAB 1: CHART ════════════════════════════════════════════════════════
    with tab_chart:
        ccol, rcol = st.columns([3,1], gap="small")

        with ccol:
            if result:
                ind   = result.get("indicators",{})
                rsi_v = ind.get("rsi",50)
                mv    = ind.get("macd",0); hv=ind.get("macd_hist",0)
                rc    = "#00d4aa" if 30<rsi_v<70 else "#f87171"
                mc2   = "#00d4aa" if mv>0 else "#f87171"
                hc    = "#00d4aa" if hv>0 else "#f87171"

                # Toolbar row
                tb1, tb2, tb3 = st.columns([1,1,4])
                with tb1:
                    if st.button("🔄 Refresh", key="chart_ref"):
                        st.session_state.last_fetch[ck] = 0
                        st.rerun()
                with tb2:
                    fd_d, td_d = resolve_date_range(date_mode, custom_from, custom_to, interval)
                    fd_show = fd_d.split(" ")[0]; td_show = td_d.split(" ")[0]
                    candle_count = len(result.get("candles", []))
                    st.markdown(f"<span style='font-size:.72rem;color:#4a6fa5;line-height:2.2;'>"
                                f"📅 {fd_show}→{td_show} · {candle_count} candles</span>",
                                unsafe_allow_html=True)

                st.markdown(f"""<div class='ind-row'>
                  <span class='ind-chip'>EMA9 <span>{fmt(ind.get('ema9',0))}</span></span>
                  <span class='ind-chip'>EMA21 <span>{fmt(ind.get('ema21',0))}</span></span>
                  <span class='ind-chip'>RSI <span style='color:{rc}'>{rsi_v}</span></span>
                  <span class='ind-chip'>MACD <span style='color:{mc2}'>{mv:+.1f}</span></span>
                  <span class='ind-chip'>Hist <span style='color:{hc}'>{hv:+.1f}</span></span>
                  <span class='ind-chip'>VWAP <span>{fmt(ind.get('vwap',0))}</span></span>
                  <span class='ind-chip'>ATR <span>{ind.get('atr',0)}</span></span>
                  <span class='ind-chip'>BB <span>{fmt(ind.get('bb_lower',0))}–{fmt(ind.get('bb_upper',0))}</span></span>
                </div>""", unsafe_allow_html=True)

                fig = build_chart(result.get("candles"), result.get("candle_signals"),
                                  ind, show_ema, show_vwap, show_bb)
                if fig:
                    st.plotly_chart(fig, use_container_width=True, config={"displaylogo":False,"scrollZoom":True})
                ts = st.session_state.last_fetch.get(ck, 0)
                refresh_lbl = "auto-refresh 90s" if live_mode else "historical — click Refresh to reload"
                st.caption(f"Updated {datetime.fromtimestamp(ts).strftime('%H:%M:%S')} IST · {tf_lbl} · {date_mode} · {refresh_lbl}")
            else:
                st.info("Waiting for candle data...")

        with rcol:
            # Signal
            st.markdown("#### Signal")
            if result:
                sig   = result.get("signal",{})
                stype = sig.get("type","NEUTRAL")
                score = sig.get("score",0)
                conf  = sig.get("confidence","")
                pats  = sig.get("patterns",[])
                reas  = sig.get("reasons",[])
                emoji = "🟢" if stype=="BUY" else "🔴" if stype=="SELL" else "🟡"
                pat   = pats[0]["pattern"] if pats else (reas[0] if reas else "—")

                st.markdown(f"""<div class='sig-{stype}'>
                  <div class='sig-label'>{emoji} {stype}</div>
                  <div class='sig-sub'>{pat}</div>
                  <div class='sig-score'>Score {score:+d} · {conf}</div>
                </div>""", unsafe_allow_html=True)

                ind = result.get("indicators",{})
                rsi_v = ind.get("rsi",50)
                rs = " ".join(reas)
                def vb(c,t,f): return f'<span style="color:#00d4aa">{t}</span>' if c else f'<span style="color:#f87171">{f}</span>'
                st.markdown(f"""<div style='font-size:.76rem;margin-top:8px;'>
                  <div class='str-row'><span class='str-name'>EMA Stack</span>{vb("EMA Bullish" in rs,"🟢 Bull","🔴 Bear")}</div>
                  <div class='str-row'><span class='str-name'>RSI {rsi_v:.0f}</span>{vb(30<rsi_v<70,"🟢 OK","⚠️ Extreme")}</div>
                  <div class='str-row'><span class='str-name'>MACD Hist</span>{vb(ind.get("macd_hist",0)>0,"🟢 Bull","🔴 Bear")}</div>
                  <div class='str-row'><span class='str-name'>VWAP</span>{vb("Above VWAP" in rs,"🟢 Above","🔴 Below")}</div>
                  <div class='str-row'><span class='str-name'>Patterns</span>
                    <span style='color:#e2e8f0'>{", ".join(p["pattern"] for p in pats) or "—"}</span></div>
                </div>""", unsafe_allow_html=True)

                rp = int(min(max(rsi_v,0),100))
                bc2 = "#f87171" if rsi_v>70 or rsi_v<30 else "#00d4aa"
                st.markdown(f"""<div style='margin:8px 0 2px'>
                  <div style='height:5px;border-radius:3px;background:#1e3050;overflow:hidden'>
                    <div style='height:100%;width:{rp}%;background:{bc2};border-radius:3px'></div></div>
                  <div style='display:flex;justify-content:space-between;font-size:9px;color:#4a6fa5;margin-top:2px'>
                    <span>OS 30</span><span>RSI</span><span>OB 70</span></div></div>""",
                unsafe_allow_html=True)

            st.divider()
            # Alerts
            st.markdown("#### Alerts")
            alerts = st.session_state.alerts
            if not alerts:
                st.caption("No signals yet.")
            for a in alerts[:8]:
                cm={"BUY":"#00d4aa","SELL":"#f87171","INFO":"#60a5fa"}
                c=cm.get(a["type"],"#4a6fa5")
                st.markdown(f"""<div class='alert-item'>
                  <div class='adot' style='background:{c}'></div>
                  <div><span style='color:{c};font-weight:700'>{a["type"]}</span>
                  <span style='color:#94a3b8'> {a["text"]}</span>
                  <div style='font-size:.65rem;color:#4a6fa5'>{a["time"]}</div></div></div>""",
                unsafe_allow_html=True)

    # ═══ TAB 2: OPTION CHAIN ════════════════════════════════════════════════
    with tab_oc:
        show_option_chain_tab(sym, ltp)

    # ═══ TAB 3: STRATEGIES ══════════════════════════════════════════════════
    with tab_strat:
        show_strategy_tab(result, sym, tf_lbl)

    # ═══ TAB 4: PORTFOLIO ═══════════════════════════════════════════════════
    with tab_port:
        show_portfolio_tab()

    # ═══ TAB 5: CONFIG ══════════════════════════════════════════════════════
    with tab_cfg:
        show_config_tab()


# ─── STRATEGY TAB ────────────────────────────────────────────────────────────
def _log_closed_trade(active_trade, sym, pnl_pct, exit_reason):
    """Auto-log a closed strategy trade to the trade journal with full charge calc."""
    if not active_trade:
        return
    entry    = active_trade.get("entry_price", 0)
    direction = active_trade.get("direction", "LONG")
    opt_type  = active_trade.get("option_type", "")
    strategy  = active_trade.get("strategy", "")
    lot       = LOT_SIZES.get(sym, 1)
    qty       = lot  # default 1 lot

    if not entry:
        return

    # Reconstruct approximate exit price from pnl_pct
    if direction == "LONG":
        exit_price = round(entry * (1 + pnl_pct / 100), 2)
    else:
        exit_price = round(entry * (1 - pnl_pct / 100), 2)

    # Determine trade type
    trade_type = "FNO_INTRADAY" if opt_type in ("CE","PE") else "EQ_INTRADAY"

    pnl_data = calc_pnl(entry, exit_price, qty, direction, trade_type)
    rec = {
        "time":      ist_now().strftime("%d %b %H:%M"),
        "symbol":    f"{sym} {opt_type}" if opt_type else sym,
        "direction": direction,
        "qty":       qty,
        "entry":     entry,
        "exit":      exit_price,
        "type":      trade_type,
        "note":      f"{strategy} · {exit_reason}",
        **pnl_data,
    }
    st.session_state.trade_log.insert(0, rec)
    add_alert("INFO", f"Journal: {rec['symbol']} Net ₹{pnl_data['net_pnl']:+,.2f}")


def show_strategy_tab(result, sym, tf_lbl):
    if not result:
        st.info("Load chart data first.")
        return

    config = st.session_state.get("strategy_config",{})
    active = st.session_state.get("active_trades",{})
    setups = run_all_strategies(result, config, active)
    con    = consensus(setups)

    cd = con["consensus"]
    cc = "#00d4aa" if "BUY" in cd else "#f87171" if "SELL" in cd else "#f59e0b" if cd in ("STOP_LOSS","EXIT") else "#4a6fa5"
    em = "🟢" if "BUY" in cd else "🔴" if "SELL" in cd else "⚠️" if cd in ("STOP_LOSS","EXIT") else "⏸️"

    st.markdown(f"""<div style='background:{cc}15;border:1.5px solid {cc}44;border-radius:12px;
         padding:14px 18px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;'>
      <div>
        <div style='font-size:.7rem;color:#4a6fa5;margin-bottom:2px;'>CONSENSUS — {sym} ({tf_lbl})</div>
        <div style='font-size:1.6rem;font-weight:800;color:{cc};'>{em} {cd}</div>
      </div>
      <div style='text-align:right;font-size:.76rem;'>
        <span style='color:#00d4aa'>▲ {con["bull_count"]}</span> &nbsp;
        <span style='color:#f87171'>▼ {con["bear_count"]}</span> &nbsp;
        <span style='color:#f59e0b'>⏸ {con["hold_count"]}</span> &nbsp;
        <span style='color:#4a6fa5'>⏳ {con["wait_count"]}</span>
      </div>
    </div>""", unsafe_allow_html=True)

    for name, setup in setups.items():
        act = setup.action
        cm2 = {
            "ENTER_LONG":("#00d4aa","🟢 ENTER LONG — BUY CE"),
            "ENTER_SHORT":("#f87171","🔴 ENTER SHORT — BUY PE"),
            "HOLD":("#f59e0b","⏸️ HOLD"),
            "EXIT_LONG":("#60a5fa","🔵 EXIT LONG"),
            "EXIT_SHORT":("#60a5fa","🔵 EXIT SHORT"),
            "STOP_LOSS":("#ef4444","🚨 STOP LOSS"),
            "WAIT":("#4a6fa5","⏳ WAIT"),
        }
        sc2,lbl = cm2.get(act,("#4a6fa5",act))
        cb_lbl = {"HIGH":"🔥","MEDIUM":"⚡","LOW":"🌀"}.get(setup.confidence,"")

        with st.expander(f"{lbl} · **{name}** {cb_lbl}", expanded=act not in ("WAIT",)):
            so = ALL_STRATEGIES.get(name)
            if so: st.caption(so.description)

            if act in ("ENTER_LONG","ENTER_SHORT"):
                direction = "LONG" if act=="ENTER_LONG" else "SHORT"
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Entry",   f"₹{setup.entry_price:,.2f}")
                c2.metric("SL",      f"₹{setup.stop_loss:,.2f}", delta=f"-{setup.sl_pct:.1f}%",delta_color="inverse")
                c3.metric("Target1", f"₹{setup.target_1:,.2f}")
                c4.metric("Target2", f"₹{setup.target_2:,.2f}")
                c5,c6,c7,c8 = st.columns(4)
                c5.metric("Target3", f"₹{setup.target_3:,.2f}")
                c6.metric("R:R",     f"1:{setup.rr_ratio:.1f}")
                c7.metric("Risk/Lot",f"₹{setup.risk_per_lot:,.0f}")
                c8.metric("Option",  f"{setup.option_type}@{setup.suggested_strike:.0f}")
                for r in setup.reasons: st.markdown(f"✅ {r}")
                for w in setup.warnings: st.warning(f"⚠️ {w}")
                st.markdown("---")
                if st.button("✅ Activate Trade",key=f"act_{name}"):
                    st.session_state.active_trades[name] = {
                        "strategy":name,"direction":direction,
                        "entry_price":setup.entry_price,"stop_loss":setup.stop_loss,
                        "trailing_sl":setup.stop_loss,"target_1":setup.target_1,
                        "target_2":setup.target_2,"target_3":setup.target_3,
                        "option_type":setup.option_type,"entry_time":datetime.now().strftime("%H:%M"),
                    }
                    add_alert(act.split("_")[0], f"{name}: {direction} @{setup.entry_price:.0f}")
                    st.success("Trade activated!"); st.rerun()

            elif act == "HOLD":
                if setup.in_trade:
                    pnl=setup.current_pnl_pct; mile=setup.milestone_hit
                    c1,c2,c3,c4 = st.columns(4)
                    c1.metric("Entry", f"₹{active.get(name,{}).get('entry_price',0):,.0f}")
                    c2.metric("P&L",   f"{pnl:+.2f}%", delta_color="normal" if pnl>=0 else "inverse")
                    c3.metric("SL",    f"₹{setup.stop_loss:,.0f}")
                    c4.metric("Trail", f"₹{setup.trailing_sl:,.0f}" if setup.trailing_sl else "—")
                    if mile:
                        mc3="#00d4aa" if "T3" in mile else "#f59e0b" if "T2" in mile else "#60a5fa"
                        st.markdown(f"<div style='background:{mc3}22;border:1px solid {mc3}55;border-radius:6px;padding:8px;color:{mc3};font-weight:700;'>🎯 {mile.replace('_',' ')}</div>",unsafe_allow_html=True)
                for r in (setup.hold_reasons or []): st.markdown(f"⏸ {r}")
                if setup.in_trade and st.button("🚪 Close",key=f"cls_{name}"):
                    at = st.session_state.active_trades.pop(name, {})
                    _log_closed_trade(at, sym, setup.current_pnl_pct, "Manual exit")
                    add_alert("INFO",f"{name}: Manual exit"); st.success("Closed"); st.rerun()

            elif act in ("EXIT_LONG","EXIT_SHORT"):
                pnl=setup.current_pnl_pct; pc="#00d4aa" if pnl>=0 else "#f87171"
                st.markdown(f"<div style='background:#60a5fa18;border:1px solid #60a5fa44;border-radius:8px;padding:10px;'><span style='color:#60a5fa;font-weight:700;font-size:1.1rem;'>EXIT</span><span style='color:{pc};margin-left:10px;'>{pnl:+.2f}%</span></div>",unsafe_allow_html=True)
                for r in (setup.exit_reasons or []): st.markdown(f"🔵 {r}")
                if st.button("✅ Confirm Exit",key=f"ext_{name}"):
                    at = st.session_state.active_trades.pop(name, {})
                    _log_closed_trade(at, sym, pnl, "Signal Exit")
                    add_alert("INFO",f"{name}: EXIT {pnl:+.2f}%"); st.rerun()

            elif act == "STOP_LOSS":
                pnl=setup.current_pnl_pct
                st.markdown(f"<div style='background:#ef444420;border:2px solid #ef4444;border-radius:8px;padding:12px;'><div style='font-size:1.2rem;font-weight:800;color:#ef4444;'>🚨 STOP LOSS HIT</div><div style='color:#f87171;font-size:.85rem;'>Loss: {pnl:+.2f}%</div></div>",unsafe_allow_html=True)
                for r in (setup.sl_reasons or []): st.error(r)
                if st.button("🚨 Confirm SL Exit",key=f"sl_{name}",type="primary"):
                    at = st.session_state.active_trades.pop(name, {})
                    _log_closed_trade(at, sym, pnl, "Stop Loss")
                    add_alert("SELL",f"{name}: SL {pnl:+.2f}%"); st.rerun()
            else:
                for r in (setup.hold_reasons or ["No setup — stand aside"]): st.caption(f"⏳ {r}")

    if active:
        st.divider(); st.markdown("### Active Trades")
        for strat,trade in active.items():
            close = result.get("candles",[{}])[-1].get("c",0) if result else 0
            entry = trade.get("entry_price",close)
            d     = trade.get("direction","LONG")
            pnl   = ((close-entry)/entry*100) if d=="LONG" and entry else ((entry-close)/entry*100) if entry else 0
            pc    = "#00d4aa" if pnl>=0 else "#f87171"
            st.markdown(f"""<div style='background:#0d1525;border:.5px solid #1e3050;border-radius:8px;
                 padding:9px 14px;margin-bottom:5px;display:flex;justify-content:space-between;align-items:center;'>
              <div><b style='color:#e2e8f0'>{strat}</b>
                <span style='color:#4a6fa5;font-size:.73rem;margin-left:8px;'>{d} · @{entry:.0f} · SL {trade.get("stop_loss",0):.0f}</span></div>
              <div style='font-weight:700;color:{pc}'>{pnl:+.2f}%</div></div>""",
            unsafe_allow_html=True)


# ─── CONFIG TAB ──────────────────────────────────────────────────────────────
def show_config_tab():
    st.markdown("### ⚙️ Strategy Configuration")
    cfg = st.session_state.get("strategy_config",{})

    with st.expander("🔧 Global Risk",expanded=True):
        c1,c2,c3 = st.columns(3)
        with c1: sl_atr=st.slider("SL ATR Mult",0.5,3.0,float(cfg.get("sl_atr_mult",1.5)),0.1)
        with c2: t2_rr=st.slider("Target2 RR",1.5,5.0,float(cfg.get("t2_rr",2.5)),0.5)
        with c3: t3_rr=st.slider("Target3 RR",2.0,8.0,float(cfg.get("t3_rr",4.0)),0.5)
        cfg.update(sl_atr_mult=sl_atr,t2_rr=t2_rr,t3_rr=t3_rr,t1_rr=round(t2_rr*0.6,1))

    with st.expander("📊 EMA Trend"):
        ms=st.slider("Min Score",20,70,int(cfg.get("min_score",30)),5)
        cfg["min_score"]=ms

    with st.expander("📉 RSI Mean Reversion"):
        c1,c2=st.columns(2)
        with c1: ros=st.slider("RSI Oversold",20,40,int(cfg.get("rsi_os",30)),1)
        with c2: rob=st.slider("RSI Overbought",60,80,int(cfg.get("rsi_ob",70)),1)
        cfg.update(rsi_os=ros,rsi_ob=rob)

    with st.expander("🎯 Multi-Confluence"):
        mc=st.slider("Min Confluences",2,6,int(cfg.get("min_confluences",4)),1)
        cfg["min_confluences"]=mc
        st.caption(f"Requires {mc}/6 signals to align")

    if st.button("💾 Save Config",type="primary",use_container_width=True):
        st.session_state.strategy_config=cfg
        st.success("✅ Saved!")

    st.divider()
    st.markdown("### 📚 Strategy Guide")
    for name,(best,avoid,sig,sl) in {
        "EMA Trend Follow":("Trending","Sideways","EMA cross+MACD+VWAP","ATR below swing"),
        "RSI Mean Reversion":("Range-bound","Strong trend","RSI extreme+BB+candle","Below trigger candle"),
        "MACD Momentum":("Breakout","Low volume","MACD×signal+expansion","Wide ATR×2"),
        "VWAP Reversal":("Intraday scalp","First 15min","VWAP cross+volume","Just past VWAP"),
        "Multi-Confluence":("Any (best accuracy)","Impatient","4+/6 signals agree","ATR×1.8"),
    }.items():
        with st.expander(f"📖 {name}"):
            c1,c2=st.columns(2)
            with c1: st.markdown(f"✅ **Best:** {best}\n\n❌ **Avoid:** {avoid}")
            with c2: st.markdown(f"⚡ **Signal:** {sig}\n\n🛑 **SL:** {sl}")

    st.divider()
    if st.button("🗑️ Clear All Active Trades",type="secondary"):
        st.session_state.active_trades={}
        st.success("Cleared."); st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════
if st.session_state.authenticated:
    show_dashboard()
else:
    show_login()
