"""
ta_engine.py — Technical Analysis Engine
Computes indicators and generates BUY/SELL signals from OHLCV data.
All functions are pure Python (no external TA libs needed).
"""

from __future__ import annotations
from typing import TypedDict

# ─── TYPES ───────────────────────────────────────────────────────────────────
class OHLCV(TypedDict):
    timestamp: list[int]
    open:      list[float]
    high:      list[float]
    low:       list[float]
    close:     list[float]
    volume:    list[int]

class Signal(TypedDict):
    type:       str          # BUY | SELL | NEUTRAL
    pattern:    str
    strength:   float        # 0–100
    confidence: str          # HIGH | MEDIUM | LOW

class Indicators(TypedDict):
    ema9:   float
    ema21:  float
    ema50:  float
    rsi:    float
    macd:   float
    signal_line: float
    macd_hist:   float
    bb_upper: float
    bb_mid:   float
    bb_lower: float
    vwap:   float
    atr:    float


# ─── MOVING AVERAGES ─────────────────────────────────────────────────────────
def ema(prices: list[float], period: int) -> list[float]:
    """Exponential Moving Average."""
    if len(prices) < period:
        return [prices[-1]] * len(prices)
    k = 2 / (period + 1)
    result = [sum(prices[:period]) / period]
    for p in prices[period:]:
        result.append(p * k + result[-1] * (1 - k))
    # Pad front with None-equivalent (use first EMA value)
    padded = [result[0]] * (period - 1) + result
    return padded


def sma(prices: list[float], period: int) -> list[float]:
    """Simple Moving Average."""
    result = []
    for i in range(len(prices)):
        if i < period - 1:
            result.append(prices[i])
        else:
            result.append(sum(prices[i - period + 1:i + 1]) / period)
    return result


# ─── RSI ─────────────────────────────────────────────────────────────────────
def rsi(closes: list[float], period: int = 14) -> list[float]:
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return [50.0] * len(closes)
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    result = [50.0] * (period + 1)
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs  = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi_val = 100 - (100 / (1 + rs))
        result.append(round(rsi_val, 2))
    return result


# ─── MACD ────────────────────────────────────────────────────────────────────
def macd(closes: list[float], fast=12, slow=26, signal=9) -> tuple[list, list, list]:
    """Returns (macd_line, signal_line, histogram)."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [round(f - s, 2) for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal)
    histogram = [round(m - s, 2) for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, histogram


# ─── BOLLINGER BANDS ─────────────────────────────────────────────────────────
def bollinger(closes: list[float], period=20, stddev=2.0) -> tuple[list, list, list]:
    """Returns (upper, mid, lower)."""
    mid_band = sma(closes, period)
    upper, lower = [], []
    for i in range(len(closes)):
        if i < period - 1:
            upper.append(closes[i])
            lower.append(closes[i])
        else:
            window = closes[i - period + 1:i + 1]
            mean = sum(window) / period
            variance = sum((x - mean) ** 2 for x in window) / period
            std = variance ** 0.5
            upper.append(round(mean + stddev * std, 2))
            lower.append(round(mean - stddev * std, 2))
    return upper, mid_band, lower


# ─── VWAP ────────────────────────────────────────────────────────────────────
def vwap(highs: list[float], lows: list[float],
         closes: list[float], volumes: list[int]) -> list[float]:
    """Volume Weighted Average Price."""
    result = []
    cum_tpv = 0.0
    cum_vol = 0
    for h, l, c, v in zip(highs, lows, closes, volumes):
        tp = (h + l + c) / 3
        cum_tpv += tp * v
        cum_vol += v
        result.append(round(cum_tpv / cum_vol if cum_vol else c, 2))
    return result


# ─── ATR ─────────────────────────────────────────────────────────────────────
def atr(highs: list[float], lows: list[float],
        closes: list[float], period=14) -> list[float]:
    """Average True Range."""
    trs = []
    for i in range(len(closes)):
        if i == 0:
            trs.append(highs[i] - lows[i])
        else:
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i]  - closes[i - 1]),
            )
            trs.append(tr)
    result = [trs[0]]
    k = 1 / period
    for tr in trs[1:]:
        result.append(tr * k + result[-1] * (1 - k))
    return [round(v, 2) for v in result]


# ─── CANDLE PATTERN DETECTION ────────────────────────────────────────────────
def detect_patterns(ohlcv: OHLCV, idx: int) -> list[dict]:
    """
    Detect candle patterns at candle index `idx`.
    Returns list of { pattern, direction } dicts.
    """
    opens  = ohlcv["open"]
    highs  = ohlcv["high"]
    lows   = ohlcv["low"]
    closes = ohlcv["close"]

    patterns = []
    if idx < 2:
        return patterns

    o, h, l, c = opens[idx], highs[idx], lows[idx], closes[idx]
    po, ph, pl, pc = opens[idx-1], highs[idx-1], lows[idx-1], closes[idx-1]
    ppo, pph, ppl, ppc = opens[idx-2], highs[idx-2], lows[idx-2], closes[idx-2]

    body = abs(c - o)
    full_range = h - l if h != l else 1
    body_pct = body / full_range

    # Doji
    if body_pct < 0.1:
        patterns.append({"pattern": "Doji", "direction": "NEUTRAL"})

    # Bullish Engulfing
    if pc < po and c > o and c > po and o < pc:
        patterns.append({"pattern": "Bullish Engulfing", "direction": "BUY"})

    # Bearish Engulfing
    if pc > po and c < o and c < po and o > pc:
        patterns.append({"pattern": "Bearish Engulfing", "direction": "SELL"})

    # Hammer
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    if lower_wick > 2 * body and upper_wick < body * 0.3 and c > o:
        patterns.append({"pattern": "Hammer", "direction": "BUY"})

    # Shooting Star
    if upper_wick > 2 * body and lower_wick < body * 0.3 and c < o:
        patterns.append({"pattern": "Shooting Star", "direction": "SELL"})

    # Morning Star (3-candle)
    mid_body = abs(pc - po)
    if ppc > ppo and mid_body < (abs(ppc - ppo) * 0.5) and c > o and c > (ppo + ppc) / 2:
        patterns.append({"pattern": "Morning Star", "direction": "BUY"})

    # Evening Star
    if ppc < ppo and mid_body < (abs(ppc - ppo) * 0.5) and c < o and c < (ppo + ppc) / 2:
        patterns.append({"pattern": "Evening Star", "direction": "SELL"})

    # Marubozu Bullish
    if body_pct > 0.9 and c > o:
        patterns.append({"pattern": "Bullish Marubozu", "direction": "BUY"})

    # Marubozu Bearish
    if body_pct > 0.9 and c < o:
        patterns.append({"pattern": "Bearish Marubozu", "direction": "SELL"})

    return patterns


# ─── MAIN ANALYSIS FUNCTION ──────────────────────────────────────────────────
def analyse(ohlcv: OHLCV) -> dict:
    """
    Full technical analysis on OHLCV data.
    Returns indicators + signal for the latest candle.
    """
    opens   = [float(x) for x in ohlcv.get("open",  [])]
    highs   = [float(x) for x in ohlcv.get("high",  [])]
    lows    = [float(x) for x in ohlcv.get("low",   [])]
    closes  = [float(x) for x in ohlcv.get("close", [])]
    volumes = [int(x)   for x in ohlcv.get("volume", [])]
    timestamps = ohlcv.get("timestamp", list(range(len(closes))))

    n = len(closes)
    if n < 5:
        return {"error": "Not enough candle data (need ≥5 candles)"}

    # Compute indicators
    ema9_series  = ema(closes, 9)
    ema21_series = ema(closes, 21)
    ema50_series = ema(closes, 50)
    rsi_series   = rsi(closes, 14)
    macd_line, signal_line, histogram = macd(closes)
    bb_upper, bb_mid, bb_lower = bollinger(closes)
    vwap_series  = vwap(highs, lows, closes, volumes)
    atr_series   = atr(highs, lows, closes)

    # Latest values
    idx = n - 1
    ind: Indicators = {
        "ema9":        round(ema9_series[idx], 2),
        "ema21":       round(ema21_series[idx], 2),
        "ema50":       round(ema50_series[idx], 2),
        "rsi":         rsi_series[idx],
        "macd":        macd_line[idx],
        "signal_line": signal_line[idx],
        "macd_hist":   histogram[idx],
        "bb_upper":    bb_upper[idx],
        "bb_mid":      bb_mid[idx],
        "bb_lower":    bb_lower[idx],
        "vwap":        round(vwap_series[idx], 2),
        "atr":         atr_series[idx],
    }

    # Pattern detection (last 3 candles)
    all_patterns = detect_patterns(
        {"open": opens, "high": highs, "low": lows, "close": closes},
        idx
    )

    # Signal scoring
    score = 0
    reasons = []
    close = closes[idx]

    # EMA alignment
    if ema9_series[idx] > ema21_series[idx] > ema50_series[idx]:
        score += 25
        reasons.append("EMA Bullish Stack")
    elif ema9_series[idx] < ema21_series[idx] < ema50_series[idx]:
        score -= 25
        reasons.append("EMA Bearish Stack")

    # EMA crossover
    if idx > 0 and ema9_series[idx] > ema21_series[idx] and ema9_series[idx-1] <= ema21_series[idx-1]:
        score += 20
        reasons.append("EMA9 x EMA21 Bull Cross")
    elif idx > 0 and ema9_series[idx] < ema21_series[idx] and ema9_series[idx-1] >= ema21_series[idx-1]:
        score -= 20
        reasons.append("EMA9 x EMA21 Bear Cross")

    # RSI
    rsi_val = rsi_series[idx]
    if 50 < rsi_val < 70:
        score += 10
        reasons.append(f"RSI Bullish ({rsi_val})")
    elif rsi_val > 70:
        score -= 5
        reasons.append(f"RSI Overbought ({rsi_val})")
    elif 30 < rsi_val < 50:
        score -= 10
        reasons.append(f"RSI Bearish ({rsi_val})")
    elif rsi_val < 30:
        score += 5
        reasons.append(f"RSI Oversold ({rsi_val})")

    # MACD
    if histogram[idx] > 0 and (idx == 0 or histogram[idx] > histogram[idx-1]):
        score += 15
        reasons.append("MACD Bull Momentum")
    elif histogram[idx] < 0 and (idx == 0 or histogram[idx] < histogram[idx-1]):
        score -= 15
        reasons.append("MACD Bear Momentum")

    # VWAP
    if close > vwap_series[idx]:
        score += 10
        reasons.append("Price Above VWAP")
    else:
        score -= 10
        reasons.append("Price Below VWAP")

    # Bollinger Band position
    bb_pos = (close - bb_lower[idx]) / (bb_upper[idx] - bb_lower[idx] + 0.001)
    if bb_pos > 0.8:
        score -= 5
        reasons.append("Near BB Upper (overbought)")
    elif bb_pos < 0.2:
        score += 5
        reasons.append("Near BB Lower (oversold bounce)")

    # Candle patterns
    for p in all_patterns:
        if p["direction"] == "BUY":
            score += 15
            reasons.append(p["pattern"])
        elif p["direction"] == "SELL":
            score -= 15
            reasons.append(p["pattern"])

    # Final signal
    if score >= 30:
        signal_type = "BUY"
        confidence  = "HIGH" if score >= 55 else "MEDIUM"
    elif score <= -30:
        signal_type = "SELL"
        confidence  = "HIGH" if score <= -55 else "MEDIUM"
    else:
        signal_type = "NEUTRAL"
        confidence  = "LOW"

    # Build per-candle signal list (for chart overlay)
    candle_signals = []
    for i in range(2, n):
        pats = detect_patterns(
            {"open": opens, "high": highs, "low": lows, "close": closes}, i
        )
        for p in pats:
            candle_signals.append({
                "index":   i,
                "pattern": p["pattern"],
                "direction": p["direction"],
                "price":   closes[i],
                "high":    highs[i],
                "low":     lows[i],
            })

    # Serialise full candle data for charting
    candles = [
        {
            "t": timestamps[i],
            "o": opens[i],
            "h": highs[i],
            "l": lows[i],
            "c": closes[i],
            "v": volumes[i] if i < len(volumes) else 0,
            "ema9":  round(ema9_series[i], 2),
            "ema21": round(ema21_series[i], 2),
            "vwap":  round(vwap_series[i], 2),
            "macd_hist": histogram[i],
            "rsi":   rsi_series[i],
        }
        for i in range(n)
    ]

    return {
        "indicators":     ind,
        "signal": {
            "type":       signal_type,
            "score":      score,
            "confidence": confidence,
            "reasons":    reasons,
            "patterns":   all_patterns,
        },
        "candles":        candles,
        "candle_signals": candle_signals,
    }
