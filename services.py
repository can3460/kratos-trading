# ============================================================
#  services.py — KRATOS Unified Trading Platform  v2.0
#  Backend: Market Data · 6 Agents · AGORA Protocol · Risk Manager
#  Ported from Swift/SwiftUI DayiApp (Argus) codebase
# ============================================================

from __future__ import annotations
import time
import threading
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────
#  CENTRAL CONFIGURATION  (mirrors KratosConfig / ArgusConfig.swift)
# ─────────────────────────────────────────────────────────────
class Config:
    # Data TTLs (seconds)
    QUOTE_TTL          = 30
    CANDLE_TTL         = 300
    FUNDAMENTAL_TTL    = 86_400
    MACRO_TTL          = 3_600

    # AGORA consensus thresholds
    TIER1_THRESHOLD    = 85.0   # BANKO
    TIER2_THRESHOLD    = 70.0   # STANDART
    TIER3_THRESHOLD    = 60.0   # SPEKÜLATİF

    # Quality gates
    QUALITY_TIER1      = 0.80
    QUALITY_TIER2      = 0.50
    QUALITY_MINIMUM    = 0.40

    # Debate multipliers
    SUPPORT_MULT       = 10.0
    OBJECTION_MULT     = 25.0

    # Risk / position sizing
    ATR_STOP_MULT      = 2.0
    ATR_TARGET_MULT    = 3.0
    RISK_PCT_TRADE     = 0.02   # 2 % equity at risk per trade

    # Portfolio limits
    MIN_CASH_RATIO     = 0.20
    EMERGENCY_CASH     = 0.10
    MAX_POSITIONS      = 15
    MAX_POS_WEIGHT     = 0.15
    MAX_SECTOR_CONC    = 0.40
    MAX_DAILY_TRADES   = 10

    # Macro risk-escape thresholds (Aether score)
    DEEP_RISK_OFF      = 25.0
    RISK_OFF           = 40.0

    # Data health gate
    MIN_COVERAGE_PCT   = 60.0

    # Sector ETF mapping
    SECTOR_ETFS: Dict[str, str] = {
        "Technology":           "XLK",
        "Financials":           "XLF",
        "Financial Services":   "XLF",
        "Healthcare":           "XLV",
        "Health Care":          "XLV",
        "Energy":               "XLE",
        "Industrials":          "XLI",
        "Basic Materials":      "XLB",
        "Materials":            "XLB",
        "Consumer Cyclical":    "XLY",
        "Consumer Discretionary": "XLY",
        "Consumer Defensive":   "XLP",
        "Consumer Staples":     "XLP",
        "Real Estate":          "XLRE",
        "Utilities":            "XLU",
        "Communication Services": "XLC",
    }


# ─────────────────────────────────────────────────────────────
#  DOMAIN ENUMS & DATA MODELS
# ─────────────────────────────────────────────────────────────
class SignalAction(Enum):
    BUY            = "BUY"
    SELL           = "SELL"
    HOLD           = "HOLD"
    AGGRESSIVE_BUY = "AGGRESSIVE BUY"
    ACCUMULATE     = "ACCUMULATE"
    WAIT           = "WAIT"
    ABSTAIN        = "ABSTAIN"

class AgoraStance(Enum):
    CLAIM   = "CLAIM"
    SUPPORT = "SUPPORT"
    OBJECT  = "OBJECT"
    ABSTAIN = "ABSTAIN"

class MarketRegime(Enum):
    NEUTRAL    = "Neutral"
    TREND      = "Trend"
    CHOP       = "Chop"
    RISK_OFF   = "Risk-Off"
    NEWS_SHOCK = "News Shock"

class RiskPolicyMode(Enum):
    NORMAL       = "NORMAL"
    RISK_OFF     = "RISK_OFF"
    DEEP_RISK_OFF = "DEEP_RISK_OFF"

class DecisionTier(Enum):
    """(label, position_size_multiplier)"""
    TIER1    = ("BANKO",          1.00)
    TIER2    = ("STANDART",       0.50)
    TIER3    = ("SPEKÜLATİF",     0.25)
    REJECTED = ("YETERSİZ GÜÇ",  0.00)

    def __init__(self, label: str, size: float):
        self.label = label
        self.size  = size


@dataclass
class AgentOpinion:
    agent_name:       str
    stance:           AgoraStance
    preferred_action: SignalAction
    strength:         float          # 0–1  conviction
    score:            float          # 0–100 raw score
    confidence:       float          # 0–1  data quality
    evidence:         List[str] = field(default_factory=list)


@dataclass
class AgoraDebate:
    claimant:          Optional[AgentOpinion]
    supporters:        List[AgentOpinion]
    objectors:         List[AgentOpinion]
    abstainers:        List[AgentOpinion]
    consensus_score:   float
    consensus_quality: float
    final_action:      SignalAction
    tier:              DecisionTier
    position_size:     float
    reasoning:         str


@dataclass
class DecisionResult:
    symbol:            str
    timestamp:         datetime
    # Agent scores
    orion_score:       Optional[float]
    atlas_score:       Optional[float]
    aether_score:      Optional[float]
    hermes_score:      Optional[float]
    demeter_score:     Optional[float]
    phoenix_score:     Optional[float]
    # Final verdict
    final_score:       float
    final_action:      SignalAction
    tier:              DecisionTier
    position_size:     float
    # Risk / execution
    entry_price:       Optional[float]
    stop_loss:         Optional[float]
    target_price:      Optional[float]
    risk_reward:       Optional[float]
    # Meta
    reasoning:         List[str]
    debate:            Optional[AgoraDebate]
    regime:            MarketRegime
    data_quality:      float


@dataclass
class Position:
    symbol:      str
    entry_price: float
    quantity:    float
    sector:      str
    entry_time:  datetime
    stop_loss:   float
    target:      float


@dataclass
class RiskMetrics:
    total_equity:      float
    cash:              float
    cash_ratio:        float
    invested_capital:  float
    var_95:            float
    var_99:            float
    max_drawdown:      float
    sharpe_ratio:      float
    position_count:    int
    sector_weights:    Dict[str, float]
    max_pos_weight:    float
    risk_policy:       RiskPolicyMode
    aether_score:      float


# ─────────────────────────────────────────────────────────────
#  EVENT BUS  (mirrors Swift EventBus / DecisionTrace)
# ─────────────────────────────────────────────────────────────
class EventLevel(Enum):
    INFO    = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR   = "ERROR"
    SYSTEM  = "SYSTEM"
    AGENT   = "AGENT"
    TRADE   = "TRADE"
    MACRO   = "MACRO"


@dataclass
class TerminalEvent:
    timestamp: datetime
    level:     EventLevel
    source:    str
    message:   str
    symbol:    Optional[str] = None


class EventBus:
    """Thread-safe ring-buffer event log for the terminal pane."""

    def __init__(self, max_events: int = 500):
        self._events: List[TerminalEvent] = []
        self._lock   = threading.Lock()
        self._max    = max_events

    def emit(self, level: EventLevel, source: str,
             message: str, symbol: str = None) -> None:
        ev = TerminalEvent(datetime.now(), level, source, message, symbol)
        with self._lock:
            self._events.append(ev)
            if len(self._events) > self._max:
                self._events = self._events[-self._max:]

    def get(self, limit: int = 200) -> List[TerminalEvent]:
        with self._lock:
            return list(self._events[-limit:])

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


# Module-level singleton — imported by app.py
event_bus = EventBus()


# ─────────────────────────────────────────────────────────────
#  MARKET DATA SERVICE  (mirrors HeimdallOrchestrator + providers)
# ─────────────────────────────────────────────────────────────
class MarketDataService:
    """
    yfinance-backed data provider with TTL caching.
    Mirrors the ProviderAdapterRegistry + MarketDataStore in Swift.
    """

    def __init__(self):
        self._cache: Dict[str, dict] = {}
        self._lock  = threading.Lock()

    # ── helpers ───────────────────────────────────────────────
    def _fresh(self, key: str, ttl: int) -> bool:
        return key in self._cache and (time.time() - self._cache[key]["ts"]) < ttl

    def _store(self, key: str, data) -> None:
        with self._lock:
            self._cache[key] = {"data": data, "ts": time.time()}

    # ── public API ────────────────────────────────────────────
    def get_quote(self, symbol: str) -> Optional[dict]:
        key = f"q_{symbol}"
        if self._fresh(key, Config.QUOTE_TTL):
            return self._cache[key]["data"]
        try:
            event_bus.emit(EventLevel.INFO, "DataSvc", f"→ Quote {symbol}", symbol)
            t     = yf.Ticker(symbol)
            fi    = t.fast_info
            price = float(fi.last_price)
            prev  = float(fi.previous_close)
            chg   = (price - prev) / prev * 100 if prev else 0.0
            data  = {"symbol": symbol, "price": price,
                     "prev_close": prev, "change_pct": chg,
                     "timestamp": datetime.now()}
            self._store(key, data)
            event_bus.emit(EventLevel.SUCCESS, "DataSvc",
                           f"{symbol} ${price:.2f} ({chg:+.2f}%)", symbol)
            return data
        except Exception as e:
            event_bus.emit(EventLevel.ERROR, "DataSvc", f"Quote {symbol}: {e}", symbol)
            return None

    def get_candles(self, symbol: str,
                    period: str = "6mo", interval: str = "1d") -> Optional[pd.DataFrame]:
        key = f"c_{symbol}_{period}_{interval}"
        if self._fresh(key, Config.CANDLE_TTL):
            return self._cache[key]["data"]
        try:
            event_bus.emit(EventLevel.INFO, "DataSvc", f"→ Candles {symbol}", symbol)
            df = yf.download(symbol, period=period, interval=interval,
                             progress=False, auto_adjust=True)
            if df.empty:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            df = df.dropna()
            self._store(key, df)
            event_bus.emit(EventLevel.SUCCESS, "DataSvc",
                           f"{symbol} candles: {len(df)} bars", symbol)
            return df
        except Exception as e:
            event_bus.emit(EventLevel.ERROR, "DataSvc", f"Candles {symbol}: {e}", symbol)
            return None

    def get_fundamentals(self, symbol: str) -> Optional[dict]:
        key = f"f_{symbol}"
        if self._fresh(key, Config.FUNDAMENTAL_TTL):
            return self._cache[key]["data"]
        try:
            event_bus.emit(EventLevel.INFO, "DataSvc", f"→ Fundamentals {symbol}", symbol)
            info = yf.Ticker(symbol).info
            data = {
                "pe_ratio":      info.get("trailingPE"),
                "forward_pe":    info.get("forwardPE"),
                "pb_ratio":      info.get("priceToBook"),
                "rev_growth":    info.get("revenueGrowth"),
                "earn_growth":   info.get("earningsGrowth"),
                "profit_margin": info.get("profitMargins"),
                "op_margin":     info.get("operatingMargins"),
                "debt_equity":   info.get("debtToEquity"),
                "roe":           info.get("returnOnEquity"),
                "market_cap":    info.get("marketCap"),
                "sector":        info.get("sector", "Unknown"),
                "industry":      info.get("industry", "Unknown"),
                "beta":          info.get("beta", 1.0),
                "name":          info.get("longName", symbol),
            }
            self._store(key, data)
            return data
        except Exception as e:
            event_bus.emit(EventLevel.WARNING, "DataSvc",
                           f"Fundamentals {symbol}: {e}", symbol)
            return None

    def get_macro(self) -> dict:
        """Fetch VIX, 10Y, SPY trend, Gold — cached 1 h."""
        key = "macro"
        if self._fresh(key, Config.MACRO_TTL):
            return self._cache[key]["data"]
        macro: dict = {}
        event_bus.emit(EventLevel.MACRO, "Aether", "Fetching macro indicators")
        try:
            def _dl(ticker, period="3mo"):
                df = yf.download(ticker, period=period, interval="1d",
                                 progress=False, auto_adjust=True)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(1)
                return df.dropna()

            # VIX
            vix_df = _dl("^VIX")
            if not vix_df.empty:
                macro["vix"]       = float(vix_df["Close"].iloc[-1])
                macro["vix_sma20"] = float(vix_df["Close"].rolling(20).mean().iloc[-1])

            # 10-Year Treasury
            tnx_df = _dl("^TNX")
            if not tnx_df.empty:
                macro["tnx"]          = float(tnx_df["Close"].iloc[-1])
                macro["tnx_chg_1m"]   = float(tnx_df["Close"].pct_change(21).iloc[-1] * 100)

            # SPY
            spy_df = _dl("SPY", "1y")
            if not spy_df.empty:
                c = spy_df["Close"]
                macro["spy_20d"]       = float((c.iloc[-1] / c.iloc[-21] - 1) * 100)
                macro["spy_60d"]       = float((c.iloc[-1] / c.iloc[-61] - 1) * 100)
                macro["spy_sma200_ok"] = bool(c.iloc[-1] > c.rolling(200).mean().iloc[-1])

            # Gold (risk-off proxy)
            gld_df = _dl("GLD")
            if not gld_df.empty:
                c = gld_df["Close"]
                macro["gld_20d"] = float((c.iloc[-1] / c.iloc[-21] - 1) * 100)

            self._store(key, macro)
            event_bus.emit(EventLevel.SUCCESS, "Aether",
                f"Macro ready — VIX={macro.get('vix',0):.1f} "
                f"SPY20d={macro.get('spy_20d',0):.1f}%")
        except Exception as e:
            event_bus.emit(EventLevel.ERROR, "Aether", f"Macro fetch: {e}")
        return macro


# ─────────────────────────────────────────────────────────────
#  TECHNICAL INDICATOR HELPERS
# ─────────────────────────────────────────────────────────────
def _series(df_or_series, col="Close") -> pd.Series:
    """Always return a 1-D Series."""
    if isinstance(df_or_series, pd.DataFrame):
        s = df_or_series[col]
        return s.squeeze() if hasattr(s, "squeeze") else s
    return df_or_series.squeeze() if hasattr(df_or_series, "squeeze") else df_or_series


def rsi(s: pd.Series, n=14) -> pd.Series:
    d = s.diff()
    g = d.where(d > 0, 0).rolling(n).mean()
    l = (-d.where(d < 0, 0)).rolling(n).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))


def macd(s: pd.Series, fast=12, slow=26, sig=9):
    m = s.ewm(span=fast).mean() - s.ewm(span=slow).mean()
    signal = m.ewm(span=sig).mean()
    return m, signal, m - signal


def atr(df: pd.DataFrame, n=14) -> pd.Series:
    h, l, c = _series(df, "High"), _series(df, "Low"), _series(df, "Close")
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def bollinger(s: pd.Series, n=20, k=2.0):
    mid = s.rolling(n).mean()
    std = s.rolling(n).std()
    return mid + k * std, mid, mid - k * std


def linreg_channel(s: pd.Series, lookback=60):
    y  = s.values[-lookback:]
    x  = np.arange(len(y))
    cf = np.polyfit(x, y, 1)
    fitted = np.polyval(cf, x)
    resid  = y - fitted
    σ      = resid.std()
    ss_res = (resid**2).sum()
    ss_tot = ((y - y.mean())**2).sum()
    r2     = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    cur    = np.polyval(cf, len(y) - 1)
    return cf[0], cur + 2*σ, cur - 2*σ, r2, cur   # slope, upper, lower, r², mid


# ─────────────────────────────────────────────────────────────
#  BASE AGENT
# ─────────────────────────────────────────────────────────────
class BaseAgent:
    name = "Base"

    def _stance(self, score: float) -> Tuple[AgoraStance, SignalAction]:
        if score >= 68:
            return AgoraStance.CLAIM,   SignalAction.BUY
        if score >= 58:
            return AgoraStance.SUPPORT, SignalAction.BUY
        if score >= 42:
            return AgoraStance.ABSTAIN, SignalAction.HOLD
        if score >= 32:
            return AgoraStance.SUPPORT, SignalAction.SELL
        return AgoraStance.CLAIM, SignalAction.SELL

    def _abstain(self, reason: str) -> AgentOpinion:
        return AgentOpinion(
            agent_name=self.name, stance=AgoraStance.ABSTAIN,
            preferred_action=SignalAction.ABSTAIN,
            strength=0.0, score=50.0, confidence=0.0, evidence=[reason])

    def _build(self, score: float, confidence: float,
               evidence: List[str]) -> AgentOpinion:
        score = float(np.clip(score, 0, 100))
        stance, action = self._stance(score)
        return AgentOpinion(
            agent_name=self.name, stance=stance,
            preferred_action=action,
            strength=abs(score - 50) / 50,
            score=score, confidence=float(np.clip(confidence, 0, 1)),
            evidence=evidence)


# ─────────────────────────────────────────────────────────────
#  ORION AGENT — Technical Analysis
# ─────────────────────────────────────────────────────────────
class OrionAgent(BaseAgent):
    """
    Trend · Momentum · Structure · Volatility
    Mirrors OrionScoringEngine.swift (BIST & Global variants merged)
    """
    name = "Orion"

    def __init__(self, ds: MarketDataService): self.ds = ds

    def score(self, symbol: str) -> AgentOpinion:
        event_bus.emit(EventLevel.AGENT, "Orion", f"[{symbol}] Technical analysis", symbol)
        df = self.ds.get_candles(symbol, "1y", "1d")
        if df is None or len(df) < 50:
            return self._abstain("Insufficient price history")

        close = _series(df)
        high  = _series(df, "High")
        low   = _series(df, "Low")
        vol   = _series(df, "Volume")
        price = float(close.iloc[-1])
        ev    = []
        sc    = 50.0

        # ── TREND SYSTEM (±20 pts) ──────────────────────────
        sma20  = close.rolling(20).mean()
        sma50  = close.rolling(50).mean()
        sma200 = close.rolling(200).mean() if len(close) >= 200 else None

        if sma200 is not None and not np.isnan(sma200.iloc[-1]):
            r = price / float(sma200.iloc[-1])
            if   r > 1.02: sc += 12; ev.append(f"Price > SMA200 (+{(r-1)*100:.1f}%)")
            elif r > 1.00: sc += 6
            elif r > 0.97: sc += 1
            else:          sc -= 8;  ev.append("Price < SMA200 (Bear)")

        r50 = price / float(sma50.iloc[-1])
        if   r50 > 1.01: sc += 7;  ev.append("Above SMA50")
        elif r50 < 0.99: sc -= 5;  ev.append("Below SMA50")

        # Golden / Death cross
        if sma200 is not None and len(sma200.dropna()) > 5:
            if float(sma50.iloc[-1]) > float(sma200.iloc[-1]) and \
               float(sma50.iloc[-5]) <= float(sma200.iloc[-5]):
                sc += 10; ev.append("Golden Cross ✓")
            elif float(sma50.iloc[-1]) < float(sma200.iloc[-1]) and \
                 float(sma50.iloc[-5]) >= float(sma200.iloc[-5]):
                sc -= 10; ev.append("Death Cross ✗")

        # ── MOMENTUM SYSTEM (±15 pts) ───────────────────────
        rsi_s   = rsi(close, 14)
        rsi_v   = float(rsi_s.iloc[-1])
        _, _, h = macd(close)
        h_now   = float(h.iloc[-1])
        h_prev  = float(h.iloc[-2]) if len(h) > 1 else 0.0

        if   rsi_v > 70:  sc -= 8;  ev.append(f"RSI overbought {rsi_v:.0f}")
        elif rsi_v > 60:  sc += 10; ev.append(f"RSI strong {rsi_v:.0f}")
        elif rsi_v > 50:  sc += 4
        elif rsi_v > 40:  sc -= 3
        elif rsi_v > 30:  sc -= 7;  ev.append(f"RSI weak {rsi_v:.0f}")
        else:             sc += 4;  ev.append(f"RSI oversold bounce {rsi_v:.0f}")

        if   h_now > 0 and h_now > h_prev: sc += 8;  ev.append("MACD bullish accel")
        elif h_now > 0:                    sc += 3
        elif h_now < 0 and h_now < h_prev: sc -= 8;  ev.append("MACD bearish accel")
        else:                              sc -= 3

        # ── VOLUME (±7 pts) ─────────────────────────────────
        avg_vol  = float(vol.rolling(20).mean().iloc[-1])
        vol_now  = float(vol.iloc[-1])
        vr       = vol_now / avg_vol if avg_vol > 0 else 1.0
        pc       = (float(close.iloc[-1]) - float(close.iloc[-2])) / float(close.iloc[-2])
        if vr > 1.5 and pc > 0.01:  sc += 7;  ev.append(f"Vol breakout {vr:.1f}x")
        if vr > 1.5 and pc < -0.01: sc -= 7;  ev.append(f"Vol breakdown {vr:.1f}x")

        # ── BOLLINGER (±5 pts) ──────────────────────────────
        bbu, _, bbl = bollinger(close)
        bw = float(bbu.iloc[-1]) - float(bbl.iloc[-1])
        if bw > 0:
            bp = (price - float(bbl.iloc[-1])) / bw
            if bp < 0.15: sc += 5;  ev.append("BB lower band touch")
            if bp > 0.85: sc -= 5;  ev.append("BB upper band touch")

        conf = min(len(df) / 200, 1.0)
        event_bus.emit(EventLevel.AGENT, "Orion",
            f"[{symbol}] score={sc:.1f} RSI={rsi_v:.0f}", symbol)
        return self._build(sc, conf, ev)

    def get_atr(self, symbol: str) -> Optional[float]:
        df = self.ds.get_candles(symbol, "3mo", "1d")
        if df is None or len(df) < 14:
            return None
        v = float(atr(df).iloc[-1])
        return None if np.isnan(v) else v


# ─────────────────────────────────────────────────────────────
#  ATLAS AGENT — Fundamental Analysis
# ─────────────────────────────────────────────────────────────
class AtlasAgent(BaseAgent):
    """
    Valuation (40 %) · Growth (35 %) · Quality (25 %)
    Mirrors AtlasScoringEngine.swift with global + BIST logic merged.
    """
    name = "Atlas"

    def __init__(self, ds: MarketDataService): self.ds = ds

    def score(self, symbol: str) -> AgentOpinion:
        event_bus.emit(EventLevel.AGENT, "Atlas", f"[{symbol}] Fundamental analysis", symbol)
        f = self.ds.get_fundamentals(symbol)
        if f is None:
            return self._abstain("No fundamental data")

        ev     = []
        avail  = 0
        pe     = f.get("pe_ratio")
        pb     = f.get("pb_ratio")
        rg     = f.get("rev_growth")    # decimal (0.25 = 25 %)
        eg     = f.get("earn_growth")
        pm     = f.get("profit_margin")
        de     = f.get("debt_equity")
        roe    = f.get("roe")

        # ── Valuation (0–40 mapped → 0–40 contribution) ─────
        val = 20.0
        if pe and pe > 0:
            avail += 1
            if   pe < 8:  val = 38; ev.append(f"Deep value P/E {pe:.1f}x")
            elif pe < 15: val = 32; ev.append(f"Value P/E {pe:.1f}x")
            elif pe < 25: val = 24; ev.append(f"Fair P/E {pe:.1f}x")
            elif pe < 40: val = 12; ev.append(f"Elevated P/E {pe:.1f}x")
            else:         val = 4;  ev.append(f"Bubble P/E {pe:.1f}x")

        if pb and pb > 0:
            avail += 1
            if   pb < 1.0: val += 8;  ev.append(f"Below-book P/B {pb:.2f}")
            elif pb < 2.0: val += 3
            elif pb > 5.0: val -= 4;  ev.append(f"High P/B {pb:.2f}")

        # ── Growth (0–30) ────────────────────────────────────
        gro = 15.0
        if rg is not None:
            avail += 1
            p = rg * 100
            if   p > 50: gro = 28; ev.append(f"Explosive rev growth +{p:.0f}%")
            elif p > 25: gro = 22; ev.append(f"Strong rev growth +{p:.0f}%")
            elif p > 10: gro = 17
            elif p > 0:  gro = 12
            else:        gro = 4;  ev.append(f"Rev contraction {p:.0f}%")

        if eg is not None:
            avail += 1
            p = eg * 100
            if   p > 30: gro += 5;  ev.append(f"EPS growth +{p:.0f}%")
            elif p < 0:  gro -= 5;  ev.append(f"EPS declining {p:.0f}%")

        # ── Quality (0–30) ───────────────────────────────────
        qual = 15.0
        if pm is not None:
            avail += 1
            p = pm * 100
            if   p > 20: qual += 8;  ev.append(f"High margins {p:.0f}%")
            elif p > 10: qual += 4
            elif p < 0:  qual -= 8;  ev.append(f"Unprofitable margin {p:.0f}%")

        if de is not None:
            avail += 1
            r = de / 100
            if   r < 0.3: qual += 5;  ev.append(f"Low leverage D/E {r:.2f}")
            elif r > 2.0: qual -= 5;  ev.append(f"High leverage D/E {r:.2f}")

        if roe is not None:
            avail += 1
            p = roe * 100
            if   p > 20: qual += 5;  ev.append(f"ROE {p:.0f}%")
            elif p < 0:  qual -= 5;  ev.append(f"Negative ROE {p:.0f}%")

        # Combine (weights 0.40 / 0.35 / 0.25, then scale to 0–100)
        raw  = val * 0.40 + gro * 0.35 + qual * 0.25
        sc   = np.clip(raw * 100 / 35, 0, 100)  # normalise
        conf = min(avail / 6, 1.0) if avail > 0 else 0.1

        event_bus.emit(EventLevel.AGENT, "Atlas",
            f"[{symbol}] score={sc:.1f} P/E={pe} RevGrowth={rg}", symbol)
        return self._build(sc, conf, ev)


# ─────────────────────────────────────────────────────────────
#  AETHER AGENT — Macro Regime
# ─────────────────────────────────────────────────────────────
class AetherAgent(BaseAgent):
    """
    VIX · Market trend · Rates · Gold
    Mirrors AetherScoringEngine.swift with AetherScoringConfig weights.
    """
    name = "Aether"
    WEIGHTS = {"vix": 0.22, "mkt_trend": 0.28, "momentum": 0.28,
               "rates": 0.12, "gold": 0.10}

    def __init__(self, ds: MarketDataService): self.ds = ds

    def score(self, symbol: str = None) -> AgentOpinion:
        event_bus.emit(EventLevel.MACRO, "Aether", "Macro regime analysis")
        m  = self.ds.get_macro()
        if not m:
            return self._abstain("Macro data unavailable")

        ev   = []
        comp = {}

        # VIX
        vix  = m.get("vix", 20.0)
        vs20 = m.get("vix_sma20", 20.0)
        if   vix > 35: vs = 12;  ev.append(f"VIX={vix:.1f} extreme fear")
        elif vix > 25: vs = 35;  ev.append(f"VIX={vix:.1f} elevated")
        elif vix > 20: vs = 52
        elif vix > 15: vs = 70;  ev.append(f"VIX={vix:.1f} calm")
        else:          vs = 85;  ev.append(f"VIX={vix:.1f} risk-on")
        if vix > vs20 * 1.25: vs -= 10; ev.append("VIX spiking above avg")
        comp["vix"] = float(np.clip(vs, 0, 100))

        # Market trend (SPY above SMA200 + 20d momentum)
        s20  = m.get("spy_20d", 0.0)
        ok200 = m.get("spy_sma200_ok", True)
        mts  = 65 if ok200 else 35
        if not ok200: ev.append("SPY below SMA200")
        if   s20 > 5:  mts += 15; ev.append(f"SPY +{s20:.1f}% (20d)")
        elif s20 > 0:  mts += 5
        elif s20 > -5: mts -= 5
        else:          mts -= 15; ev.append(f"SPY {s20:.1f}% (20d)")
        comp["mkt_trend"] = float(np.clip(mts, 0, 100))

        # 60-day momentum
        s60 = m.get("spy_60d", 0.0)
        if   s60 > 10:  ms = 80;  ev.append(f"Bull trend SPY +{s60:.1f}% (60d)")
        elif s60 > 3:   ms = 65
        elif s60 > -3:  ms = 50
        elif s60 > -10: ms = 35
        else:           ms = 18;  ev.append(f"Bear trend SPY {s60:.1f}% (60d)")
        comp["momentum"] = float(ms)

        # Rates (10Y)
        tnx_chg = m.get("tnx_chg_1m", 0.0)
        if   tnx_chg > 15: rs = 25;  ev.append(f"Rates rising fast ({tnx_chg:.0f}%)")
        elif tnx_chg > 5:  rs = 42
        elif tnx_chg > -5: rs = 60
        else:              rs = 75;  ev.append("Rates easing")
        comp["rates"] = float(rs)

        # Gold (risk-off)
        gld20 = m.get("gld_20d", 0.0)
        if   gld20 > 5:  gs = 28;  ev.append(f"Gold surging +{gld20:.1f}% → risk-off")
        elif gld20 > 2:  gs = 42
        elif gld20 > -2: gs = 60
        else:            gs = 75
        comp["gold"] = float(gs)

        sc   = sum(comp[k] * self.WEIGHTS[k] for k in self.WEIGHTS if k in comp)
        conf = 0.85 if len(comp) >= 4 else 0.5
        grade = self.letter_grade(sc)
        event_bus.emit(EventLevel.MACRO, "Aether",
            f"Macro={sc:.1f} ({grade}) VIX={vix:.1f}")
        return self._build(sc, conf, ev)

    @staticmethod
    def letter_grade(score: float) -> str:
        if score >= 80: return "A — Risk On"
        if score >= 70: return "B — Constructive"
        if score >= 60: return "C — Neutral"
        if score >= 50: return "D — Caution"
        return "F — Risk Off"

    def policy_mode(self, score: float) -> RiskPolicyMode:
        if score < Config.DEEP_RISK_OFF: return RiskPolicyMode.DEEP_RISK_OFF
        if score < Config.RISK_OFF:      return RiskPolicyMode.RISK_OFF
        return RiskPolicyMode.NORMAL


# ─────────────────────────────────────────────────────────────
#  HERMES AGENT — News / Sentiment (rule-based proxy)
# ─────────────────────────────────────────────────────────────
class HermesAgent(BaseAgent):
    """
    Proxy-based sentiment using price gaps, volume, and short-term ROC.
    Mirrors HermesScoringEngine.swift sentiment rules.
    """
    name = "Hermes"

    def __init__(self, ds: MarketDataService): self.ds = ds

    def score(self, symbol: str) -> AgentOpinion:
        event_bus.emit(EventLevel.AGENT, "Hermes", f"[{symbol}] Sentiment analysis", symbol)
        df = self.ds.get_candles(symbol, "3mo", "1d")
        if df is None or len(df) < 10:
            return self._abstain("Insufficient data for sentiment")

        close = _series(df)
        vol   = _series(df, "Volume")
        sc    = 50.0
        ev    = []
        avg_v = vol.rolling(20).mean()

        # Price gap analysis (news event proxy)
        for i in range(1, min(6, len(df))):
            gap  = (float(close.iloc[-i]) - float(close.iloc[-i-1])) / float(close.iloc[-i-1]) * 100
            av   = float(avg_v.iloc[-i]) if float(avg_v.iloc[-i]) > 0 else 1.0
            vr   = float(vol.iloc[-i]) / av
            if abs(gap) > 2.0 and vr > 1.5:
                if gap > 0: sc += 6;  ev.append(f"Bullish event +{gap:.1f}% on {vr:.1f}x vol")
                else:       sc -= 6;  ev.append(f"Bearish event {gap:.1f}% on {vr:.1f}x vol")

        # Short-term ROC sentiment
        roc5  = (float(close.iloc[-1]) / float(close.iloc[-6]) - 1) * 100 if len(close) > 6 else 0.0
        roc20 = (float(close.iloc[-1]) / float(close.iloc[-21]) - 1) * 100 if len(close) > 21 else 0.0

        if   roc5 > 5:  sc += 10; ev.append(f"5d momentum +{roc5:.1f}%")
        elif roc5 > 2:  sc += 4
        elif roc5 < -5: sc -= 10; ev.append(f"5d momentum {roc5:.1f}%")
        elif roc5 < -2: sc -= 4

        # Volume climax
        rv5  = float(vol.rolling(5).mean().iloc[-1])
        av20 = float(vol.rolling(20).mean().iloc[-1])
        vsr  = rv5 / av20 if av20 > 0 else 1.0
        if vsr > 2.0:
            if roc5 > 3:  sc += 8;  ev.append(f"Vol surge + rise = accumulation {vsr:.1f}x")
            elif roc5 < -3: sc -= 8; ev.append(f"Vol surge + drop = distribution {vsr:.1f}x")

        event_bus.emit(EventLevel.AGENT, "Hermes",
            f"[{symbol}] score={sc:.1f} ROC5={roc5:.1f}%", symbol)
        return self._build(sc, 0.55, ev)


# ─────────────────────────────────────────────────────────────
#  DEMETER AGENT — Sector Flow
# ─────────────────────────────────────────────────────────────
class DemeterAgent(BaseAgent):
    """
    Sector ETF relative strength vs SPY.
    Mirrors DemeterScoringEngine.swift momentum + RS logic.
    """
    name = "Demeter"

    def __init__(self, ds: MarketDataService):
        self.ds   = ds
        self._sc_cache: dict = {}
        self._sc_ts   = 0.0

    def score(self, symbol: str) -> AgentOpinion:
        event_bus.emit(EventLevel.AGENT, "Demeter", f"[{symbol}] Sector flow analysis", symbol)
        f    = self.ds.get_fundamentals(symbol)
        sect = (f or {}).get("sector", "Unknown")
        etf  = Config.SECTOR_ETFS.get(sect)

        if not etf:
            return self._abstain(f"Sector '{sect}' not mapped")

        sc, ev = self._score_etf(etf, sect)
        event_bus.emit(EventLevel.AGENT, "Demeter",
            f"[{symbol}] {sect}/{etf} score={sc:.1f}", symbol)
        return self._build(sc, 0.75, ev)

    def all_sector_scores(self) -> Dict[str, float]:
        if time.time() - self._sc_ts < 1800:
            return self._sc_cache
        spy = self.ds.get_candles("SPY", "3mo", "1d")
        out = {}
        for nm, etf in Config.SECTOR_ETFS.items():
            try:   sc, _ = self._score_etf(etf, nm, spy); out[nm] = sc
            except: out[nm] = 50.0
        self._sc_cache = out; self._sc_ts = time.time()
        return out

    def _score_etf(self, etf, sector, spy_df=None) -> Tuple[float, List[str]]:
        df = self.ds.get_candles(etf, "3mo", "1d")
        if df is None or len(df) < 21:
            return 50.0, ["Insufficient sector data"]

        c    = _series(df)
        ev   = []
        sc   = 50.0
        m20  = (float(c.iloc[-1]) / float(c.iloc[-21]) - 1) * 100
        m5   = (float(c.iloc[-1]) / float(c.iloc[-6])  - 1) * 100 if len(c) > 6 else 0.0

        if   m20 > 8:  sc += 20; ev.append(f"{etf} +{m20:.1f}% (20d) strong")
        elif m20 > 3:  sc += 10
        elif m20 > -3: pass
        elif m20 > -8: sc -= 10
        else:          sc -= 20; ev.append(f"{etf} {m20:.1f}% (20d) weak")

        if m5 > 3:  sc += 7
        elif m5 < -3: sc -= 7

        if spy_df is not None and len(spy_df) >= 21:
            cs     = _series(spy_df)
            spy_m  = (float(cs.iloc[-1]) / float(cs.iloc[-21]) - 1) * 100
            rs     = m20 - spy_m
            if   rs > 3:  sc += 18; ev.append(f"RS vs SPY +{rs:.1f}%")
            elif rs > 0:  sc += 8
            elif rs > -3: pass
            else:         sc -= 12; ev.append(f"Underperforming SPY {rs:.1f}%")

        return float(np.clip(sc, 0, 100)), ev


# ─────────────────────────────────────────────────────────────
#  PHOENIX AGENT — Price Action / Regression Channel
# ─────────────────────────────────────────────────────────────
class PhoenixAgent(BaseAgent):
    """
    Linear regression channel entry/exit scoring.
    Mirrors PhoenixEngine.swift channel + trigger logic.
    """
    name = "Phoenix"

    def __init__(self, ds: MarketDataService): self.ds = ds

    def score(self, symbol: str) -> AgentOpinion:
        event_bus.emit(EventLevel.AGENT, "Phoenix", f"[{symbol}] Price action channels", symbol)
        df = self.ds.get_candles(symbol, "1y", "1d")
        if df is None or len(df) < 60:
            return self._abstain("Insufficient bars for channel")

        close = _series(df)
        price = float(close.iloc[-1])
        slope, upper, lower, r2, mid = linreg_channel(close, 60)

        ev      = []
        sc      = 50.0
        trigs   = 0
        bw      = upper - lower
        pos     = (price - lower) / bw if bw > 0 else 0.5

        rsi_v = float(rsi(close, 14).iloc[-1])
        atr_v = float(atr(df).iloc[-1]) if not np.isnan(float(atr(df).iloc[-1])) else price * 0.02

        # Channel position score
        if   pos < 0.15: sc += 22; trigs += 1; ev.append(f"Lower band entry zone (pos={pos:.2f})")
        elif pos < 0.35: sc += 12;              ev.append(f"Below channel midpoint (pos={pos:.2f})")
        elif pos > 0.85: sc -= 18;              ev.append(f"Upper band — overbought (pos={pos:.2f})")
        elif pos > 0.65: sc -= 7

        # RSI confirmation
        if rsi_v < 35 and pos < 0.30:
            sc += 15; trigs += 1; ev.append("RSI oversold + lower band = Strong entry")
        elif rsi_v > 70 and pos > 0.70:
            sc -= 15; ev.append("RSI overbought + upper band")

        # Slope direction
        avg_p = float(close.mean())
        slope_pct = (slope / avg_p) * 100 if avg_p > 0 else 0.0
        if   slope_pct > 0.10: sc += 10; trigs += 1; ev.append(f"Channel upslope +{slope_pct:.3f}%/day")
        elif slope_pct < -0.10: sc -= 10;             ev.append(f"Channel downslope {slope_pct:.3f}%/day")

        # R² quality
        if   r2 > 0.7: sc += 5;  ev.append(f"High channel fit R²={r2:.2f}")
        elif r2 < 0.3: sc -= 5;  ev.append(f"Choppy channel R²={r2:.2f}")

        sc += trigs * 4
        event_bus.emit(EventLevel.AGENT, "Phoenix",
            f"[{symbol}] score={sc:.1f} pos={pos:.2f} R²={r2:.2f}", symbol)
        return self._build(sc, min(r2 + 0.2, 1.0), ev)

    def channel_data(self, symbol: str) -> Optional[dict]:
        df = self.ds.get_candles(symbol, "1y", "1d")
        if df is None or len(df) < 60:
            return None
        close = _series(df)
        price = float(close.iloc[-1])
        slope, upper, lower, r2, mid = linreg_channel(close, 60)
        atr_v = float(atr(df).iloc[-1]) if not np.isnan(float(atr(df).iloc[-1])) else price * 0.02
        return {
            "upper": upper, "lower": lower, "mid": mid,
            "slope": slope, "r2": r2, "atr": atr_v,
            "stop":  price - atr_v * Config.ATR_STOP_MULT,
            "t1":    price + atr_v * Config.ATR_TARGET_MULT,
        }


# ─────────────────────────────────────────────────────────────
#  CHIRON WEIGHT ENGINE — Dynamic Agent Weights
# ─────────────────────────────────────────────────────────────
class ChironWeightEngine:
    """
    Detects market regime, adjusts agent weights accordingly.
    Mirrors ChironOptimizationOutput + regime detection in Swift.
    """
    BASE = {"Orion": 0.30, "Atlas": 0.20, "Aether": 0.20,
            "Hermes": 0.10, "Demeter": 0.10, "Phoenix": 0.10}

    REGIME_WEIGHTS = {
        MarketRegime.TREND:      {"Orion": 0.40, "Atlas": 0.15, "Aether": 0.15,
                                  "Hermes": 0.10, "Demeter": 0.10, "Phoenix": 0.10},
        MarketRegime.NEUTRAL:    {"Orion": 0.25, "Atlas": 0.20, "Aether": 0.20,
                                  "Hermes": 0.10, "Demeter": 0.15, "Phoenix": 0.10},
        MarketRegime.CHOP:       {"Orion": 0.18, "Atlas": 0.28, "Aether": 0.20,
                                  "Hermes": 0.10, "Demeter": 0.14, "Phoenix": 0.10},
        MarketRegime.RISK_OFF:   {"Orion": 0.18, "Atlas": 0.25, "Aether": 0.37,
                                  "Hermes": 0.05, "Demeter": 0.10, "Phoenix": 0.05},
        MarketRegime.NEWS_SHOCK: {"Orion": 0.18, "Atlas": 0.12, "Aether": 0.20,
                                  "Hermes": 0.28, "Demeter": 0.07, "Phoenix": 0.15},
    }

    def __init__(self, ds: MarketDataService):
        self.ds = ds

    def detect_regime(self) -> MarketRegime:
        m = self.ds.get_macro()
        if not m:
            return MarketRegime.NEUTRAL
        vix  = m.get("vix", 20)
        vs20 = m.get("vix_sma20", 20)
        s20  = m.get("spy_20d", 0)
        s60  = m.get("spy_60d", 0)
        ok200 = m.get("spy_sma200_ok", True)

        if vix > vs20 * 1.30 and vix > 25:
            return MarketRegime.RISK_OFF if vix > 35 else MarketRegime.NEWS_SHOCK
        if not ok200 or s60 < -15:
            return MarketRegime.RISK_OFF
        if abs(s20) > 5 and abs(s60) > 8:
            return MarketRegime.TREND
        if abs(s20) < 2 and abs(s60) < 3:
            return MarketRegime.CHOP
        return MarketRegime.NEUTRAL

    def weights(self, regime: MarketRegime) -> Dict[str, float]:
        return self.REGIME_WEIGHTS.get(regime, self.BASE)


# ─────────────────────────────────────────────────────────────
#  KRATOS DECISION ENGINE — AGORA V2 PROTOCOL
# ─────────────────────────────────────────────────────────────
class KratosDecisionEngine:
    """
    Assembles all agent opinions, runs AGORA V2 debate, returns DecisionResult.
    Mirrors ArgusCouncilService + AgoraDebateEngine in Swift → KRATOS Python port.
    """

    def __init__(self, ds: MarketDataService):
        self.ds      = ds
        self.orion   = OrionAgent(ds)
        self.atlas   = AtlasAgent(ds)
        self.aether  = AetherAgent(ds)
        self.hermes  = HermesAgent(ds)
        self.demeter = DemeterAgent(ds)
        self.phoenix = PhoenixAgent(ds)
        self.chiron  = ChironWeightEngine(ds)
        self._agents = {
            "Orion":   self.orion,   "Atlas":  self.atlas,
            "Aether":  self.aether,  "Hermes": self.hermes,
            "Demeter": self.demeter, "Phoenix": self.phoenix,
        }

    # ── Public entry point ──────────────────────────────────
    def analyze(self, symbol: str) -> DecisionResult:
        event_bus.emit(EventLevel.SYSTEM, "AGORA",
            f"╔══ ANALYZING {symbol} ══╗", symbol)

        # Phase 1 — regime & weights
        regime  = self.chiron.detect_regime()
        weights = self.chiron.weights(regime)
        event_bus.emit(EventLevel.SYSTEM, "Chiron",
            f"Regime: {regime.value} | Weights adjusted", symbol)

        # Phase 2 — gather opinions
        opinions: Dict[str, AgentOpinion] = {}
        for nm, agent in self._agents.items():
            try:
                opinions[nm] = agent.score(symbol)
            except Exception as e:
                event_bus.emit(EventLevel.ERROR, nm, f"[{symbol}] {e}", symbol)
                opinions[nm] = self.orion._abstain(f"Error: {e}")
                opinions[nm].agent_name = nm

        # Phase 3 — data health gate
        valid  = [op for op in opinions.values() if op.stance != AgoraStance.ABSTAIN]
        cov    = len(valid) / len(opinions) * 100
        if cov < Config.MIN_COVERAGE_PCT:
            event_bus.emit(EventLevel.WARNING, "AGORA",
                f"[{symbol}] Coverage {cov:.0f}% < min → ABSTAIN", symbol)
            return self._abstain_result(symbol, opinions, regime)

        quality = float(np.mean([op.confidence for op in valid]))
        event_bus.emit(EventLevel.SYSTEM, "AGORA",
            f"[{symbol}] Coverage={cov:.0f}% Quality={quality:.2f}", symbol)

        # Phase 4 — AGORA debate
        debate = self._debate(symbol, opinions, weights, quality)

        # Phase 5 — build result
        quote = self.ds.get_quote(symbol)
        price = quote["price"] if quote else None
        ch    = self.phoenix.channel_data(symbol)
        stop  = ch["stop"] if ch else (price * 0.97 if price else None)
        t1    = ch["t1"]   if ch else (price * 1.06 if price else None)
        rr    = (t1 - price) / (price - stop) if (price and stop and t1 and price > stop) else None

        ev_all = []
        for nm, op in opinions.items():
            ev_all.extend([f"[{nm}] {e}" for e in op.evidence[:2]])

        res = DecisionResult(
            symbol=symbol, timestamp=datetime.now(),
            orion_score=opinions["Orion"].score,
            atlas_score=opinions["Atlas"].score,
            aether_score=opinions["Aether"].score,
            hermes_score=opinions["Hermes"].score,
            demeter_score=opinions["Demeter"].score,
            phoenix_score=opinions["Phoenix"].score,
            final_score=debate.consensus_score,
            final_action=debate.final_action,
            tier=debate.tier,
            position_size=debate.position_size,
            entry_price=price,
            stop_loss=stop,
            target_price=t1,
            risk_reward=rr,
            reasoning=ev_all,
            debate=debate,
            regime=regime,
            data_quality=quality,
        )

        event_bus.emit(EventLevel.TRADE, "AGORA",
            f"[{symbol}] ▶ {debate.final_action.value} | "
            f"{debate.tier.label} | Score={debate.consensus_score:.1f}", symbol)
        return res

    # ── AGORA V2 Debate ─────────────────────────────────────
    def _debate(self, symbol: str, opinions: Dict[str, AgentOpinion],
                weights: Dict[str, float], quality: float) -> AgoraDebate:

        valid = {k: v for k, v in opinions.items()
                 if v.stance != AgoraStance.ABSTAIN}
        if not valid:
            return self._make_abstain_debate()

        # ── Find Claimant (max conviction = |score-50| × confidence) ──
        def conviction(op): return abs(op.score - 50) * op.confidence
        cl_name = max(valid, key=lambda k: conviction(valid[k]))
        cl      = valid[cl_name]
        ca      = cl.preferred_action

        event_bus.emit(EventLevel.SYSTEM, "AGORA",
            f"Claimant: {cl_name} → {ca.value} (score={cl.score:.1f})")

        # ── Classify remaining ──────────────────────────────
        supporters: List[AgentOpinion] = []
        objectors:  List[AgentOpinion] = []
        abstainers: List[AgentOpinion] = []

        for nm, op in opinions.items():
            if nm == cl_name: continue
            if op.stance == AgoraStance.ABSTAIN:
                abstainers.append(op); continue

            buy_claim  = ca in (SignalAction.BUY, SignalAction.AGGRESSIVE_BUY)
            sell_claim = ca == SignalAction.SELL

            agrees = (buy_claim  and op.score >= 55) or \
                     (sell_claim and op.score <= 45) or \
                     (not buy_claim and not sell_claim and 45 <= op.score <= 55)

            if agrees:
                supporters.append(op)
                event_bus.emit(EventLevel.AGENT, nm, f"SUPPORT → {ca.value}")
            else:
                objectors.append(op)
                event_bus.emit(EventLevel.AGENT, nm,
                    f"OBJECT (score={op.score:.1f} vs {ca.value})")

        # ── Consensus calculation ────────────────────────────
        direction      = 1.0 if ca in (SignalAction.BUY, SignalAction.AGGRESSIVE_BUY) else -1.0
        sup_power      = sum(op.strength * weights.get(op.agent_name, 0.1) for op in supporters)
        obj_power      = sum(op.strength * weights.get(op.agent_name, 0.1) for op in objectors)
        sup_impact     = sup_power * Config.SUPPORT_MULT   *  direction
        obj_impact     = obj_power * Config.OBJECTION_MULT * -direction
        consensus      = float(np.clip(cl.score + sup_impact + obj_impact, 0, 100))

        # ── Quality gates + tier ─────────────────────────────
        if quality < Config.QUALITY_MINIMUM:
            tier   = DecisionTier.REJECTED
            action = SignalAction.WAIT
            event_bus.emit(EventLevel.WARNING, "AGORA",
                f"Quality gate FAIL ({quality:.2f} < {Config.QUALITY_MINIMUM})")
        else:
            if   consensus >= Config.TIER1_THRESHOLD and quality >= Config.QUALITY_TIER1:
                tier = DecisionTier.TIER1
            elif consensus >= Config.TIER2_THRESHOLD and quality >= Config.QUALITY_TIER2:
                tier = DecisionTier.TIER2
            elif consensus >= Config.TIER3_THRESHOLD:
                tier = DecisionTier.TIER3
            else:
                tier = DecisionTier.REJECTED

            if tier == DecisionTier.REJECTED:
                action = SignalAction.HOLD
            elif ca in (SignalAction.BUY, SignalAction.AGGRESSIVE_BUY, SignalAction.ACCUMULATE):
                action = SignalAction.BUY if tier.size >= 0.5 else SignalAction.ACCUMULATE
            elif ca in (SignalAction.SELL, SignalAction.LIQUIDATE):
                action = SignalAction.SELL
            else:
                action = SignalAction.HOLD

        reasoning = (f"Claimant: {cl_name} ({ca.value}, {cl.score:.1f}) | "
                     f"Support: {len(supporters)} | Objectors: {len(objectors)} | "
                     f"Consensus: {consensus:.1f} | {tier.label}")
        event_bus.emit(EventLevel.SYSTEM, "AGORA", reasoning)

        return AgoraDebate(
            claimant=cl, supporters=supporters, objectors=objectors,
            abstainers=abstainers, consensus_score=consensus,
            consensus_quality=quality, final_action=action,
            tier=tier, position_size=tier.size, reasoning=reasoning)

    # ── Helpers ─────────────────────────────────────────────
    def _abstain_result(self, symbol, opinions, regime) -> DecisionResult:
        g = lambda nm: opinions[nm].score if nm in opinions else 50.0
        return DecisionResult(
            symbol=symbol, timestamp=datetime.now(),
            orion_score=g("Orion"), atlas_score=g("Atlas"),
            aether_score=g("Aether"), hermes_score=g("Hermes"),
            demeter_score=g("Demeter"), phoenix_score=g("Phoenix"),
            final_score=50.0, final_action=SignalAction.WAIT,
            tier=DecisionTier.REJECTED, position_size=0.0,
            entry_price=None, stop_loss=None, target_price=None,
            risk_reward=None, reasoning=["Insufficient data coverage"],
            debate=None, regime=regime, data_quality=0.0)

    @staticmethod
    def _make_abstain_debate() -> AgoraDebate:
        return AgoraDebate(
            claimant=None, supporters=[], objectors=[], abstainers=[],
            consensus_score=50.0, consensus_quality=0.0,
            final_action=SignalAction.WAIT, tier=DecisionTier.REJECTED,
            position_size=0.0, reasoning="All agents abstained")


# ─────────────────────────────────────────────────────────────
#  PORTFOLIO RISK MANAGER  (mirrors PortfolioRiskManager.swift)
# ─────────────────────────────────────────────────────────────
class PortfolioRiskManager:
    """
    Risk limits, position sizing, trade validation, VaR, drawdown.
    """

    def __init__(self, equity: float = 100_000.0):
        self.initial_equity   = equity
        self.current_equity   = equity
        self.cash             = equity
        self.positions:       Dict[str, Position] = {}
        self.trade_history:   List[dict] = []
        self._daily_trades    = 0
        self._day_reset       = datetime.now().date()

    # ── Properties ──────────────────────────────────────────
    @property
    def invested_capital(self) -> float:
        return sum(p.quantity * p.entry_price for p in self.positions.values())

    @property
    def cash_ratio(self) -> float:
        total = self.cash + self.invested_capital
        return self.cash / total if total > 0 else 1.0

    # ── Position sizing ──────────────────────────────────────
    def calc_size(self, entry: float, stop: float, tier: DecisionTier,
                  aether_score: float = 60.0) -> dict:
        risk_pct   = Config.RISK_PCT_TRADE * tier.size
        risk_amt   = self.current_equity * risk_pct
        r_per_sh   = abs(entry - stop) if abs(entry - stop) > 0.01 else entry * 0.02
        raw_shares = risk_amt / r_per_sh
        pos_val    = raw_shares * entry

        # Policy multiplier
        policy = self._policy(aether_score)
        if   policy == RiskPolicyMode.DEEP_RISK_OFF: pos_val *= 0.40
        elif policy == RiskPolicyMode.RISK_OFF:       pos_val *= 0.70

        # Cap at max weight
        pos_val = min(pos_val, self.current_equity * Config.MAX_POS_WEIGHT)
        shares  = pos_val / entry if entry > 0 else 0.0

        return {"shares": round(shares, 4), "pos_value": pos_val,
                "risk_amt": risk_amt, "risk_pct": risk_pct,
                "r_per_share": r_per_sh, "policy": policy.value}

    # ── Trade validation ─────────────────────────────────────
    def validate(self, symbol: str, entry: float, shares: float,
                 sector: str, aether_score: float = 60.0) -> Tuple[bool, List[str]]:
        val  = entry * shares
        msgs = []
        total = self.cash + self.invested_capital

        new_cash_ratio = (self.cash - val) / total if total > 0 else 1.0
        if new_cash_ratio < Config.EMERGENCY_CASH:
            msgs.append(f"❌ Cash < emergency floor ({new_cash_ratio:.1%})")
        elif new_cash_ratio < Config.MIN_CASH_RATIO:
            msgs.append(f"⚠️  Cash < min ratio ({new_cash_ratio:.1%})")

        if len(self.positions) >= Config.MAX_POSITIONS:
            msgs.append(f"❌ Max positions ({Config.MAX_POSITIONS}) reached")

        w = val / total if total > 0 else 1.0
        if w > Config.MAX_POS_WEIGHT:
            msgs.append(f"❌ Position weight {w:.1%} > max {Config.MAX_POS_WEIGHT:.1%}")

        sec_v = sum(p.quantity * p.entry_price for p in self.positions.values()
                    if p.sector == sector)
        sec_w = (sec_v + val) / total if total > 0 else 1.0
        if sec_w > Config.MAX_SECTOR_CONC:
            msgs.append(f"❌ Sector '{sector}' concentration {sec_w:.1%}")

        self._reset_daily()
        if self._daily_trades >= Config.MAX_DAILY_TRADES:
            msgs.append(f"❌ Daily trade limit ({Config.MAX_DAILY_TRADES}) reached")

        policy = self._policy(aether_score)
        if policy != RiskPolicyMode.NORMAL:
            safe = {"Utilities", "Consumer Staples", "Consumer Defensive", "Healthcare"}
            if sector not in safe:
                msgs.append(f"⚠️  {policy.value}: '{sector}' is a risky sector")

        ok = not any("❌" in m for m in msgs)
        return ok, msgs

    # ── Position management ──────────────────────────────────
    def open_position(self, symbol: str, price: float, shares: float,
                      sector: str, stop: float, target: float) -> bool:
        val = price * shares
        if self.cash < val:
            return False
        self.positions[symbol] = Position(symbol, price, shares, sector,
                                          datetime.now(), stop, target)
        self.cash        -= val
        self._daily_trades += 1
        self.trade_history.append({
            "time": datetime.now(), "symbol": symbol, "action": "BUY",
            "price": price, "shares": shares, "value": val})
        event_bus.emit(EventLevel.TRADE, "RiskMgr",
            f"OPENED {symbol}: {shares:.2f} @ ${price:.2f} | val=${val:,.0f}")
        return True

    def close_position(self, symbol: str, exit_price: float) -> Optional[dict]:
        pos = self.positions.get(symbol)
        if not pos:
            return None
        pnl     = (exit_price - pos.entry_price) * pos.quantity
        pnl_pct = (exit_price / pos.entry_price - 1) * 100
        self.cash += exit_price * pos.quantity
        self.current_equity = self.cash + sum(
            p.quantity * p.entry_price for p in self.positions.values()
            if p.symbol != symbol)
        del self.positions[symbol]
        trade = {"time": datetime.now(), "symbol": symbol, "action": "SELL",
                 "entry": pos.entry_price, "exit": exit_price,
                 "shares": pos.quantity, "pnl": pnl, "pnl_pct": pnl_pct,
                 "days": (datetime.now() - pos.entry_time).days}
        self.trade_history.append(trade)
        event_bus.emit(EventLevel.TRADE, "RiskMgr",
            f"CLOSED {symbol}: PnL ${pnl:+,.0f} ({pnl_pct:+.1f}%)")
        return trade

    # ── Risk metrics ─────────────────────────────────────────
    def metrics(self, ds: MarketDataService, aether_score: float = 60.0) -> RiskMetrics:
        total = self.cash
        for sym, pos in self.positions.items():
            q = ds.get_quote(sym)
            total += (q["price"] if q else pos.entry_price) * pos.quantity
        self.current_equity = total

        # Sector weights
        sec_vals: Dict[str, float] = {}
        for pos in self.positions.values():
            sec_vals[pos.sector] = sec_vals.get(pos.sector, 0) + pos.quantity * pos.entry_price
        sec_w = {k: v / total for k, v in sec_vals.items()} if total > 0 else {}

        max_pw = max((p.quantity * p.entry_price / total
                      for p in self.positions.values()), default=0.0) if total > 0 else 0.0

        # VaR from trade history
        rets = [t["pnl_pct"] / 100 for t in self.trade_history if "pnl_pct" in t]
        var95 = float(np.percentile(rets, 5)) * total  if len(rets) > 5 else -total * 0.05
        var99 = float(np.percentile(rets, 1)) * total  if len(rets) > 5 else -total * 0.10

        # Max drawdown
        curve = [self.initial_equity]
        run   = self.initial_equity
        for t in self.trade_history:
            if "pnl" in t:
                run += t["pnl"]
                curve.append(run)
        dd = 0.0
        peak = curve[0]
        for v in curve:
            peak = max(peak, v)
            dd   = max(dd, (peak - v) / peak if peak > 0 else 0.0)

        # Sharpe
        sharpe = 0.0
        if len(rets) > 2:
            μ, σ = np.mean(rets), np.std(rets)
            sharpe = float(μ / σ * np.sqrt(252)) if σ > 0 else 0.0

        return RiskMetrics(
            total_equity=total, cash=self.cash,
            cash_ratio=self.cash / total if total > 0 else 1.0,
            invested_capital=self.invested_capital,
            var_95=var95, var_99=var99,
            max_drawdown=dd, sharpe_ratio=sharpe,
            position_count=len(self.positions),
            sector_weights=sec_w, max_pos_weight=max_pw,
            risk_policy=self._policy(aether_score),
            aether_score=aether_score)

    def _policy(self, score: float) -> RiskPolicyMode:
        if score < Config.DEEP_RISK_OFF: return RiskPolicyMode.DEEP_RISK_OFF
        if score < Config.RISK_OFF:      return RiskPolicyMode.RISK_OFF
        return RiskPolicyMode.NORMAL

    def _reset_daily(self):
        if datetime.now().date() != self._day_reset:
            self._daily_trades = 0
            self._day_reset    = datetime.now().date()


# ─────────────────────────────────────────────────────────────
#  TRADE BRAIN — Top-level Orchestrator
# ─────────────────────────────────────────────────────────────
# Backward-compat alias
ArgusDecisionEngine = KratosDecisionEngine


class TradeBrain:
    """KRATOS orchestrator — ties all agents + risk manager together."""

    def __init__(self, equity: float = 100_000.0):
        self.ds           = MarketDataService()
        self.engine       = KratosDecisionEngine(self.ds)
        self.risk_manager = PortfolioRiskManager(equity)

    def analyze(self, symbol: str) -> DecisionResult:
        return self.engine.analyze(symbol)

    def scan(self, symbols: List[str]) -> Dict[str, DecisionResult]:
        event_bus.emit(EventLevel.SYSTEM, "TradeBrain",
            f"═ Watchlist scan: {len(symbols)} symbols ═")
        out: Dict[str, DecisionResult] = {}
        for sym in symbols:
            try:
                out[sym] = self.analyze(sym)
            except Exception as e:
                event_bus.emit(EventLevel.ERROR, "TradeBrain", f"{sym}: {e}")
        buys  = sum(1 for r in out.values() if r.final_action == SignalAction.BUY)
        sells = sum(1 for r in out.values() if r.final_action == SignalAction.SELL)
        holds = len(out) - buys - sells
        event_bus.emit(EventLevel.SYSTEM, "TradeBrain",
            f"Done — BUY={buys} SELL={sells} HOLD/WAIT={holds}")
        return out
