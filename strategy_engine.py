"""
strategy_engine.py — Trade Strategy Engine
Converts raw indicator data into structured trade decisions:
  ENTER LONG / ENTER SHORT / HOLD / EXIT / STOP LOSS HIT
Supports multiple configurable strategies.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Literal
import math

# ─── TRADE DECISION MODEL ────────────────────────────────────────────────────

Action = Literal["ENTER_LONG", "ENTER_SHORT", "HOLD", "EXIT_LONG", "EXIT_SHORT", "STOP_LOSS", "WAIT"]

@dataclass
class TradeSetup:
    action:        Action
    strategy_name: str
    confidence:    Literal["HIGH", "MEDIUM", "LOW"]
    score:         int                    # net score -100..+100

    # Price levels
    entry_price:   float = 0.0
    stop_loss:     float = 0.0
    target_1:      float = 0.0           # 1:1.5 RR
    target_2:      float = 0.0           # 1:2.5 RR
    target_3:      float = 0.0           # 1:4   RR

    # Risk
    risk_per_lot:  float = 0.0           # ₹ risk from entry to SL
    rr_ratio:      float = 0.0           # Risk:Reward to T2
    sl_pct:        float = 0.0           # SL % from entry

    # Options recommendation
    option_type:   str = ""              # CE or PE
    suggested_strike: float = 0.0

    # Context
    reasons:       list[str] = field(default_factory=list)
    warnings:      list[str] = field(default_factory=list)
    hold_reasons:  list[str] = field(default_factory=list)
    exit_reasons:  list[str] = field(default_factory=list)
    sl_reasons:    list[str] = field(default_factory=list)

    # Trade management (if in a trade)
    in_trade:         bool  = False
    trade_direction:  str   = ""         # LONG or SHORT
    trade_entry:      float = 0.0
    current_pnl_pct:  float = 0.0
    trailing_sl:      float = 0.0
    milestone_hit:    str   = ""         # T1_HIT / T2_HIT / T3_HIT

    def to_dict(self) -> dict:
        return asdict(self)


# ─── STRATEGY BASE CLASS ──────────────────────────────────────────────────────

class BaseStrategy:
    name = "Base"
    description = ""

    # Configurable defaults (overridden by user config)
    sl_atr_mult:  float = 1.5    # SL = entry ± ATR * mult
    t1_rr:        float = 1.5    # Target1 RR
    t2_rr:        float = 2.5    # Target2 RR
    t3_rr:        float = 4.0    # Target3 RR
    min_score:    int   = 30     # Min score to enter
    rsi_ob:       float = 68     # RSI overbought
    rsi_os:       float = 32     # RSI oversold

    def compute(self, ind: dict, candles: list[dict], patterns: list[dict],
                reasons: list[str], score: int, config: dict,
                active_trade: dict | None = None) -> TradeSetup:
        raise NotImplementedError

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _levels(self, entry: float, atr: float, direction: str, config: dict) -> dict:
        """Compute SL and targets from entry + ATR."""
        sl_mult = config.get("sl_atr_mult", self.sl_atr_mult)
        t1_rr   = config.get("t1_rr", self.t1_rr)
        t2_rr   = config.get("t2_rr", self.t2_rr)
        t3_rr   = config.get("t3_rr", self.t3_rr)

        sl_dist = atr * sl_mult
        if direction == "LONG":
            sl = round(entry - sl_dist, 2)
            t1 = round(entry + sl_dist * t1_rr, 2)
            t2 = round(entry + sl_dist * t2_rr, 2)
            t3 = round(entry + sl_dist * t3_rr, 2)
        else:
            sl = round(entry + sl_dist, 2)
            t1 = round(entry - sl_dist * t1_rr, 2)
            t2 = round(entry - sl_dist * t2_rr, 2)
            t3 = round(entry - sl_dist * t3_rr, 2)

        risk     = sl_dist
        rr_ratio = round(sl_dist * t2_rr / risk, 2) if risk else 0
        sl_pct   = round(sl_dist / entry * 100, 2)
        return dict(sl=sl, t1=t1, t2=t2, t3=t3,
                    risk=round(risk, 2), rr=rr_ratio, sl_pct=sl_pct)

    def _suggest_strike(self, entry: float, direction: str, atm_gap: float = 50) -> float:
        """Round to nearest ATM strike then shift one OTM."""
        atm = round(entry / atm_gap) * atm_gap
        if direction == "LONG":
            return atm              # ATM CE — slight OTM gives leverage
        else:
            return atm              # ATM PE

    def _check_stop_loss(self, active: dict, close: float, ind: dict) -> tuple[bool, list[str]]:
        """Returns (sl_hit, reasons)."""
        reasons = []
        if not active:
            return False, []
        direction = active.get("direction", "LONG")
        sl = active.get("stop_loss", 0)
        if direction == "LONG" and close <= sl:
            reasons.append(f"Price {close} broke below SL {sl}")
            return True, reasons
        if direction == "SHORT" and close >= sl:
            reasons.append(f"Price {close} broke above SL {sl}")
            return True, reasons

        # Trailing SL breach
        trailing = active.get("trailing_sl", 0)
        if trailing:
            if direction == "LONG" and close <= trailing:
                reasons.append(f"Trailing SL {trailing} breached")
                return True, reasons
            if direction == "SHORT" and close >= trailing:
                reasons.append(f"Trailing SL {trailing} breached")
                return True, reasons

        return False, []

    def _check_exit(self, active: dict, close: float, ind: dict,
                    patterns: list[dict], score: int) -> tuple[bool, list[str]]:
        """Check if we should exit an active trade."""
        reasons = []
        if not active:
            return False, []
        direction = active.get("direction", "LONG")
        t2        = active.get("target_2", 0)
        t3        = active.get("target_3", 0)
        entry     = active.get("entry_price", close)

        # Target 3 hit → full exit
        if direction == "LONG" and close >= t3:
            reasons.append(f"Target 3 hit ({t3:.0f}) — full exit recommended")
            return True, reasons
        if direction == "SHORT" and close <= t3:
            reasons.append(f"Target 3 hit ({t3:.0f}) — full exit recommended")
            return True, reasons

        # Signal reversal
        if direction == "LONG" and score <= -30:
            reasons.append("Signal reversed to SELL — exit long")
            return True, reasons
        if direction == "SHORT" and score >= 30:
            reasons.append("Signal reversed to BUY — exit short")
            return True, reasons

        # RSI reversal at extreme
        rsi_v = ind.get("rsi", 50)
        if direction == "LONG" and rsi_v > 75:
            reasons.append(f"RSI overbought ({rsi_v:.1f}) — consider exiting")
            return True, reasons
        if direction == "SHORT" and rsi_v < 25:
            reasons.append(f"RSI oversold ({rsi_v:.1f}) — consider exiting")
            return True, reasons

        # Reversal candle pattern
        reversal_pats = {p["pattern"] for p in patterns}
        if direction == "LONG" and reversal_pats & {"Bearish Engulfing", "Evening Star", "Shooting Star", "Bearish Marubozu"}:
            pat = (reversal_pats & {"Bearish Engulfing", "Evening Star", "Shooting Star", "Bearish Marubozu"}).pop()
            reasons.append(f"Reversal pattern: {pat}")
            return True, reasons
        if direction == "SHORT" and reversal_pats & {"Bullish Engulfing", "Morning Star", "Hammer", "Bullish Marubozu"}:
            pat = (reversal_pats & {"Bullish Engulfing", "Morning Star", "Hammer", "Bullish Marubozu"}).pop()
            reasons.append(f"Reversal pattern: {pat}")
            return True, reasons

        return False, []

    def _trailing_sl(self, active: dict, close: float, atr: float, direction: str, config: dict) -> float:
        """Update trailing SL. Move SL up/down as trade goes in our favour."""
        entry    = active.get("entry_price", close)
        t1       = active.get("target_1", 0)
        t2       = active.get("target_2", 0)
        old_sl   = active.get("stop_loss", 0)
        trail_sl = active.get("trailing_sl", old_sl)

        if direction == "LONG":
            # Once T1 hit, move SL to entry (breakeven)
            if close >= t1 and trail_sl < entry:
                return round(entry, 2)
            # Once T2 hit, trail at 1 ATR below current close
            if close >= t2:
                new_trail = round(close - atr * 1.0, 2)
                return max(trail_sl, new_trail)
        else:
            if close <= t1 and trail_sl > entry:
                return round(entry, 2)
            if close <= t2:
                new_trail = round(close + atr * 1.0, 2)
                return min(trail_sl, new_trail)

        return trail_sl

    def _milestone(self, active: dict, close: float) -> str:
        if not active:
            return ""
        t1, t2, t3 = active.get("target_1", 0), active.get("target_2", 0), active.get("target_3", 0)
        direction  = active.get("direction", "LONG")
        if direction == "LONG":
            if close >= t3: return "T3_HIT"
            if close >= t2: return "T2_HIT"
            if close >= t1: return "T1_HIT"
        else:
            if close <= t3: return "T3_HIT"
            if close <= t2: return "T2_HIT"
            if close <= t1: return "T1_HIT"
        return ""

    def _pnl_pct(self, active: dict, close: float) -> float:
        entry = active.get("entry_price", close)
        direction = active.get("direction", "LONG")
        if not entry:
            return 0.0
        if direction == "LONG":
            return round((close - entry) / entry * 100, 2)
        return round((entry - close) / entry * 100, 2)


# ─── STRATEGY 1: EMA TREND FOLLOWING ─────────────────────────────────────────

class EMATrendStrategy(BaseStrategy):
    name        = "EMA Trend Follow"
    description = "Enters on EMA9 × EMA21 crossover confirmed by MACD and VWAP. Best for trending markets."
    sl_atr_mult = 1.5

    def compute(self, ind, candles, patterns, reasons, score, config, active_trade=None) -> TradeSetup:
        close  = candles[-1]["c"] if candles else ind.get("vwap", 0)
        atr    = ind.get("atr", 10)
        ema9   = ind.get("ema9",  close)
        ema21  = ind.get("ema21", close)
        ema50  = ind.get("ema50", close)
        macd_h = ind.get("macd_hist", 0)
        rsi_v  = ind.get("rsi", 50)
        vwap_v = ind.get("vwap", close)

        setup = TradeSetup(action="WAIT", strategy_name=self.name,
                           confidence="LOW", score=score,
                           entry_price=close, reasons=list(reasons))

        # ── STOP LOSS CHECK (highest priority) ────────────────────────────
        if active_trade and active_trade.get("strategy") == self.name:
            sl_hit, sl_r = self._check_stop_loss(active_trade, close, ind)
            if sl_hit:
                setup.action      = "STOP_LOSS"
                setup.sl_reasons  = sl_r
                setup.in_trade    = True
                setup.trade_direction = active_trade.get("direction", "")
                setup.current_pnl_pct = self._pnl_pct(active_trade, close)
                return setup

        # ── EXIT CHECK ────────────────────────────────────────────────────
        if active_trade and active_trade.get("strategy") == self.name:
            exit_now, exit_r = self._check_exit(active_trade, close, ind, patterns, score)
            if exit_now:
                direction = active_trade.get("direction", "LONG")
                setup.action       = "EXIT_LONG" if direction == "LONG" else "EXIT_SHORT"
                setup.exit_reasons = exit_r
                setup.in_trade     = True
                setup.trade_direction = direction
                setup.current_pnl_pct = self._pnl_pct(active_trade, close)
                setup.trailing_sl  = self._trailing_sl(active_trade, close, atr, direction, config)
                setup.milestone_hit = self._milestone(active_trade, close)
                return setup

        # ── HOLD CHECK ────────────────────────────────────────────────────
        if active_trade and active_trade.get("strategy") == self.name:
            direction = active_trade.get("direction", "LONG")
            t_sl  = self._trailing_sl(active_trade, close, atr, direction, config)
            mile  = self._milestone(active_trade, close)
            hold_r = [f"Trend intact — {direction} trade active"]
            if mile == "T1_HIT":  hold_r.append("✅ Target 1 hit — SL moved to breakeven")
            if mile == "T2_HIT":  hold_r.append("✅ Target 2 hit — trailing SL activated")
            if close > ema9 > ema21 and direction == "LONG":
                hold_r.append("EMA9 > EMA21 — uptrend continuing")
            if close < ema9 < ema21 and direction == "SHORT":
                hold_r.append("EMA9 < EMA21 — downtrend continuing")

            setup.action        = "HOLD"
            setup.hold_reasons  = hold_r
            setup.in_trade      = True
            setup.trade_direction = direction
            setup.current_pnl_pct = self._pnl_pct(active_trade, close)
            setup.trailing_sl   = t_sl
            setup.milestone_hit = mile
            setup.stop_loss     = active_trade.get("stop_loss", 0)
            setup.target_1      = active_trade.get("target_1", 0)
            setup.target_2      = active_trade.get("target_2", 0)
            setup.target_3      = active_trade.get("target_3", 0)
            return setup

        # ── ENTRY CHECK ───────────────────────────────────────────────────
        bull_cross = (ema9 > ema21 and
                      len(candles) >= 2 and candles[-2]["ema9"] <= candles[-2]["ema21"])
        bear_cross = (ema9 < ema21 and
                      len(candles) >= 2 and candles[-2]["ema9"] >= candles[-2]["ema21"])

        warnings = []
        if rsi_v > self.rsi_ob: warnings.append(f"RSI overbought ({rsi_v:.0f}) — wait for pullback")
        if rsi_v < self.rsi_os: warnings.append(f"RSI oversold ({rsi_v:.0f}) — short entry risky")

        min_score = config.get("min_score", self.min_score)

        # LONG entry
        if (bull_cross or (score >= min_score and ema9 > ema21 > ema50)) and macd_h > 0 and close > vwap_v:
            lv = self._levels(close, atr, "LONG", config)
            setup.action        = "ENTER_LONG"
            setup.confidence    = "HIGH" if score >= 55 else "MEDIUM"
            setup.stop_loss     = lv["sl"]
            setup.target_1      = lv["t1"]
            setup.target_2      = lv["t2"]
            setup.target_3      = lv["t3"]
            setup.risk_per_lot  = lv["risk"]
            setup.rr_ratio      = lv["rr"]
            setup.sl_pct        = lv["sl_pct"]
            setup.option_type   = "CE"
            setup.suggested_strike = self._suggest_strike(close, "LONG")
            setup.warnings      = warnings
            if bull_cross: setup.reasons.insert(0, "EMA9 × EMA21 Bullish Crossover")

        # SHORT entry
        elif (bear_cross or (score <= -min_score and ema9 < ema21 < ema50)) and macd_h < 0 and close < vwap_v:
            lv = self._levels(close, atr, "SHORT", config)
            setup.action        = "ENTER_SHORT"
            setup.confidence    = "HIGH" if score <= -55 else "MEDIUM"
            setup.stop_loss     = lv["sl"]
            setup.target_1      = lv["t1"]
            setup.target_2      = lv["t2"]
            setup.target_3      = lv["t3"]
            setup.risk_per_lot  = lv["risk"]
            setup.rr_ratio      = lv["rr"]
            setup.sl_pct        = lv["sl_pct"]
            setup.option_type   = "PE"
            setup.suggested_strike = self._suggest_strike(close, "SHORT")
            setup.warnings      = warnings
            if bear_cross: setup.reasons.insert(0, "EMA9 × EMA21 Bearish Crossover")
        else:
            setup.action     = "WAIT"
            setup.hold_reasons = ["No crossover or confirmation missing — wait for setup"]
            if not (macd_h > 0 or macd_h < 0): setup.hold_reasons.append("MACD flat — no momentum")
            if close < vwap_v and score > 0:    setup.hold_reasons.append("Price below VWAP — wait for reclaim")
            if close > vwap_v and score < 0:    setup.hold_reasons.append("Price above VWAP — wait for breakdown")

        return setup


# ─── STRATEGY 2: RSI MEAN REVERSION ──────────────────────────────────────────

class RSIMeanReversionStrategy(BaseStrategy):
    name        = "RSI Mean Reversion"
    description = "Buys oversold dips and shorts overbought bounces. Best for range-bound / sideways markets."
    sl_atr_mult = 1.2
    rsi_ob      = 70
    rsi_os      = 30

    def compute(self, ind, candles, patterns, reasons, score, config, active_trade=None) -> TradeSetup:
        close  = candles[-1]["c"] if candles else ind.get("vwap", 0)
        atr    = ind.get("atr", 10)
        rsi_v  = ind.get("rsi", 50)
        bb_lo  = ind.get("bb_lower", close * 0.98)
        bb_hi  = ind.get("bb_upper", close * 1.02)
        bb_mid = ind.get("bb_mid",   close)

        setup = TradeSetup(action="WAIT", strategy_name=self.name,
                           confidence="LOW", score=score,
                           entry_price=close, reasons=list(reasons))

        rsi_ob = config.get("rsi_ob", self.rsi_ob)
        rsi_os = config.get("rsi_os", self.rsi_os)

        if active_trade and active_trade.get("strategy") == self.name:
            sl_hit, sl_r = self._check_stop_loss(active_trade, close, ind)
            if sl_hit:
                setup.action     = "STOP_LOSS"
                setup.sl_reasons = sl_r
                setup.in_trade   = True
                setup.trade_direction = active_trade.get("direction", "")
                setup.current_pnl_pct = self._pnl_pct(active_trade, close)
                return setup

            exit_now, exit_r = self._check_exit(active_trade, close, ind, patterns, score)
            direction = active_trade.get("direction", "LONG")
            # RSI mean-reversion specific exit: RSI returned to mid zone
            if direction == "LONG" and 45 < rsi_v < 60:
                exit_r.append(f"RSI returned to mid zone ({rsi_v:.0f}) — take profit")
                exit_now = True
            if direction == "SHORT" and 40 < rsi_v < 55:
                exit_r.append(f"RSI returned to mid zone ({rsi_v:.0f}) — take profit")
                exit_now = True

            if exit_now:
                setup.action       = "EXIT_LONG" if direction == "LONG" else "EXIT_SHORT"
                setup.exit_reasons = exit_r
                setup.in_trade     = True
                setup.trade_direction = direction
                setup.current_pnl_pct = self._pnl_pct(active_trade, close)
                return setup

            mile = self._milestone(active_trade, close)
            setup.action       = "HOLD"
            setup.hold_reasons = [f"Mean reversion in progress — RSI {rsi_v:.0f}",
                                  f"Target: BB mid {bb_mid:.0f}"]
            if mile: setup.hold_reasons.append(f"✅ {mile.replace('_', ' ')}")
            setup.in_trade     = True
            setup.trade_direction = direction
            setup.current_pnl_pct = self._pnl_pct(active_trade, close)
            setup.trailing_sl  = self._trailing_sl(active_trade, close, atr, direction, config)
            setup.milestone_hit = mile
            setup.stop_loss    = active_trade.get("stop_loss", 0)
            setup.target_1     = active_trade.get("target_1", 0)
            setup.target_2     = active_trade.get("target_2", 0)
            setup.target_3     = active_trade.get("target_3", 0)
            return setup

        pat_names = {p["pattern"] for p in patterns}

        # LONG: RSI oversold + near BB lower + bullish candle
        if (rsi_v < rsi_os and close <= bb_lo * 1.005 and
                pat_names & {"Hammer", "Bullish Engulfing", "Morning Star", "Doji"}):
            lv = self._levels(close, atr, "LONG", config)
            setup.action       = "ENTER_LONG"
            setup.confidence   = "HIGH" if rsi_v < 25 else "MEDIUM"
            setup.stop_loss    = lv["sl"]
            setup.target_1     = lv["t1"]
            setup.target_2     = round(bb_mid, 2)   # target mid band
            setup.target_3     = round(bb_hi, 2)    # target upper band
            setup.risk_per_lot = lv["risk"]
            setup.rr_ratio     = lv["rr"]
            setup.sl_pct       = lv["sl_pct"]
            setup.option_type  = "CE"
            setup.suggested_strike = self._suggest_strike(close, "LONG")
            setup.reasons.insert(0, f"RSI Oversold ({rsi_v:.0f}) + BB Lower bounce")
            setup.warnings     = []

        # SHORT: RSI overbought + near BB upper + bearish candle
        elif (rsi_v > rsi_ob and close >= bb_hi * 0.995 and
              pat_names & {"Shooting Star", "Bearish Engulfing", "Evening Star", "Doji"}):
            lv = self._levels(close, atr, "SHORT", config)
            setup.action       = "ENTER_SHORT"
            setup.confidence   = "HIGH" if rsi_v > 75 else "MEDIUM"
            setup.stop_loss    = lv["sl"]
            setup.target_1     = lv["t1"]
            setup.target_2     = round(bb_mid, 2)
            setup.target_3     = round(bb_lo, 2)
            setup.risk_per_lot = lv["risk"]
            setup.rr_ratio     = lv["rr"]
            setup.sl_pct       = lv["sl_pct"]
            setup.option_type  = "PE"
            setup.suggested_strike = self._suggest_strike(close, "SHORT")
            setup.reasons.insert(0, f"RSI Overbought ({rsi_v:.0f}) + BB Upper rejection")
        else:
            w = []
            if rsi_v > rsi_os and rsi_v < rsi_ob:
                w.append(f"RSI {rsi_v:.0f} in neutral zone — wait for extreme (< {rsi_os} or > {rsi_ob})")
            setup.hold_reasons = w or ["Waiting for RSI extreme + BB band touch + candle confirmation"]

        return setup


# ─── STRATEGY 3: MACD MOMENTUM ───────────────────────────────────────────────

class MACDMomentumStrategy(BaseStrategy):
    name        = "MACD Momentum"
    description = "Rides momentum on MACD histogram expansion. Best for breakout / strong trend days."
    sl_atr_mult = 2.0   # wider SL for momentum trades

    def compute(self, ind, candles, patterns, reasons, score, config, active_trade=None) -> TradeSetup:
        close  = candles[-1]["c"] if candles else ind.get("vwap", 0)
        atr    = ind.get("atr", 10)
        macd_h = ind.get("macd_hist", 0)
        macd_l = ind.get("macd", 0)
        sig_l  = ind.get("signal_line", 0)
        ema9   = ind.get("ema9", close)
        ema21  = ind.get("ema21", close)
        vwap_v = ind.get("vwap", close)
        rsi_v  = ind.get("rsi", 50)

        # Need at least 2 candles for histogram comparison
        prev_hist = candles[-2]["macd_hist"] if len(candles) >= 2 else 0

        setup = TradeSetup(action="WAIT", strategy_name=self.name,
                           confidence="LOW", score=score,
                           entry_price=close, reasons=list(reasons))

        if active_trade and active_trade.get("strategy") == self.name:
            sl_hit, sl_r = self._check_stop_loss(active_trade, close, ind)
            if sl_hit:
                setup.action     = "STOP_LOSS"
                setup.sl_reasons = sl_r
                setup.in_trade   = True
                setup.trade_direction = active_trade.get("direction", "")
                setup.current_pnl_pct = self._pnl_pct(active_trade, close)
                return setup

            direction = active_trade.get("direction", "LONG")
            # MACD-specific exit: histogram crossed zero or shrinking fast
            exit_now, exit_r = self._check_exit(active_trade, close, ind, patterns, score)
            if not exit_now:
                if direction == "LONG" and macd_h < 0:
                    exit_r.append("MACD histogram crossed below zero — momentum lost")
                    exit_now = True
                if direction == "SHORT" and macd_h > 0:
                    exit_r.append("MACD histogram crossed above zero — momentum lost")
                    exit_now = True
                # histogram shrinking significantly (>40% from peak)
                if direction == "LONG" and macd_h > 0 and macd_h < prev_hist * 0.6 and prev_hist > 0:
                    exit_r.append("MACD histogram shrinking — momentum fading, consider partial exit")
                    exit_now = True
                if direction == "SHORT" and macd_h < 0 and macd_h > prev_hist * 0.6 and prev_hist < 0:
                    exit_r.append("MACD histogram shrinking — momentum fading")
                    exit_now = True

            if exit_now:
                setup.action       = "EXIT_LONG" if direction == "LONG" else "EXIT_SHORT"
                setup.exit_reasons = exit_r
                setup.in_trade     = True
                setup.trade_direction = direction
                setup.current_pnl_pct = self._pnl_pct(active_trade, close)
                return setup

            mile = self._milestone(active_trade, close)
            setup.action       = "HOLD"
            setup.hold_reasons = [
                f"MACD momentum active — hist {macd_h:+.1f}",
                f"Histogram {'expanding' if abs(macd_h) > abs(prev_hist) else 'flat'}",
            ]
            if mile: setup.hold_reasons.append(f"✅ {mile.replace('_', ' ')}")
            setup.in_trade     = True
            setup.trade_direction = direction
            setup.current_pnl_pct = self._pnl_pct(active_trade, close)
            setup.trailing_sl  = self._trailing_sl(active_trade, close, atr, direction, config)
            setup.milestone_hit = mile
            setup.stop_loss    = active_trade.get("stop_loss", 0)
            setup.target_1     = active_trade.get("target_1", 0)
            setup.target_2     = active_trade.get("target_2", 0)
            setup.target_3     = active_trade.get("target_3", 0)
            return setup

        # Detect MACD line crossover (signal line cross)
        # Need previous MACD values from candles
        bull_macd_cross = (macd_l > sig_l and macd_h > 0 and prev_hist <= 0 and prev_hist is not None)
        bear_macd_cross = (macd_l < sig_l and macd_h < 0 and prev_hist >= 0 and prev_hist is not None)

        expanding_bull = macd_h > 0 and macd_h > prev_hist * 1.2 and prev_hist > 0
        expanding_bear = macd_h < 0 and macd_h < prev_hist * 1.2 and prev_hist < 0

        if (bull_macd_cross or expanding_bull) and close > ema9 > ema21 and rsi_v < 70:
            lv = self._levels(close, atr, "LONG", config)
            setup.action       = "ENTER_LONG"
            setup.confidence   = "HIGH" if bull_macd_cross else "MEDIUM"
            setup.stop_loss    = lv["sl"]
            setup.target_1     = lv["t1"]
            setup.target_2     = lv["t2"]
            setup.target_3     = lv["t3"]
            setup.risk_per_lot = lv["risk"]
            setup.rr_ratio     = lv["rr"]
            setup.sl_pct       = lv["sl_pct"]
            setup.option_type  = "CE"
            setup.suggested_strike = self._suggest_strike(close, "LONG")
            if bull_macd_cross: setup.reasons.insert(0, "MACD Line × Signal Line Bullish Cross")
            else:               setup.reasons.insert(0, "MACD Histogram Expanding Bullish")

        elif (bear_macd_cross or expanding_bear) and close < ema9 < ema21 and rsi_v > 30:
            lv = self._levels(close, atr, "SHORT", config)
            setup.action       = "ENTER_SHORT"
            setup.confidence   = "HIGH" if bear_macd_cross else "MEDIUM"
            setup.stop_loss    = lv["sl"]
            setup.target_1     = lv["t1"]
            setup.target_2     = lv["t2"]
            setup.target_3     = lv["t3"]
            setup.risk_per_lot = lv["risk"]
            setup.rr_ratio     = lv["rr"]
            setup.sl_pct       = lv["sl_pct"]
            setup.option_type  = "PE"
            setup.suggested_strike = self._suggest_strike(close, "SHORT")
            if bear_macd_cross: setup.reasons.insert(0, "MACD Line × Signal Line Bearish Cross")
            else:               setup.reasons.insert(0, "MACD Histogram Expanding Bearish")
        else:
            setup.hold_reasons = ["MACD setup not confirmed — wait for histogram cross or expansion"]
            if abs(macd_h) < atr * 0.1:
                setup.hold_reasons.append("MACD histogram too small — low momentum, avoid entry")

        return setup


# ─── STRATEGY 4: VWAP REVERSAL ───────────────────────────────────────────────

class VWAPReversalStrategy(BaseStrategy):
    name        = "VWAP Reversal"
    description = "Trades rejections and reclaims of VWAP. Intraday scalping / swing trades."
    sl_atr_mult = 1.0   # tight SL — VWAP is precise

    def compute(self, ind, candles, patterns, reasons, score, config, active_trade=None) -> TradeSetup:
        close  = candles[-1]["c"] if candles else ind.get("vwap", 0)
        prev_c = candles[-2]["c"] if len(candles) >= 2 else close
        atr    = ind.get("atr", 10)
        vwap_v = ind.get("vwap", close)
        ema9   = ind.get("ema9",  close)
        rsi_v  = ind.get("rsi", 50)
        macd_h = ind.get("macd_hist", 0)

        setup = TradeSetup(action="WAIT", strategy_name=self.name,
                           confidence="LOW", score=score,
                           entry_price=close, reasons=list(reasons))

        if active_trade and active_trade.get("strategy") == self.name:
            sl_hit, sl_r = self._check_stop_loss(active_trade, close, ind)
            if sl_hit:
                setup.action     = "STOP_LOSS"
                setup.sl_reasons = sl_r
                setup.in_trade   = True
                setup.trade_direction = active_trade.get("direction", "")
                setup.current_pnl_pct = self._pnl_pct(active_trade, close)
                return setup

            direction = active_trade.get("direction", "LONG")
            exit_now, exit_r = self._check_exit(active_trade, close, ind, patterns, score)
            if not exit_now:
                # VWAP flip: trade went wrong direction vs VWAP
                if direction == "LONG" and close < vwap_v * 0.998:
                    exit_r.append("Price broke below VWAP — exit long")
                    exit_now = True
                if direction == "SHORT" and close > vwap_v * 1.002:
                    exit_r.append("Price reclaimed VWAP — exit short")
                    exit_now = True

            if exit_now:
                setup.action       = "EXIT_LONG" if direction == "LONG" else "EXIT_SHORT"
                setup.exit_reasons = exit_r
                setup.in_trade     = True
                setup.trade_direction = direction
                setup.current_pnl_pct = self._pnl_pct(active_trade, close)
                return setup

            mile = self._milestone(active_trade, close)
            vwap_dist = round((close - vwap_v) / vwap_v * 100, 2)
            setup.action       = "HOLD"
            setup.hold_reasons = [
                f"Price {'above' if close > vwap_v else 'below'} VWAP by {abs(vwap_dist):.2f}%",
                f"VWAP level: {vwap_v:.0f}",
            ]
            if mile: setup.hold_reasons.append(f"✅ {mile.replace('_', ' ')}")
            setup.in_trade     = True
            setup.trade_direction = direction
            setup.current_pnl_pct = self._pnl_pct(active_trade, close)
            setup.trailing_sl  = self._trailing_sl(active_trade, close, atr, direction, config)
            setup.milestone_hit = mile
            setup.stop_loss    = active_trade.get("stop_loss", 0)
            setup.target_1     = active_trade.get("target_1", 0)
            setup.target_2     = active_trade.get("target_2", 0)
            setup.target_3     = active_trade.get("target_3", 0)
            return setup

        pat_names = {p["pattern"] for p in patterns}

        # VWAP reclaim (price was below, crossed above) + bullish confirmation
        vwap_reclaim = prev_c < vwap_v <= close
        vwap_reject  = prev_c > vwap_v >= close   # price was above, fell below

        if (vwap_reclaim and macd_h > 0 and rsi_v < 65 and
                (pat_names & {"Bullish Engulfing", "Hammer", "Morning Star", "Bullish Marubozu"} or score > 20)):
            lv = self._levels(close, atr, "LONG", config)
            setup.action       = "ENTER_LONG"
            setup.confidence   = "HIGH" if score >= 40 else "MEDIUM"
            setup.stop_loss    = min(lv["sl"], round(vwap_v - atr * 0.5, 2))
            setup.target_1     = lv["t1"]
            setup.target_2     = lv["t2"]
            setup.target_3     = lv["t3"]
            setup.risk_per_lot = lv["risk"]
            setup.rr_ratio     = lv["rr"]
            setup.sl_pct       = lv["sl_pct"]
            setup.option_type  = "CE"
            setup.suggested_strike = self._suggest_strike(close, "LONG")
            setup.reasons.insert(0, f"VWAP Reclaim — price crossed above {vwap_v:.0f}")

        elif (vwap_reject and macd_h < 0 and rsi_v > 35 and
              (pat_names & {"Bearish Engulfing", "Shooting Star", "Evening Star", "Bearish Marubozu"} or score < -20)):
            lv = self._levels(close, atr, "SHORT", config)
            setup.action       = "ENTER_SHORT"
            setup.confidence   = "HIGH" if score <= -40 else "MEDIUM"
            setup.stop_loss    = max(lv["sl"], round(vwap_v + atr * 0.5, 2))
            setup.target_1     = lv["t1"]
            setup.target_2     = lv["t2"]
            setup.target_3     = lv["t3"]
            setup.risk_per_lot = lv["risk"]
            setup.rr_ratio     = lv["rr"]
            setup.sl_pct       = lv["sl_pct"]
            setup.option_type  = "PE"
            setup.suggested_strike = self._suggest_strike(close, "SHORT")
            setup.reasons.insert(0, f"VWAP Rejection — price broke below {vwap_v:.0f}")
        else:
            dist = abs(close - vwap_v)
            setup.hold_reasons = [f"Price {'above' if close > vwap_v else 'below'} VWAP by {dist:.0f} pts — wait for cross"]
            if dist > atr * 2:
                setup.hold_reasons.append("Too far from VWAP — extended move, don't chase")

        return setup


# ─── STRATEGY 5: MULTI-CONFLUENCE ────────────────────────────────────────────

class MultiConfluenceStrategy(BaseStrategy):
    """
    Requires 3+ independent confirmations from different indicator families
    before entering. Highest accuracy, fewer signals.
    """
    name        = "Multi-Confluence"
    description = "Enters only when EMA + RSI + MACD + Candle Pattern all agree. Fewest signals, highest accuracy."
    sl_atr_mult = 1.8
    min_score   = 50   # higher bar

    def compute(self, ind, candles, patterns, reasons, score, config, active_trade=None) -> TradeSetup:
        close  = candles[-1]["c"] if candles else ind.get("vwap", 0)
        atr    = ind.get("atr", 10)
        ema9   = ind.get("ema9",  close)
        ema21  = ind.get("ema21", close)
        ema50  = ind.get("ema50", close)
        rsi_v  = ind.get("rsi", 50)
        macd_h = ind.get("macd_hist", 0)
        vwap_v = ind.get("vwap", close)
        bb_lo  = ind.get("bb_lower", close * 0.98)
        bb_hi  = ind.get("bb_upper", close * 1.02)

        setup = TradeSetup(action="WAIT", strategy_name=self.name,
                           confidence="LOW", score=score,
                           entry_price=close, reasons=list(reasons))

        if active_trade and active_trade.get("strategy") == self.name:
            sl_hit, sl_r = self._check_stop_loss(active_trade, close, ind)
            if sl_hit:
                setup.action     = "STOP_LOSS"
                setup.sl_reasons = sl_r
                setup.in_trade   = True
                setup.trade_direction = active_trade.get("direction", "")
                setup.current_pnl_pct = self._pnl_pct(active_trade, close)
                return setup

            direction = active_trade.get("direction", "LONG")
            exit_now, exit_r = self._check_exit(active_trade, close, ind, patterns, score)
            if exit_now:
                setup.action       = "EXIT_LONG" if direction == "LONG" else "EXIT_SHORT"
                setup.exit_reasons = exit_r
                setup.in_trade     = True
                setup.trade_direction = direction
                setup.current_pnl_pct = self._pnl_pct(active_trade, close)
                return setup

            mile = self._milestone(active_trade, close)
            setup.action       = "HOLD"
            setup.hold_reasons = ["Multi-confluence trade — all signals aligned, maintain position"]
            if mile: setup.hold_reasons.append(f"✅ {mile.replace('_', ' ')}")
            setup.in_trade     = True
            setup.trade_direction = direction
            setup.current_pnl_pct = self._pnl_pct(active_trade, close)
            setup.trailing_sl  = self._trailing_sl(active_trade, close, atr, direction, config)
            setup.milestone_hit = mile
            setup.stop_loss    = active_trade.get("stop_loss", 0)
            setup.target_1     = active_trade.get("target_1", 0)
            setup.target_2     = active_trade.get("target_2", 0)
            setup.target_3     = active_trade.get("target_3", 0)
            return setup

        pat_names = {p["pattern"] for p in patterns}
        min_score = config.get("min_score", self.min_score)

        # Count bullish confluences
        bull_conf = []
        if ema9 > ema21 > ema50:           bull_conf.append("EMA Bullish Stack")
        if macd_h > 0:                      bull_conf.append("MACD Bullish")
        if 50 < rsi_v < 70:                 bull_conf.append(f"RSI Bullish ({rsi_v:.0f})")
        if close > vwap_v:                  bull_conf.append("Above VWAP")
        if close < bb_hi * 0.97:            bull_conf.append("BB Room to Grow")
        if pat_names & {"Bullish Engulfing", "Hammer", "Morning Star", "Bullish Marubozu"}:
            bull_conf.append("Bullish Candle Pattern")

        # Count bearish confluences
        bear_conf = []
        if ema9 < ema21 < ema50:           bear_conf.append("EMA Bearish Stack")
        if macd_h < 0:                      bear_conf.append("MACD Bearish")
        if 30 < rsi_v < 50:                 bear_conf.append(f"RSI Bearish ({rsi_v:.0f})")
        if close < vwap_v:                  bear_conf.append("Below VWAP")
        if close > bb_lo * 1.03:            bear_conf.append("BB Room to Fall")
        if pat_names & {"Bearish Engulfing", "Shooting Star", "Evening Star", "Bearish Marubozu"}:
            bear_conf.append("Bearish Candle Pattern")

        required = config.get("min_confluences", 4)

        if len(bull_conf) >= required and score >= min_score:
            lv = self._levels(close, atr, "LONG", config)
            setup.action       = "ENTER_LONG"
            setup.confidence   = "HIGH"
            setup.stop_loss    = lv["sl"]
            setup.target_1     = lv["t1"]
            setup.target_2     = lv["t2"]
            setup.target_3     = lv["t3"]
            setup.risk_per_lot = lv["risk"]
            setup.rr_ratio     = lv["rr"]
            setup.sl_pct       = lv["sl_pct"]
            setup.option_type  = "CE"
            setup.suggested_strike = self._suggest_strike(close, "LONG")
            setup.reasons      = bull_conf

        elif len(bear_conf) >= required and score <= -min_score:
            lv = self._levels(close, atr, "SHORT", config)
            setup.action       = "ENTER_SHORT"
            setup.confidence   = "HIGH"
            setup.stop_loss    = lv["sl"]
            setup.target_1     = lv["t1"]
            setup.target_2     = lv["t2"]
            setup.target_3     = lv["t3"]
            setup.risk_per_lot = lv["risk"]
            setup.rr_ratio     = lv["rr"]
            setup.sl_pct       = lv["sl_pct"]
            setup.option_type  = "PE"
            setup.suggested_strike = self._suggest_strike(close, "SHORT")
            setup.reasons      = bear_conf
        else:
            n_bull = len(bull_conf)
            n_bear = len(bear_conf)
            setup.hold_reasons = [
                f"Need {required} confluences — Bull: {n_bull}/{required}, Bear: {n_bear}/{required}",
                f"Missing bull: {', '.join(set(['EMA Stack','MACD','RSI','VWAP','BB','Pattern']) - set(bull_conf))[:60]}"
                if n_bull > n_bear else
                f"Missing bear: {', '.join(set(['EMA Stack','MACD','RSI','VWAP','BB','Pattern']) - set(bear_conf))[:60]}"
            ]

        return setup


# ─── STRATEGY REGISTRY ───────────────────────────────────────────────────────

ALL_STRATEGIES: dict[str, BaseStrategy] = {
    "EMA Trend Follow":    EMATrendStrategy(),
    "RSI Mean Reversion":  RSIMeanReversionStrategy(),
    "MACD Momentum":       MACDMomentumStrategy(),
    "VWAP Reversal":       VWAPReversalStrategy(),
    "Multi-Confluence":    MultiConfluenceStrategy(),
}


# ─── RUN ALL STRATEGIES ──────────────────────────────────────────────────────

def run_all_strategies(
    analysis: dict,
    config: dict,
    active_trades: dict | None = None,   # {strategy_name: active_trade_dict}
) -> dict[str, TradeSetup]:
    """
    Run every strategy against the latest analysis result.
    Returns { strategy_name: TradeSetup }.
    """
    ind     = analysis.get("indicators", {})
    candles = analysis.get("candles", [])
    signals = analysis.get("signal", {})
    patterns = signals.get("patterns", [])
    reasons  = signals.get("reasons", [])
    score    = signals.get("score", 0)

    results = {}
    for name, strategy in ALL_STRATEGIES.items():
        active = (active_trades or {}).get(name)
        try:
            setup = strategy.compute(
                ind=ind, candles=candles, patterns=patterns,
                reasons=reasons, score=score, config=config,
                active_trade=active,
            )
        except Exception as e:
            setup = TradeSetup(
                action="WAIT", strategy_name=name,
                confidence="LOW", score=0,
                hold_reasons=[f"Strategy error: {e}"],
            )
        results[name] = setup

    return results


# ─── SUMMARY / CONSENSUS ─────────────────────────────────────────────────────

def consensus(setups: dict[str, TradeSetup]) -> dict:
    """
    Aggregate all strategy outputs into one consensus view.
    """
    actions = [s.action for s in setups.values()]
    bull = sum(1 for a in actions if a in ("ENTER_LONG",))
    bear = sum(1 for a in actions if a in ("ENTER_SHORT",))
    hold = sum(1 for a in actions if a in ("HOLD",))
    exit_c = sum(1 for a in actions if a in ("EXIT_LONG","EXIT_SHORT"))
    sl   = sum(1 for a in actions if a == "STOP_LOSS")
    wait = sum(1 for a in actions if a == "WAIT")

    total = len(setups) or 1
    if sl > 0:
        direction = "STOP_LOSS"
    elif exit_c >= 2:
        direction = "EXIT"
    elif bull >= 3:
        direction = "STRONG BUY"
    elif bull == 2:
        direction = "BUY"
    elif bear >= 3:
        direction = "STRONG SELL"
    elif bear == 2:
        direction = "SELL"
    elif hold >= 3:
        direction = "HOLD"
    else:
        direction = "WAIT"

    return {
        "consensus":    direction,
        "bull_count":   bull,
        "bear_count":   bear,
        "hold_count":   hold,
        "exit_count":   exit_c,
        "sl_count":     sl,
        "wait_count":   wait,
        "total":        total,
        "bull_pct":     round(bull / total * 100),
        "bear_pct":     round(bear / total * 100),
    }
