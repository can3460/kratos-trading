# ============================================================
#  app.py — KRATOS Unified Trading Dashboard  v2.0
#  Streamlit front-end · Python port of DayiApp (Swift/Argus)
#  Run: streamlit run app.py
# ============================================================

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime

from services import (
    TradeBrain, MarketDataService, AetherAgent, DemeterAgent,
    DecisionResult, SignalAction, DecisionTier, RiskPolicyMode,
    MarketRegime, EventLevel, event_bus,
    rsi as calc_rsi, macd as calc_macd, atr as calc_atr,
    bollinger as calc_bb, linreg_channel, _series,
)

# ─────────────────────────────────────────────────────────────
#  PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="KRATOS Trading Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────
#  STOCK UNIVERSE  — symbol → {name, exchange}
# ─────────────────────────────────────────────────────────────
STOCK_UNIVERSE: dict = {
    # ── US / NASDAQ ──────────────────────────────────────────
    "AAPL":     {"name": "Apple Inc.",                    "exchange": "NASDAQ"},
    "MSFT":     {"name": "Microsoft Corp.",               "exchange": "NASDAQ"},
    "NVDA":     {"name": "NVIDIA Corp.",                  "exchange": "NASDAQ"},
    "GOOGL":    {"name": "Alphabet Inc. (A)",             "exchange": "NASDAQ"},
    "GOOG":     {"name": "Alphabet Inc. (C)",             "exchange": "NASDAQ"},
    "AMZN":     {"name": "Amazon.com Inc.",               "exchange": "NASDAQ"},
    "META":     {"name": "Meta Platforms Inc.",           "exchange": "NASDAQ"},
    "TSLA":     {"name": "Tesla Inc.",                    "exchange": "NASDAQ"},
    "AVGO":     {"name": "Broadcom Inc.",                 "exchange": "NASDAQ"},
    "AMD":      {"name": "Advanced Micro Devices",        "exchange": "NASDAQ"},
    "INTC":     {"name": "Intel Corp.",                   "exchange": "NASDAQ"},
    "QCOM":     {"name": "Qualcomm Inc.",                 "exchange": "NASDAQ"},
    "MU":       {"name": "Micron Technology",             "exchange": "NASDAQ"},
    "ADBE":     {"name": "Adobe Inc.",                    "exchange": "NASDAQ"},
    "NFLX":     {"name": "Netflix Inc.",                  "exchange": "NASDAQ"},
    "PYPL":     {"name": "PayPal Holdings",               "exchange": "NASDAQ"},
    "COST":     {"name": "Costco Wholesale",              "exchange": "NASDAQ"},
    "ASML":     {"name": "ASML Holding NV",               "exchange": "NASDAQ"},
    "IBIT":     {"name": "iShares Bitcoin Trust",         "exchange": "NASDAQ"},
    "QQQ":      {"name": "Nasdaq-100 ETF (Invesco)",      "exchange": "NASDAQ"},
    # ── US / NYSE ────────────────────────────────────────────
    "ORCL":     {"name": "Oracle Corp.",                  "exchange": "NYSE"},
    "CRM":      {"name": "Salesforce Inc.",               "exchange": "NYSE"},
    "NOW":      {"name": "ServiceNow Inc.",               "exchange": "NYSE"},
    "SPOT":     {"name": "Spotify Technology",            "exchange": "NYSE"},
    "SHOP":     {"name": "Shopify Inc.",                  "exchange": "NYSE"},
    "JPM":      {"name": "JPMorgan Chase",                "exchange": "NYSE"},
    "BAC":      {"name": "Bank of America",               "exchange": "NYSE"},
    "GS":       {"name": "Goldman Sachs",                 "exchange": "NYSE"},
    "MS":       {"name": "Morgan Stanley",                "exchange": "NYSE"},
    "V":        {"name": "Visa Inc.",                     "exchange": "NYSE"},
    "MA":       {"name": "Mastercard Inc.",               "exchange": "NYSE"},
    "BRK-B":    {"name": "Berkshire Hathaway B",          "exchange": "NYSE"},
    "JNJ":      {"name": "Johnson & Johnson",             "exchange": "NYSE"},
    "UNH":      {"name": "UnitedHealth Group",            "exchange": "NYSE"},
    "PFE":      {"name": "Pfizer Inc.",                   "exchange": "NYSE"},
    "XOM":      {"name": "Exxon Mobil",                   "exchange": "NYSE"},
    "CVX":      {"name": "Chevron Corp.",                 "exchange": "NYSE"},
    "WMT":      {"name": "Walmart Inc.",                  "exchange": "NYSE"},
    "HD":       {"name": "Home Depot Inc.",               "exchange": "NYSE"},
    "DIS":      {"name": "The Walt Disney Co.",           "exchange": "NYSE"},
    "BA":       {"name": "Boeing Co.",                    "exchange": "NYSE"},
    "CAT":      {"name": "Caterpillar Inc.",              "exchange": "NYSE"},
    "SAP":      {"name": "SAP SE",                        "exchange": "NYSE"},
    "SHELL":    {"name": "Shell plc",                     "exchange": "NYSE"},
    "SPY":      {"name": "S&P 500 ETF (SPDR)",            "exchange": "NYSE Arca"},
    "GLD":      {"name": "Gold ETF (SPDR)",               "exchange": "NYSE Arca"},
    "TLT":      {"name": "20Y Treasury ETF (iShares)",    "exchange": "NYSE Arca"},
    "ETHA":     {"name": "iShares Ethereum Trust",        "exchange": "NYSE Arca"},
    # ── BIST — Borsa İstanbul ────────────────────────────────
    "THYAO.IS": {"name": "Türk Hava Yolları (THY)",       "exchange": "BIST"},
    "GARAN.IS": {"name": "Garanti BBVA",                  "exchange": "BIST"},
    "AKBNK.IS": {"name": "Akbank",                        "exchange": "BIST"},
    "EREGL.IS": {"name": "Ereğli Demir Çelik",            "exchange": "BIST"},
    "KCHOL.IS": {"name": "Koç Holding",                   "exchange": "BIST"},
    "SAHOL.IS": {"name": "Sabancı Holding",               "exchange": "BIST"},
    "ISCTR.IS": {"name": "İş Bankası (İŞBANK)",           "exchange": "BIST"},
    "TKFEN.IS": {"name": "Tekfen Holding",                "exchange": "BIST"},
    "SISE.IS":  {"name": "Şişecam",                       "exchange": "BIST"},
    "TOASO.IS": {"name": "Tofaş Oto. Fab.",               "exchange": "BIST"},
    "TUPRS.IS": {"name": "Tüpraş",                        "exchange": "BIST"},
    "ASELS.IS": {"name": "ASELSAN",                       "exchange": "BIST"},
    "BIMAS.IS": {"name": "BİM Birleşik Mağazalar",        "exchange": "BIST"},
    "FROTO.IS": {"name": "Ford Otosan",                   "exchange": "BIST"},
    "PGSUS.IS": {"name": "Pegasus Hava Taşımacılığı",     "exchange": "BIST"},
    "SASA.IS":  {"name": "SASA Polyester",                "exchange": "BIST"},
    "KONTR.IS": {"name": "Kontrolmatik Teknoloji",        "exchange": "BIST"},
    "KRDMD.IS": {"name": "Kardemir (D)",                  "exchange": "BIST"},
    "PETKM.IS": {"name": "Petkim Petrokimya",             "exchange": "BIST"},
    "YATAS.IS": {"name": "Yataş Holding",                 "exchange": "BIST"},
    "ODAS.IS":  {"name": "Odaş Elektrik",                 "exchange": "BIST"},
    "DOHOL.IS": {"name": "Doğan Holding",                 "exchange": "BIST"},
    "ARCLK.IS": {"name": "Arçelik",                       "exchange": "BIST"},
    "VESTL.IS": {"name": "Vestel Elektronik",             "exchange": "BIST"},
    "ULKER.IS": {"name": "Ülker Bisküvi",                 "exchange": "BIST"},
    "ENKAI.IS": {"name": "Enka İnşaat",                   "exchange": "BIST"},
    "TAVHL.IS": {"name": "TAV Havalimanları",             "exchange": "BIST"},
    "EKGYO.IS": {"name": "Emlak Konut GYO",               "exchange": "BIST"},
    "MAVI.IS":  {"name": "Mavi Giyim",                    "exchange": "BIST"},
    "LOGO.IS":  {"name": "Logo Yazılım",                  "exchange": "BIST"},
    "NETAS.IS": {"name": "Netaş Telekomünikasyon",        "exchange": "BIST"},
}

# Exchange badge colours
_EXCH_COLORS = {
    "NASDAQ":   "#00e5ff",
    "NYSE":     "#ab47bc",
    "NYSE Arca":"#7e57c2",
    "BIST":     "#ffa726",
}


def _exch_badge(exchange: str) -> str:
    col = _EXCH_COLORS.get(exchange, "#4a7fa5")
    return (
        f'<span style="background:{col}22;color:{col};border:1px solid {col}55;'
        f'padding:1px 7px;border-radius:10px;font-size:0.68rem;'
        f'font-family:monospace;margin-left:6px;">{exchange}</span>'
    )


# ─────────────────────────────────────────────────────────────
#  TRANSLATIONS — EN / TR
# ─────────────────────────────────────────────────────────────
_LANG: dict = {
    "en": {
        "lang_label":       "Language / Dil",
        "search_label":     "Search Symbol or Company",
        "search_ph":        "Type symbol or company name…",
        "exchange_prefix":  "Exchange",
        "custom_sym":       "(custom symbol — not in universe)",
        "run_btn":          "▶  RUN ANALYSIS",
        "watchlist_hdr":    "Watchlist Scan",
        "symbols_lbl":      "Symbols (one per line)",
        "scan_btn":         "⚡  SCAN WATCHLIST",
        "portfolio_hdr":    "Portfolio Settings",
        "equity_lbl":       "Starting Equity ($)",
        "footer":           "KRATOS v2.0  ·  Data: Yahoo Finance",
        "tab_brain":        "⚡  KRATOS BRAIN",
        "tab_terminal":     "▓  TERMINAL",
        "tab_portfolio":    "◈  PORTFOLIO ANALYST",
        "no_results_1":     "Enter a symbol in the sidebar and press",
        "no_results_2":     "▶ RUN ANALYSIS",
        "active_sym_lbl":   "Active Symbol",
        "decision_lbl":     "DECISION",
        "tier_lbl":         "TIER",
        "consensus_lbl":    "CONSENSUS",
        "regime_lbl":       "REGIME",
        "exec_plan_hdr":    "Execution Plan",
        "entry_lbl":        "Entry Price",
        "stop_lbl":         "Stop Loss",
        "target_lbl":       "Target",
        "rr_lbl":           "R:R",
        "size_lbl":         "Position Size",
        "agora_exp":        "⚖️  AGORA Debate Log",
        "evidence_exp":     "📋  Evidence Log",
        "watchlist_sum":    "Watchlist Summary",
        "terminal_header":  "KRATOS DECISION ENGINE — LIVE EVENT STREAM",
        "filter_lbl":       "Filter Level",
        "max_lines_lbl":    "Max lines",
        "clear_btn":        "🗑  CLEAR",
        "terminal_tip":     "Tip: Re-run analysis from sidebar to see new events.",
        "port_snapshot":    "Portfolio Snapshot",
        "total_eq":         "Total Equity",
        "cash_lbl":         "Cash",
        "invested_lbl":     "Invested",
        "open_pos":         "Open Positions",
        "total_pnl":        "Total PnL",
        "risk_policy":      "RISK POLICY",
        "macro_regime":     "MACRO REGIME",
        "risk_metrics_hdr": "Risk Metrics",
        "sizer_exp":        "🧮  Position Sizing Calculator",
        "sizer_hdr":        "KRATOS Risk-Based Sizer",
        "entry_price_inp":  "Entry Price",
        "stop_inp":         "Stop Loss",
        "tier_sel":         "Tier",
        "aether_sl":        "Aether Score",
        "shares_lbl":       "Shares",
        "pos_val_lbl":      "Position Value",
        "risk_amt_lbl":     "Risk Amount",
        "risk_pct_lbl":     "Risk %",
        "trade_approved":   "✅ Trade approved — all checks passed",
        "trade_hist_exp":   "📖  Trade History",
        "no_trades":        "No trades recorded yet.",
        "sector_hm_exp":    "🌡️  Sector Heatmap",
        "virtual_hdr":      "🟢  Virtual Trading Desk",
        "open_pos_hdr":     "Open Virtual Positions",
        "no_open_pos":      "No open virtual positions. Run analysis and execute a BUY.",
        "close_pos_btn":    "✖ Close",
        "buy_success":      "Virtual BUY executed!",
        "close_success":    "Virtual position closed!",
        "no_cash":          "Insufficient virtual cash for this trade.",
        "exec_buy_btn":     "🟢  Execute Virtual BUY",
        "exec_buy_info":    "Simulates a real order using the KRATOS position sizer.",
        "agent_scores_hdr": "Agent Scores",
        "var95":            "VaR 95%",
        "var99":            "VaR 99%",
        "max_dd":           "Max Drawdown",
        "sharpe":           "Sharpe Ratio",
        "cash_ratio":       "Cash Ratio",
        "symbol_col":       "Symbol",
        "action_col":       "Action",
        "tier_col":         "Tier",
        "score_col":        "Score",
        "regime_col":       "Regime",
        "quality_col":      "Quality",
        "claimant_lbl":     "CLAIMANT",
        "supporters_lbl":   "SUPPORTERS",
        "objectors_lbl":    "OBJECTORS",
    },
    "tr": {
        "lang_label":       "Language / Dil",
        "search_label":     "Sembol veya Şirket Ara",
        "search_ph":        "Sembol veya şirket adı yazın…",
        "exchange_prefix":  "Borsa",
        "custom_sym":       "(özel sembol — listede yok)",
        "run_btn":          "▶  ANALİZ BAŞLAT",
        "watchlist_hdr":    "İzleme Listesi Taraması",
        "symbols_lbl":      "Semboller (her satıra bir tane)",
        "scan_btn":         "⚡  LİSTEYİ TARA",
        "portfolio_hdr":    "Portföy Ayarları",
        "equity_lbl":       "Başlangıç Sermayesi ($)",
        "footer":           "KRATOS v2.0  ·  Veri: Yahoo Finance",
        "tab_brain":        "⚡  KRATOS BEYNİ",
        "tab_terminal":     "▓  TERMİNAL",
        "tab_portfolio":    "◈  PORTFÖY ANALİSTİ",
        "no_results_1":     "Soldaki menüden bir sembol girin ve",
        "no_results_2":     "▶ ANALİZ BAŞLAT",
        "active_sym_lbl":   "Aktif Sembol",
        "decision_lbl":     "KARAR",
        "tier_lbl":         "SEVİYE",
        "consensus_lbl":    "KONSENSÜS",
        "regime_lbl":       "REJİM",
        "exec_plan_hdr":    "İşlem Planı",
        "entry_lbl":        "Giriş Fiyatı",
        "stop_lbl":         "Stop Loss",
        "target_lbl":       "Hedef",
        "rr_lbl":           "R:K",
        "size_lbl":         "Pozisyon Büyüklüğü",
        "agora_exp":        "⚖️  AGORA Tartışma Kaydı",
        "evidence_exp":     "📋  Kanıt Kaydı",
        "watchlist_sum":    "İzleme Listesi Özeti",
        "terminal_header":  "KRATOS KARAR MERKEZİ — CANLI OLAY AKIŞI",
        "filter_lbl":       "Seviye Filtresi",
        "max_lines_lbl":    "Maks. satır",
        "clear_btn":        "🗑  TEMİZLE",
        "terminal_tip":     "İpucu: Yeni olaylar için sol menüden analizi yeniden çalıştırın.",
        "port_snapshot":    "Portföy Anlık Görüntüsü",
        "total_eq":         "Toplam Özkaynak",
        "cash_lbl":         "Nakit",
        "invested_lbl":     "Yatırılan",
        "open_pos":         "Açık Pozisyonlar",
        "total_pnl":        "Toplam K/Z",
        "risk_policy":      "RİSK POLİTİKASI",
        "macro_regime":     "MAKRO REJİM",
        "risk_metrics_hdr": "Risk Metrikleri",
        "sizer_exp":        "🧮  Pozisyon Boyutlandırıcı",
        "sizer_hdr":        "KRATOS Risk Bazlı Boyutlandırıcı",
        "entry_price_inp":  "Giriş Fiyatı",
        "stop_inp":         "Stop Loss",
        "tier_sel":         "Seviye",
        "aether_sl":        "Aether Skoru",
        "shares_lbl":       "Hisse Adedi",
        "pos_val_lbl":      "Pozisyon Değeri",
        "risk_amt_lbl":     "Risk Tutarı",
        "risk_pct_lbl":     "Risk %",
        "trade_approved":   "✅ İşlem onaylandı — tüm kontroller geçti",
        "trade_hist_exp":   "📖  İşlem Geçmişi",
        "no_trades":        "Henüz işlem kaydı yok.",
        "sector_hm_exp":    "🌡️  Sektör Isı Haritası",
        "virtual_hdr":      "🟢  Sanal İşlem Masası",
        "open_pos_hdr":     "Açık Sanal Pozisyonlar",
        "no_open_pos":      "Açık sanal pozisyon yok. Analiz yapıp ALIM gerçekleştirin.",
        "close_pos_btn":    "✖ Kapat",
        "buy_success":      "Sanal ALIM gerçekleştirildi!",
        "close_success":    "Sanal pozisyon kapatıldı!",
        "no_cash":          "Bu işlem için yeterli sanal nakit yok.",
        "exec_buy_btn":     "🟢  Sanal ALIM Gerçekleştir",
        "exec_buy_info":    "KRATOS boyutlandırıcısını kullanarak simüle edilmiş emir çalıştırır.",
        "agent_scores_hdr": "Ajan Skorları",
        "var95":            "VaR 95%",
        "var99":            "VaR 99%",
        "max_dd":           "Maks. Drawdown",
        "sharpe":           "Sharpe Oranı",
        "cash_ratio":       "Nakit Oranı",
        "symbol_col":       "Sembol",
        "action_col":       "Karar",
        "tier_col":         "Seviye",
        "score_col":        "Skor",
        "regime_col":       "Rejim",
        "quality_col":      "Kalite",
        "claimant_lbl":     "ÖNCÜ",
        "supporters_lbl":   "DESTEKÇILER",
        "objectors_lbl":    "KARŞI ÇIKANLAR",
    },
}


def t(key: str) -> str:
    """Return translated string for current language."""
    lang = st.session_state.get("lang", "en")
    return _LANG.get(lang, _LANG["en"]).get(key, key)


# ─────────────────────────────────────────────────────────────
#  GLOBAL CSS — Dark / Hacker Theme
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
html, body, [class*="css"] {
    background-color: #0a0e17 !important;
    color: #c8d6e5 !important;
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace !important;
}
.stApp { background: #0a0e17; }
[data-testid="stSidebar"] {
    background: #0d1321 !important;
    border-right: 1px solid #1e3a5f;
}
[data-testid="stSidebar"] * { color: #8badc7 !important; }
[data-baseweb="tab-list"] { background: #0d1321; border-bottom: 1px solid #1e3a5f; }
[data-baseweb="tab"]      { color: #4a7fa5 !important; font-size: 0.85rem; }
[aria-selected="true"]    { color: #00e5ff !important; border-bottom: 2px solid #00e5ff !important; }
[data-testid="stMetric"] {
    background: #0d1321;
    border: 1px solid #1e3a5f;
    border-radius: 8px;
    padding: 14px 18px;
}
[data-testid="stMetricLabel"] { color: #4a7fa5 !important; font-size: 0.75rem; }
[data-testid="stMetricValue"] { color: #e8f4ff !important; font-size: 1.35rem; }
[data-testid="stExpander"] {
    background: #0d1321;
    border: 1px solid #1e3a5f;
    border-radius: 6px;
}
.stButton > button {
    background: #0d2137 !important;
    color: #00e5ff !important;
    border: 1px solid #00e5ff !important;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.8rem;
    letter-spacing: 0.05em;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: #00e5ff !important;
    color: #0a0e17 !important;
}
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div {
    background: #0d1321 !important;
    color: #c8d6e5 !important;
    border: 1px solid #1e3a5f !important;
    border-radius: 4px;
}
.terminal-window {
    background: #020408;
    border: 1px solid #1a3a1a;
    border-radius: 6px;
    padding: 14px 16px;
    font-family: 'JetBrains Mono', 'Courier New', monospace;
    font-size: 0.75rem;
    line-height: 1.6;
    max-height: 600px;
    overflow-y: auto;
    box-shadow: inset 0 0 30px rgba(0,229,100,0.03);
}
.terminal-window::-webkit-scrollbar { width: 4px; }
.terminal-window::-webkit-scrollbar-thumb { background: #1a3a1a; }
.log-SYSTEM  { color: #00e5ff; }
.log-SUCCESS { color: #00e564; }
.log-INFO    { color: #5a8fa5; }
.log-WARNING { color: #ffa726; }
.log-ERROR   { color: #ef5350; }
.log-AGENT   { color: #ab47bc; }
.log-TRADE   { color: #ffd54f; }
.log-MACRO   { color: #26c6da; }
.log-ts      { color: #263238; }
.log-src     { color: #37474f; }
.badge-BUY     { background:#1b5e20; color:#69f0ae; border:1px solid #2e7d32;
                 padding:3px 10px; border-radius:12px; font-size:0.75rem; }
.badge-SELL    { background:#b71c1c; color:#ff8a80; border:1px solid #c62828;
                 padding:3px 10px; border-radius:12px; font-size:0.75rem; }
.badge-HOLD    { background:#1a237e; color:#82b1ff; border:1px solid #283593;
                 padding:3px 10px; border-radius:12px; font-size:0.75rem; }
.badge-WAIT    { background:#212121; color:#bdbdbd; border:1px solid #424242;
                 padding:3px 10px; border-radius:12px; font-size:0.75rem; }
.badge-TIER1   { background:#e65100; color:#ffe0b2; border:1px solid #f57c00;
                 padding:2px 8px; border-radius:10px; font-size:0.7rem; }
.badge-TIER2   { background:#1565c0; color:#bbdefb; border:1px solid #1976d2;
                 padding:2px 8px; border-radius:10px; font-size:0.7rem; }
.badge-TIER3   { background:#4a148c; color:#e1bee7; border:1px solid #6a1b9a;
                 padding:2px 8px; border-radius:10px; font-size:0.7rem; }
.badge-REJ     { background:#1a1a1a; color:#616161; border:1px solid #333;
                 padding:2px 8px; border-radius:10px; font-size:0.7rem; }
.section-hdr {
    color:#00e5ff; font-size:0.7rem; letter-spacing:0.15em;
    text-transform:uppercase; border-bottom:1px solid #1e3a5f;
    padding-bottom:4px; margin-bottom:12px;
}
.score-bar-bg {
    background:#0d1321; border-radius:4px; height:8px;
    border:1px solid #1e3a5f; overflow:hidden;
}
.pos-card {
    background:#0d1321; border:1px solid #1e3a5f; border-radius:8px;
    padding:12px 16px; margin-bottom:8px;
}
hr { border-color: #1e3a5f !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
#  PLOTLY DARK TEMPLATE
# ─────────────────────────────────────────────────────────────
_PLOT_BG  = "#0a0e17"
_GRID_COL = "#1a2840"
_FONT_COL = "#8badc7"
_PLOT_LAYOUT = dict(
    paper_bgcolor=_PLOT_BG, plot_bgcolor=_PLOT_BG,
    font=dict(color=_FONT_COL, family="JetBrains Mono, Consolas, monospace", size=11),
    xaxis=dict(gridcolor=_GRID_COL, zerolinecolor=_GRID_COL, showgrid=True),
    yaxis=dict(gridcolor=_GRID_COL, zerolinecolor=_GRID_COL, showgrid=True),
    margin=dict(l=40, r=20, t=40, b=30),
    hoverlabel=dict(bgcolor="#0d1321", font_color="#c8d6e5", bordercolor="#1e3a5f"),
)

# ─────────────────────────────────────────────────────────────
#  SESSION STATE INIT
# ─────────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "lang":             "en",
        "brain":            None,
        "results":          {},
        "last_symbol":      "",
        "portfolio_eq":     100_000.0,
        "watchlist":        ["AAPL", "MSFT", "NVDA", "GOOGL", "TSLA"],
        "analysis_done":    False,
        "active_symbol":    None,
        "terminal_filter":  "ALL",
        "trade_feedback":   None,   # ("success"|"error", message)
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


def _brain() -> TradeBrain:
    if st.session_state.brain is None:
        st.session_state.brain = TradeBrain(st.session_state.portfolio_eq)
    return st.session_state.brain


# ─────────────────────────────────────────────────────────────
#  COLOUR / LABEL HELPERS
# ─────────────────────────────────────────────────────────────
def action_badge(action: SignalAction) -> str:
    m = {SignalAction.BUY: "BUY", SignalAction.AGGRESSIVE_BUY: "BUY",
         SignalAction.ACCUMULATE: "BUY", SignalAction.SELL: "SELL",
         SignalAction.HOLD: "HOLD", SignalAction.WAIT: "WAIT"}
    cls = m.get(action, "WAIT")
    return f'<span class="badge-{cls}">{action.value}</span>'


def tier_badge(tier: DecisionTier) -> str:
    m = {DecisionTier.TIER1: "TIER1", DecisionTier.TIER2: "TIER2",
         DecisionTier.TIER3: "TIER3", DecisionTier.REJECTED: "REJ"}
    cls = m.get(tier, "REJ")
    return f'<span class="badge-{cls}">{tier.label}</span>'


def score_color(v: float) -> str:
    if v >= 70: return "#00e564"
    if v >= 55: return "#ffd54f"
    if v >= 45: return "#4a7fa5"
    if v >= 30: return "#ffa726"
    return "#ef5350"


def action_color(action: SignalAction) -> str:
    if action in (SignalAction.BUY, SignalAction.AGGRESSIVE_BUY, SignalAction.ACCUMULATE):
        return "#00e564"
    if action == SignalAction.SELL:
        return "#ef5350"
    return "#4a7fa5"


def regime_color(regime: MarketRegime) -> str:
    m = {MarketRegime.TREND: "#00e564", MarketRegime.NEUTRAL: "#ffd54f",
         MarketRegime.CHOP: "#ffa726",  MarketRegime.RISK_OFF: "#ef5350",
         MarketRegime.NEWS_SHOCK: "#ab47bc"}
    return m.get(regime, "#4a7fa5")


# ─────────────────────────────────────────────────────────────
#  DYNAMIC STOCK SEARCH HELPERS
# ─────────────────────────────────────────────────────────────
def search_stocks(query: str) -> list[tuple[str, str, str]]:
    """
    Return list of (symbol, name, exchange) matching query.
    Matches by symbol prefix or name substring (case-insensitive).
    """
    if not query or len(query) < 1:
        return []
    q = query.upper()
    q_lower = query.lower()
    results = []
    for sym, info in STOCK_UNIVERSE.items():
        if sym.startswith(q) or q_lower in info["name"].lower():
            results.append((sym, info["name"], info["exchange"]))
    # Sort: exact symbol match first, then symbol-prefix, then name match
    results.sort(key=lambda x: (
        0 if x[0] == q else
        1 if x[0].startswith(q) else 2
    ))
    return results[:12]  # max 12 suggestions


# ─────────────────────────────────────────────────────────────
#  CHART BUILDERS
# ─────────────────────────────────────────────────────────────
def build_candlestick(symbol: str) -> go.Figure:
    ds = _brain().ds
    df = ds.get_candles(symbol, "6mo", "1d")
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(title="No data", **_PLOT_LAYOUT)
        return fig

    close = _series(df)
    sma20  = close.rolling(20).mean()
    sma50  = close.rolling(50).mean()
    sma200 = close.rolling(200).mean() if len(close) >= 200 else None
    rsi_s  = calc_rsi(close, 14)
    _, _, h_s = calc_macd(close)
    bbu, _, bbl = calc_bb(close)

    fig = make_subplots(
        rows=3, cols=1,
        row_heights=[0.60, 0.20, 0.20],
        vertical_spacing=0.03,
        shared_xaxes=True,
        subplot_titles=[f"{symbol} — Price", "RSI (14)", "MACD Histogram"],
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=_series(df, "Open"), high=_series(df, "High"),
        low=_series(df, "Low"), close=close,
        increasing_line_color="#00e564", decreasing_line_color="#ef5350",
        name="Price",
    ), row=1, col=1)

    for s, nm, col in [(sma20,"SMA20","#ffd54f"), (sma50,"SMA50","#ab47bc")]:
        fig.add_trace(go.Scatter(x=df.index, y=s, name=nm,
                                  line=dict(color=col, width=1.2)), row=1, col=1)

    if sma200 is not None:
        fig.add_trace(go.Scatter(x=df.index, y=sma200, name="SMA200",
                                  line=dict(color="#ef9a9a", width=1.0, dash="dot")),
                      row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=bbu, name="BB Upper",
                              line=dict(color="#1e3a5f", width=0.8)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=bbl, name="BB Lower",
                              line=dict(color="#1e3a5f", width=0.8),
                              fill="tonexty", fillcolor="rgba(30,58,95,0.12)"),
                  row=1, col=1)

    try:
        ch = _brain().engine.phoenix.channel_data(symbol)
        if ch:
            last60 = df.iloc[-60:]
            xs     = last60.index
            close60 = close.values[-60:]
            x_arr   = np.arange(len(close60))
            coef    = np.polyfit(x_arr, close60, 1)
            fitted  = np.polyval(coef, x_arr)
            resid   = close60 - fitted
            σ       = resid.std()
            fig.add_trace(go.Scatter(x=xs, y=fitted + 2*σ, name="Channel Up",
                                      line=dict(color="#00e5ff", width=1, dash="dash")),
                          row=1, col=1)
            fig.add_trace(go.Scatter(x=xs, y=fitted - 2*σ, name="Channel Dn",
                                      line=dict(color="#00e5ff", width=1, dash="dash"),
                                      fill="tonexty",
                                      fillcolor="rgba(0,229,255,0.04)"),
                          row=1, col=1)
            fig.add_trace(go.Scatter(x=xs, y=fitted, name="Regression",
                                      line=dict(color="#4fc3f7", width=0.8, dash="dot")),
                          row=1, col=1)
    except Exception:
        pass

    fig.add_trace(go.Scatter(x=df.index, y=rsi_s, name="RSI",
                              line=dict(color="#82b1ff", width=1.5)), row=2, col=1)
    fig.add_hline(y=70, line=dict(color="#ef5350", width=0.7, dash="dot"), row=2, col=1)
    fig.add_hline(y=30, line=dict(color="#00e564", width=0.7, dash="dot"), row=2, col=1)
    fig.add_hline(y=50, line=dict(color="#37474f", width=0.5), row=2, col=1)

    colors = ["#00e564" if v >= 0 else "#ef5350" for v in h_s.fillna(0)]
    fig.add_trace(go.Bar(x=df.index, y=h_s, name="MACD Hist",
                          marker_color=colors), row=3, col=1)

    fig.update_layout(
        title=dict(text=f"<b>{symbol}</b> — Technical Analysis",
                   font=dict(color="#00e5ff", size=14)),
        showlegend=True,
        legend=dict(orientation="h", x=0, y=1.02, bgcolor="rgba(0,0,0,0)", font=dict(size=9)),
        xaxis_rangeslider_visible=False,
        height=640, **_PLOT_LAYOUT,
    )
    return fig


def build_radar(result: DecisionResult) -> go.Figure:
    agents = ["Orion", "Atlas", "Aether", "Hermes", "Demeter", "Phoenix"]
    vals   = [result.orion_score or 50, result.atlas_score or 50,
              result.aether_score or 50, result.hermes_score or 50,
              result.demeter_score or 50, result.phoenix_score or 50]

    fig = go.Figure(go.Scatterpolar(
        r=vals + [vals[0]], theta=agents + [agents[0]],
        fill="toself", fillcolor="rgba(0,229,255,0.10)",
        line=dict(color="#00e5ff", width=1.5),
        marker=dict(color=[score_color(v) for v in vals + [vals[0]]], size=6),
        name="Agent Scores",
    ))
    fig.add_trace(go.Scatterpolar(
        r=[50]*7, theta=agents + [agents[0]],
        line=dict(color="#1e3a5f", width=1, dash="dot"), showlegend=False,
    ))
    fig.update_layout(
        polar=dict(
            bgcolor="#0a0e17",
            radialaxis=dict(visible=True, range=[0, 100],
                            gridcolor=_GRID_COL, tickfont=dict(size=9),
                            linecolor=_GRID_COL),
            angularaxis=dict(gridcolor=_GRID_COL, linecolor=_GRID_COL,
                             tickfont=dict(color="#8badc7", size=10)),
        ),
        paper_bgcolor=_PLOT_BG, font=dict(color=_FONT_COL),
        title=dict(text="Agent Council Scores", font=dict(color="#00e5ff", size=12)),
        showlegend=False, height=340, margin=dict(l=50, r=50, t=50, b=30),
    )
    return fig


def build_sector_chart(ds: MarketDataService) -> go.Figure:
    dem = DemeterAgent(ds)
    scores = dem.all_sector_scores()
    if not scores:
        fig = go.Figure()
        fig.update_layout(title="No sector data", **_PLOT_LAYOUT, height=360)
        return fig
    items   = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    sectors = [i[0] for i in items]
    vals    = [i[1] for i in items]
    fig = go.Figure(go.Bar(
        x=vals, y=sectors, orientation="h",
        marker_color=[score_color(v) for v in vals],
        text=[f"{v:.1f}" for v in vals], textposition="outside",
        textfont=dict(size=10, color="#8badc7"),
    ))
    fig.add_vline(x=50, line=dict(color="#37474f", dash="dot", width=1))
    # NOTE: xaxis / yaxis set via update_xaxes/yaxes to avoid duplicate-kwarg
    # clash when spreading _PLOT_LAYOUT (which already contains xaxis/yaxis keys)
    fig.update_layout(
        title=dict(text="Sector Momentum vs SPY", font=dict(color="#00e5ff", size=13)),
        height=360, **_PLOT_LAYOUT,
    )
    fig.update_xaxes(range=[0, 105], title_text="Score")
    fig.update_yaxes(tickfont=dict(size=10))
    return fig


def build_portfolio_pie(risk_mgr) -> go.Figure:
    if not risk_mgr.positions:
        labels = ["Cash"]; values = [100.0]; colors = ["#1e3a5f"]
    else:
        total = risk_mgr.cash + risk_mgr.invested_capital
        sec: dict = {}
        for pos in risk_mgr.positions.values():
            sec[pos.sector] = sec.get(pos.sector, 0) + pos.quantity * pos.entry_price
        sec["Cash"] = risk_mgr.cash
        labels = list(sec.keys())
        values = [v / total * 100 for v in sec.values()]
        palette = ["#00e564","#00e5ff","#ffd54f","#ab47bc","#ffa726","#ef5350","#4fc3f7","#1e3a5f"]
        colors  = palette[:len(labels)]

    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.5,
        marker=dict(colors=colors, line=dict(color=_PLOT_BG, width=2)),
        textfont=dict(color="#c8d6e5", size=10),
    ))
    fig.update_layout(
        title=dict(text="Portfolio Allocation", font=dict(color="#00e5ff", size=13)),
        paper_bgcolor=_PLOT_BG, font=dict(color=_FONT_COL),
        height=320, margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(font=dict(size=9)),
    )
    return fig


def build_equity_curve(trade_history: list, initial: float) -> go.Figure:
    if len(trade_history) < 2:
        fig = go.Figure()
        fig.update_layout(title="No trade history yet", **_PLOT_LAYOUT, height=220)
        return fig
    equity = initial
    times, equities = [datetime.now()], [initial]
    for t_item in trade_history:
        if "pnl" in t_item:
            equity += t_item["pnl"]
            times.append(t_item["time"])
            equities.append(equity)
    col = "#00e564" if equities[-1] >= initial else "#ef5350"
    fig = go.Figure(go.Scatter(
        x=times, y=equities, fill="tozeroy",
        fillcolor="rgba(0,229,100,0.06)",
        line=dict(color=col, width=2), name="Equity",
    ))
    fig.add_hline(y=initial, line=dict(color="#37474f", dash="dot", width=1))
    fig.update_layout(title="Equity Curve", height=220, **_PLOT_LAYOUT)
    return fig


# ─────────────────────────────────────────────────────────────
#  TERMINAL RENDERER
# ─────────────────────────────────────────────────────────────
_LEVEL_CSS = {
    EventLevel.SYSTEM:  "log-SYSTEM",  EventLevel.SUCCESS: "log-SUCCESS",
    EventLevel.INFO:    "log-INFO",    EventLevel.WARNING: "log-WARNING",
    EventLevel.ERROR:   "log-ERROR",   EventLevel.AGENT:   "log-AGENT",
    EventLevel.TRADE:   "log-TRADE",   EventLevel.MACRO:   "log-MACRO",
}
_LEVEL_ICONS = {
    EventLevel.SYSTEM:  "◈", EventLevel.SUCCESS: "✓", EventLevel.INFO:    "·",
    EventLevel.WARNING: "⚠", EventLevel.ERROR:   "✗", EventLevel.AGENT:   "▸",
    EventLevel.TRADE:   "⬥", EventLevel.MACRO:   "∿",
}


def render_terminal(filter_level: str = "ALL", limit: int = 150) -> str:
    events = event_bus.get(limit)
    if filter_level != "ALL":
        events = [e for e in events if e.level.value == filter_level]
    lines = []
    for ev in reversed(events):
        ts   = ev.timestamp.strftime("%H:%M:%S.%f")[:-3]
        cls  = _LEVEL_CSS.get(ev.level, "log-INFO")
        icon = _LEVEL_ICONS.get(ev.level, "·")
        sym  = f"<span style='color:#263238'>[{ev.symbol}]</span> " if ev.symbol else ""
        lines.append(
            f'<span class="log-ts">{ts}</span> '
            f'<span class="log-src">[{ev.source:<10}]</span> '
            f'<span class="{cls}">{icon} {sym}{ev.message}</span>'
        )
    body = "<br>".join(lines) if lines else '<span class="log-INFO">// Awaiting events...</span>'
    return f'<div class="terminal-window">{body}</div>'


def score_bar_html(label: str, value: float, width_px: int = 200) -> str:
    col = score_color(value)
    bar = int(value * width_px / 100)
    return (
        f'<div style="margin-bottom:6px;">'
        f'<span style="color:#4a7fa5;font-size:0.72rem;width:80px;display:inline-block;">{label}</span>'
        f'<div class="score-bar-bg" style="display:inline-block;width:{width_px}px;vertical-align:middle;">'
        f'<div style="width:{bar}px;height:8px;background:{col};border-radius:4px;"></div></div>'
        f'<span style="color:{col};font-size:0.72rem;margin-left:8px;">{value:.1f}</span>'
        f'</div>'
    )


# ─────────────────────────────────────────────────────────────
#  VIRTUAL TRADING HELPERS
# ─────────────────────────────────────────────────────────────
def execute_virtual_buy(result: DecisionResult) -> tuple[bool, str]:
    """
    Use KRATOS position sizer to open a virtual position.
    Returns (success, message).
    """
    rm = _brain().risk_manager
    if result.entry_price is None or result.stop_loss is None:
        return False, "No entry/stop data available."
    if result.tier == DecisionTier.REJECTED:
        return False, "Signal tier REJECTED — no trade."

    ae_score = result.aether_score or 60.0
    sizing   = rm.calc_size(result.entry_price, result.stop_loss, result.tier, ae_score)
    shares   = sizing["shares"]
    if shares <= 0:
        return False, "Position size calculated as 0."

    # Determine sector from universe or fundamentals
    info   = STOCK_UNIVERSE.get(result.symbol, {})
    sector = info.get("name", "Unknown")
    try:
        fund = _brain().ds.get_fundamentals(result.symbol)
        if fund:
            sector = fund.get("sector", sector)
    except Exception:
        pass

    ok, msgs = rm.validate(result.symbol, result.entry_price, shares, sector, ae_score)
    if not ok:
        return False, " | ".join(msgs)

    success = rm.open_position(
        result.symbol, result.entry_price, shares, sector,
        result.stop_loss, result.target_price or result.entry_price * 1.06
    )
    if success:
        return True, (f"{result.symbol} — {shares:.2f} shares @ ${result.entry_price:.2f}"
                      f" | Risk ${sizing['risk_amt']:,.0f}")
    return False, t("no_cash")


def execute_virtual_close(symbol: str) -> tuple[bool, str]:
    """Fetch live price and close the virtual position."""
    rm  = _brain().risk_manager
    ds  = _brain().ds
    q   = ds.get_quote(symbol)
    if q is None:
        return False, f"Cannot fetch price for {symbol}."
    trade = rm.close_position(symbol, q["price"])
    if trade:
        return True, (f"{symbol} closed @ ${q['price']:.2f}"
                      f" | PnL ${trade['pnl']:+,.2f} ({trade['pnl_pct']:+.1f}%)")
    return False, f"No open position for {symbol}."


# ══════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    # ── KRATOS Branding ───────────────────────────────────────
    st.markdown("""
    <div style="text-align:center;padding:10px 0 16px 0;">
        <div style="font-size:1.8rem;color:#00e5ff;letter-spacing:0.15em;
                    font-weight:700;text-shadow:0 0 20px #00e5ff55;">⚡ KRATOS</div>
        <div style="font-size:0.6rem;color:#37474f;letter-spacing:0.25em;">
            UNIFIED TRADING PLATFORM</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Language Toggle ───────────────────────────────────────
    lang_choice = st.radio(
        t("lang_label"),
        options=["en", "tr"],
        format_func=lambda x: "🇬🇧 English" if x == "en" else "🇹🇷 Türkçe",
        horizontal=True,
        index=0 if st.session_state.lang == "en" else 1,
        key="lang_radio",
    )
    if lang_choice != st.session_state.lang:
        st.session_state.lang = lang_choice
        st.rerun()

    st.divider()

    # ── Dynamic Stock Search ──────────────────────────────────
    st.markdown(f'<p class="section-hdr">{t("search_label")}</p>',
                unsafe_allow_html=True)

    search_query = st.text_input(
        label="search_input",
        placeholder=t("search_ph"),
        label_visibility="collapsed",
        key="stock_search_query",
    )

    symbol_input = ""
    if search_query:
        matches = search_stocks(search_query)
        if matches:
            # Build labelled options
            options_display = [
                f"{sym}  ·  {name}  [{exch}]"
                for sym, name, exch in matches
            ]
            # Add "use as-is" option at bottom if typed text isn't an exact match
            typed_upper = search_query.upper().strip()
            exact_syms  = [m[0] for m in matches]
            if typed_upper not in exact_syms:
                options_display.append(f"{typed_upper}  ·  {t('custom_sym')}  [?]")
                matches.append((typed_upper, t("custom_sym"), "?"))

            selected_idx = st.selectbox(
                label="results_box",
                options=range(len(options_display)),
                format_func=lambda i: options_display[i],
                label_visibility="collapsed",
                key="stock_search_select",
            )
            sym_sel, name_sel, exch_sel = matches[selected_idx]
            symbol_input = sym_sel

            # Exchange badge display
            col_badge = _EXCH_COLORS.get(exch_sel, "#4a7fa5")
            st.markdown(
                f'<div style="margin-top:-6px;margin-bottom:6px;">'
                f'<span style="color:#4a7fa5;font-size:0.68rem;">{t("exchange_prefix")}:</span>'
                f'<span style="background:{col_badge}22;color:{col_badge};'
                f'border:1px solid {col_badge}55;padding:1px 8px;border-radius:10px;'
                f'font-size:0.68rem;margin-left:6px;">{exch_sel}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            # No match — use raw input as custom symbol
            symbol_input = search_query.upper().strip()
            st.markdown(
                f'<div style="font-size:0.68rem;color:#37474f;margin-top:-4px;">'
                f'{t("custom_sym")}</div>',
                unsafe_allow_html=True,
            )
    else:
        # Fallback: direct text input when search is empty
        symbol_input = st.text_input(
            "Symbol", value="AAPL",
            placeholder="e.g. AAPL, TSLA, THYAO.IS",
            label_visibility="visible",
        ).upper().strip()

    run_single = st.button(t("run_btn"), use_container_width=True)

    st.divider()

    # ── Watchlist ─────────────────────────────────────────────
    st.markdown(f'<p class="section-hdr">{t("watchlist_hdr")}</p>',
                unsafe_allow_html=True)
    wl_raw = st.text_area(
        t("symbols_lbl"),
        value="\n".join(st.session_state.watchlist),
        height=120,
    )
    if wl_raw:
        st.session_state.watchlist = [s.strip().upper()
                                       for s in wl_raw.splitlines() if s.strip()]

    run_scan = st.button(t("scan_btn"), use_container_width=True)

    st.divider()

    # ── Portfolio settings ────────────────────────────────────
    st.markdown(f'<p class="section-hdr">{t("portfolio_hdr")}</p>',
                unsafe_allow_html=True)
    eq = st.number_input(t("equity_lbl"), value=100_000, step=10_000, min_value=1_000)
    if eq != st.session_state.portfolio_eq:
        st.session_state.portfolio_eq = float(eq)
        st.session_state.brain        = None   # reset brain on equity change

    st.divider()
    st.markdown(
        f'<div style="font-size:0.6rem;color:#263238;text-align:center;">'
        f'{t("footer")}</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════
#  HANDLE SIDEBAR ACTIONS
# ══════════════════════════════════════════════════════════════
if run_single and symbol_input:
    with st.spinner(f"Analyzing {symbol_input}..."):
        r = _brain().analyze(symbol_input)
        st.session_state.results[symbol_input] = r
        st.session_state.active_symbol = symbol_input
        st.session_state.analysis_done = True

if run_scan:
    with st.spinner(f"Scanning {len(st.session_state.watchlist)} symbols..."):
        batch = _brain().scan(st.session_state.watchlist)
        st.session_state.results.update(batch)
        if batch:
            st.session_state.active_symbol = list(batch.keys())[0]
        st.session_state.analysis_done = True


# ══════════════════════════════════════════════════════════════
#  MAIN TABS
# ══════════════════════════════════════════════════════════════
tab_brain, tab_terminal, tab_portfolio = st.tabs([
    t("tab_brain"), t("tab_terminal"), t("tab_portfolio"),
])

# ──────────────────────────────────────────────────────────────
#  TAB 1 — KRATOS BRAIN
# ──────────────────────────────────────────────────────────────
with tab_brain:
    if not st.session_state.results:
        st.markdown(f"""
        <div style="text-align:center;padding:80px 0;color:#1e3a5f;">
            <div style="font-size:3rem;">⚡</div>
            <div style="font-size:1.1rem;color:#37474f;margin-top:10px;">
                {t("no_results_1")}<br>
                <span style="color:#00e5ff;">{t("no_results_2")}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        syms   = list(st.session_state.results.keys())
        active = st.session_state.active_symbol or syms[0]
        if len(syms) > 1:
            active = st.selectbox(t("active_sym_lbl"), syms,
                                   index=syms.index(active) if active in syms else 0)
            st.session_state.active_symbol = active

        res: DecisionResult = st.session_state.results[active]

        # ── Top decision header ────────────────────────────────
        col_a, col_b, col_c, col_d, col_e = st.columns([2, 1.5, 1.5, 1.5, 1.5])
        with col_a:
            # Show exchange badge if known
            uni_info = STOCK_UNIVERSE.get(active, {})
            exch_str = uni_info.get("exchange", "")
            name_str = uni_info.get("name", "")
            price_str = f"${res.entry_price:.2f}" if res.entry_price else "N/A"
            exch_html = _exch_badge(exch_str) if exch_str else ""
            st.markdown(
                f'<div style="font-size:1.8rem;color:#e8f4ff;font-weight:700;">'
                f'{active}{exch_html}</div>'
                f'<div style="font-size:0.75rem;color:#37474f;">{name_str}</div>'
                f'<div style="font-size:1rem;color:#4a7fa5;">{price_str}</div>',
                unsafe_allow_html=True)
        with col_b:
            st.markdown(
                f'<div style="font-size:0.7rem;color:#4a7fa5;margin-bottom:4px;">'
                f'{t("decision_lbl")}</div>{action_badge(res.final_action)}',
                unsafe_allow_html=True)
        with col_c:
            st.markdown(
                f'<div style="font-size:0.7rem;color:#4a7fa5;margin-bottom:4px;">'
                f'{t("tier_lbl")}</div>{tier_badge(res.tier)}',
                unsafe_allow_html=True)
        with col_d:
            rc = score_color(res.final_score)
            st.markdown(
                f'<div style="font-size:0.7rem;color:#4a7fa5;">{t("consensus_lbl")}</div>'
                f'<div style="font-size:1.3rem;color:{rc};font-weight:700;">'
                f'{res.final_score:.1f}</div>',
                unsafe_allow_html=True)
        with col_e:
            rg_col = regime_color(res.regime)
            st.markdown(
                f'<div style="font-size:0.7rem;color:#4a7fa5;">{t("regime_lbl")}</div>'
                f'<div style="font-size:0.85rem;color:{rg_col};">{res.regime.value}</div>',
                unsafe_allow_html=True)

        st.divider()

        # ── Chart + Agent panel ────────────────────────────────
        chart_col, agent_col = st.columns([3, 1.3])
        with chart_col:
            st.plotly_chart(build_candlestick(active), use_container_width=True)
        with agent_col:
            st.plotly_chart(build_radar(res), use_container_width=True)
            st.markdown(f'<p class="section-hdr">{t("agent_scores_hdr")}</p>',
                        unsafe_allow_html=True)
            bar_html = "".join(
                score_bar_html(nm, v if v is not None else 50.0)
                for nm, v in [
                    ("Orion",   res.orion_score),
                    ("Atlas",   res.atlas_score),
                    ("Aether",  res.aether_score),
                    ("Hermes",  res.hermes_score),
                    ("Demeter", res.demeter_score),
                    ("Phoenix", res.phoenix_score),
                ]
            )
            st.markdown(bar_html, unsafe_allow_html=True)

        # ── Execution Plan ─────────────────────────────────────
        st.markdown(f'<p class="section-hdr">{t("exec_plan_hdr")}</p>',
                    unsafe_allow_html=True)
        r1, r2, r3, r4, r5 = st.columns(5)
        r1.metric(t("entry_lbl"),  f"${res.entry_price:.2f}"  if res.entry_price  else "—")
        r2.metric(t("stop_lbl"),   f"${res.stop_loss:.2f}"    if res.stop_loss    else "—")
        r3.metric(t("target_lbl"), f"${res.target_price:.2f}" if res.target_price else "—")
        r4.metric(t("rr_lbl"),     f"{res.risk_reward:.1f}x"  if res.risk_reward  else "—")
        r5.metric(t("size_lbl"),   f"{res.position_size * 100:.0f}% of R")

        # ── Virtual BUY button ─────────────────────────────────
        st.divider()
        buy_col, info_col = st.columns([1, 3])
        with buy_col:
            if st.button(t("exec_buy_btn"), use_container_width=True, key=f"buy_{active}"):
                ok, msg = execute_virtual_buy(res)
                if ok:
                    st.session_state.trade_feedback = ("success", f"{t('buy_success')} — {msg}")
                else:
                    st.session_state.trade_feedback = ("error", msg)
                st.rerun()
        with info_col:
            st.caption(t("exec_buy_info"))

        # Show trade feedback banner
        if st.session_state.trade_feedback:
            kind, msg = st.session_state.trade_feedback
            if kind == "success":
                st.success(msg)
            else:
                st.error(msg)
            st.session_state.trade_feedback = None

        # ── AGORA Debate ───────────────────────────────────────
        if res.debate:
            with st.expander(t("agora_exp"), expanded=False):
                d = res.debate
                st.markdown(f"`{d.reasoning}`")
                dcols = st.columns(3)
                with dcols[0]:
                    st.markdown(f"**{t('claimant_lbl')}**")
                    if d.claimant:
                        st.markdown(
                            f"- `{d.claimant.agent_name}`\n"
                            f"- Score: **{d.claimant.score:.1f}**\n"
                            f"- Action: **{d.claimant.preferred_action.value}**")
                with dcols[1]:
                    st.markdown(f"**{t('supporters_lbl')}** ({len(d.supporters)})")
                    for s in d.supporters:
                        st.markdown(f"- ✅ `{s.agent_name}` ({s.score:.1f})")
                with dcols[2]:
                    st.markdown(f"**{t('objectors_lbl')}** ({len(d.objectors)})")
                    for o in d.objectors:
                        st.markdown(f"- ❌ `{o.agent_name}` ({o.score:.1f})")

        # ── Evidence Log ───────────────────────────────────────
        with st.expander(t("evidence_exp"), expanded=False):
            if not res.reasoning:
                st.caption("No evidence recorded.")
            else:
                BULL_KW = {"bull","strong","above","growth","value","golden","cross",
                           "breakout","momentum","oversold","accumulation","upslope"}
                BEAR_KW = {"bear","weak","below","contraction","oversold","death",
                           "breakdown","distribution","overbought","downslope","declining"}

                # Group by agent prefix  [Orion], [Atlas] …
                groups: dict = {}
                for entry in res.reasoning:
                    try:
                        if entry.startswith("[") and "]" in entry:
                            bracket_end = entry.index("]")
                            agent = entry[1:bracket_end]
                            text  = entry[bracket_end + 2:].strip()
                        else:
                            agent = "System"
                            text  = entry.strip()
                    except Exception:
                        agent = "System"
                        text  = str(entry)
                    groups.setdefault(agent, []).append(text)

                _AG_COLORS = {
                    "Orion":"#ffd54f","Atlas":"#4fc3f7","Aether":"#26c6da",
                    "Hermes":"#ab47bc","Demeter":"#66bb6a","Phoenix":"#00e5ff",
                    "System":"#4a7fa5",
                }
                rows_html = []
                for agent, items in groups.items():
                    col = _AG_COLORS.get(agent, "#4a7fa5")
                    for txt in items:
                        words = set(txt.lower().split())
                        if words & BULL_KW:
                            icon, ic = "▲", "#00e564"
                        elif words & BEAR_KW:
                            icon, ic = "▼", "#ef5350"
                        else:
                            icon, ic = "●", "#4a7fa5"

                        rows_html.append(
                            f'<tr>'
                            f'<td style="width:80px;padding:4px 8px;white-space:nowrap;">'
                            f'<span style="background:{col}22;color:{col};border:1px solid {col}44;'
                            f'padding:1px 7px;border-radius:8px;font-size:0.7rem;">{agent}</span></td>'
                            f'<td style="padding:4px 8px;font-size:0.78rem;color:#c8d6e5;">'
                            f'<span style="color:{ic};margin-right:6px;">{icon}</span>{txt}</td>'
                            f'</tr>'
                        )

                table_html = (
                    '<div style="background:#020408;border:1px solid #1e3a5f;border-radius:6px;'
                    'overflow:hidden;max-height:380px;overflow-y:auto;">'
                    '<table style="width:100%;border-collapse:collapse;">'
                    '<thead><tr>'
                    '<th style="background:#0d1321;color:#4a7fa5;font-size:0.68rem;'
                    'padding:6px 8px;text-align:left;border-bottom:1px solid #1e3a5f;">AGENT</th>'
                    '<th style="background:#0d1321;color:#4a7fa5;font-size:0.68rem;'
                    'padding:6px 8px;text-align:left;border-bottom:1px solid #1e3a5f;">EVIDENCE</th>'
                    '</tr></thead>'
                    '<tbody>' + "".join(rows_html) + '</tbody>'
                    '</table></div>'
                )
                st.markdown(table_html, unsafe_allow_html=True)

        # ── Watchlist summary ──────────────────────────────────
        if len(st.session_state.results) > 1:
            st.divider()
            st.markdown(f'<p class="section-hdr">{t("watchlist_sum")}</p>',
                        unsafe_allow_html=True)
            rows = []
            for sym, r in st.session_state.results.items():
                rows.append({
                    t("symbol_col"):  sym,
                    t("action_col"):  r.final_action.value,
                    t("tier_col"):    r.tier.label,
                    t("score_col"):   f"{r.final_score:.1f}",
                    "Orion":          f"{r.orion_score:.1f}"  if r.orion_score  else "—",
                    "Atlas":          f"{r.atlas_score:.1f}"  if r.atlas_score  else "—",
                    "Aether":         f"{r.aether_score:.1f}" if r.aether_score else "—",
                    t("regime_col"):  r.regime.value,
                    t("quality_col"): f"{r.data_quality:.2f}",
                })
            df_sum = pd.DataFrame(rows)

            def colour_action(val):
                if val in ("BUY", "AGGRESSIVE BUY", "ACCUMULATE"):
                    return "background-color:#1b3a1b;color:#69f0ae"
                if val == "SELL":
                    return "background-color:#3a1b1b;color:#ff8a80"
                if val == "HOLD":
                    return "background-color:#1a1e3a;color:#82b1ff"
                return "color:#616161"

            action_col_name = t("action_col")
            try:
                # pandas >= 2.1 uses .map(); older versions use .applymap()
                styled = df_sum.style.map(colour_action, subset=[action_col_name])
            except AttributeError:
                styled = df_sum.style.applymap(colour_action, subset=[action_col_name])
            st.dataframe(styled, use_container_width=True, hide_index=True)


# ──────────────────────────────────────────────────────────────
#  TAB 2 — TERMINAL
# ──────────────────────────────────────────────────────────────
with tab_terminal:
    st.markdown(
        f'<div style="font-size:0.65rem;color:#263238;letter-spacing:0.2em;margin-bottom:16px;">'
        f'{t("terminal_header")}</div>',
        unsafe_allow_html=True)

    ctrl1, ctrl2, ctrl3 = st.columns([2, 2, 1])
    with ctrl1:
        lvl_opts = ["ALL"] + [e.value for e in EventLevel]
        filt = st.selectbox(t("filter_lbl"), lvl_opts,
                             index=lvl_opts.index(st.session_state.terminal_filter))
        st.session_state.terminal_filter = filt
    with ctrl2:
        limit = st.slider(t("max_lines_lbl"), 50, 500, 150, 50)
    with ctrl3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button(t("clear_btn"), use_container_width=True):
            event_bus.clear()

    evs       = event_bus.get(limit)
    filt_evs  = evs if filt == "ALL" else [e for e in evs if e.level.value == filt]
    counts    = {}
    for e in evs:
        counts[e.level.value] = counts.get(e.level.value, 0) + 1

    css_colors = {
        "SYSTEM": "#00e5ff", "SUCCESS": "#00e564", "INFO": "#5a8fa5",
        "WARNING": "#ffa726", "ERROR": "#ef5350", "AGENT": "#ab47bc",
        "TRADE": "#ffd54f", "MACRO": "#26c6da",
    }
    stats_cols = st.columns(len(EventLevel))
    for i, lv in enumerate(EventLevel):
        with stats_cols[i]:
            c = css_colors.get(lv.value, "#4a7fa5")
            n = counts.get(lv.value, 0)
            st.markdown(
                f'<div style="text-align:center;padding:4px;">'
                f'<div style="color:{c};font-size:1.1rem;font-weight:700;">{n}</div>'
                f'<div style="color:#263238;font-size:0.6rem;">{lv.value}</div>'
                f'</div>', unsafe_allow_html=True)

    st.markdown(render_terminal(filt, limit), unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-size:0.6rem;color:#263238;margin-top:8px;">{t("terminal_tip")}</div>',
        unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
#  TAB 3 — PORTFOLIO ANALYST
# ──────────────────────────────────────────────────────────────
with tab_portfolio:
    brain  = _brain()
    rm     = brain.risk_manager
    ds     = brain.ds

    ae_op   = AetherAgent(ds).score()
    ae_sc   = ae_op.score
    policy  = rm._policy(ae_sc)

    total   = rm.cash + rm.invested_capital
    pnl_abs = total - rm.initial_equity
    pnl_pct = pnl_abs / rm.initial_equity * 100 if rm.initial_equity > 0 else 0.0

    # ── Snapshot metrics ──────────────────────────────────────
    st.markdown(f'<p class="section-hdr">{t("port_snapshot")}</p>',
                unsafe_allow_html=True)
    pm1, pm2, pm3, pm4, pm5, pm6 = st.columns(6)
    with pm1: st.metric(t("total_eq"),    f"${total:,.0f}")
    with pm2: st.metric(t("cash_lbl"),    f"${rm.cash:,.0f}",
                         delta=f"{rm.cash_ratio:.1%}")
    with pm3: st.metric(t("invested_lbl"),f"${rm.invested_capital:,.0f}")
    with pm4: st.metric(t("open_pos"),    len(rm.positions))   # ← BUG FIX: was rm.position_count
    with pm5:
        st.metric(t("total_pnl"), f"${pnl_abs:+,.0f}", delta=f"{pnl_pct:+.2f}%")
    with pm6:
        pol_col = {"NORMAL": "#00e564", "RISK_OFF": "#ffa726",
                   "DEEP_RISK_OFF": "#ef5350"}.get(policy.value, "#4a7fa5")
        st.markdown(
            f'<div style="font-size:0.7rem;color:#4a7fa5;margin-bottom:4px;">'
            f'{t("risk_policy")}</div>'
            f'<div style="font-size:0.85rem;color:{pol_col};font-weight:700;">'
            f'{policy.value}</div>',
            unsafe_allow_html=True)

    st.divider()

    # ── Macro grade ───────────────────────────────────────────
    macro_grade = AetherAgent.letter_grade(ae_sc)
    ae_col = score_color(ae_sc)
    st.markdown(
        f'<div style="background:#0d1321;border:1px solid #1e3a5f;border-radius:6px;'
        f'padding:12px 20px;margin-bottom:16px;">'
        f'<span style="color:#4a7fa5;font-size:0.7rem;letter-spacing:0.1em;">'
        f'{t("macro_regime")}</span>'
        f'<span style="color:{ae_col};font-size:1.1rem;font-weight:700;margin-left:16px;">'
        f'{macro_grade}</span>'
        f'<span style="color:#263238;font-size:0.75rem;margin-left:12px;">'
        f'Aether Score: {ae_sc:.1f}</span>'
        f'</div>',
        unsafe_allow_html=True)

    # ── Charts row ────────────────────────────────────────────
    ch1, ch2 = st.columns([1.4, 1])
    with ch1:
        st.plotly_chart(build_sector_chart(ds), use_container_width=True)
    with ch2:
        st.plotly_chart(build_portfolio_pie(rm), use_container_width=True)

    st.plotly_chart(
        build_equity_curve(rm.trade_history, rm.initial_equity),
        use_container_width=True)

    # ── Risk Metrics ──────────────────────────────────────────
    st.markdown(f'<p class="section-hdr">{t("risk_metrics_hdr")}</p>',
                unsafe_allow_html=True)
    rm1, rm2, rm3, rm4, rm5 = st.columns(5)
    rm_data = rm.metrics(ds, ae_sc)
    with rm1: st.metric(t("var95"),    f"${abs(rm_data.var_95):,.0f}")
    with rm2: st.metric(t("var99"),    f"${abs(rm_data.var_99):,.0f}")
    with rm3: st.metric(t("max_dd"),   f"{rm_data.max_drawdown*100:.1f}%")
    with rm4: st.metric(t("sharpe"),   f"{rm_data.sharpe_ratio:.2f}")
    with rm5: st.metric(t("cash_ratio"),f"{rm_data.cash_ratio:.1%}")

    st.divider()

    # ══════════════════════════════════════════════════════════
    #  VIRTUAL TRADING DESK
    # ══════════════════════════════════════════════════════════
    st.markdown(f'<p class="section-hdr">{t("virtual_hdr")}</p>',
                unsafe_allow_html=True)

    if not rm.positions:
        st.info(t("no_open_pos"))
    else:
        st.markdown(f'**{t("open_pos_hdr")}**')
        for sym, pos in list(rm.positions.items()):
            # Try to get live quote
            q     = ds.get_quote(sym)
            cur_p = q["price"] if q else pos.entry_price
            unr_pnl     = (cur_p - pos.entry_price) * pos.quantity
            unr_pnl_pct = (cur_p / pos.entry_price - 1) * 100
            pnl_col     = "#00e564" if unr_pnl >= 0 else "#ef5350"
            days_held   = (datetime.now() - pos.entry_time).days

            row_c1, row_c2 = st.columns([5, 1])
            with row_c1:
                st.markdown(
                    f'<div class="pos-card">'
                    f'<span style="color:#00e5ff;font-weight:700;font-size:1rem;">{sym}</span>'
                    f'{_exch_badge(STOCK_UNIVERSE.get(sym, {}).get("exchange", ""))}'
                    f'<span style="color:#37474f;font-size:0.7rem;margin-left:12px;">'
                    f'{pos.sector}</span><br>'
                    f'<span style="color:#4a7fa5;font-size:0.78rem;">'
                    f'Entry: <b style="color:#c8d6e5;">${pos.entry_price:.2f}</b> &nbsp;·&nbsp; '
                    f'Now: <b style="color:#c8d6e5;">${cur_p:.2f}</b> &nbsp;·&nbsp; '
                    f'Qty: <b style="color:#c8d6e5;">{pos.quantity:.2f}</b> &nbsp;·&nbsp; '
                    f'SL: <b style="color:#ef5350;">${pos.stop_loss:.2f}</b> &nbsp;·&nbsp; '
                    f'TP: <b style="color:#00e564;">${pos.target:.2f}</b> &nbsp;·&nbsp; '
                    f'{days_held}d held'
                    f'</span><br>'
                    f'<span style="color:{pnl_col};font-size:0.9rem;font-weight:700;">'
                    f'P&L: ${unr_pnl:+,.2f} ({unr_pnl_pct:+.1f}%)</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with row_c2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button(t("close_pos_btn"), key=f"close_{sym}", use_container_width=True):
                    ok, msg = execute_virtual_close(sym)
                    if ok:
                        st.success(f"{t('close_success')} — {msg}")
                    else:
                        st.error(msg)
                    st.rerun()

    # ── Position Sizing Calculator ────────────────────────────
    with st.expander(t("sizer_exp"), expanded=False):
        st.markdown(f'<p class="section-hdr">{t("sizer_hdr")}</p>',
                    unsafe_allow_html=True)
        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1: entry_p  = st.number_input(t("entry_price_inp"), value=100.0, step=0.5, min_value=0.01)
        with sc2: stop_p   = st.number_input(t("stop_inp"),        value=96.0,  step=0.5, min_value=0.01)
        with sc3:
            tier_opts = {t_item.label: t_item for t_item in DecisionTier if t_item != DecisionTier.REJECTED}
            tier_sel  = st.selectbox(t("tier_sel"), list(tier_opts.keys()))
        with sc4: ae_inp   = st.slider(t("aether_sl"), 0, 100, int(ae_sc))

        if entry_p > stop_p:
            sizing = rm.calc_size(entry_p, stop_p, tier_opts[tier_sel], ae_inp)
            validation_ok, msgs = rm.validate(
                "CALC", entry_p, sizing["shares"], "Technology", ae_inp)

            s1, s2, s3, s4 = st.columns(4)
            with s1: st.metric(t("shares_lbl"),  f"{sizing['shares']:.2f}")
            with s2: st.metric(t("pos_val_lbl"),  f"${sizing['pos_value']:,.0f}")
            with s3: st.metric(t("risk_amt_lbl"), f"${sizing['risk_amt']:,.0f}")
            with s4: st.metric(t("risk_pct_lbl"), f"{sizing['risk_pct']*100:.1f}%")

            for msg in msgs:
                if "❌" in msg:
                    st.error(msg)
                elif "⚠️" in msg:
                    st.warning(msg)
                else:
                    st.success(msg)
            if not msgs:
                st.success(t("trade_approved"))

    # ── Trade History ─────────────────────────────────────────
    with st.expander(t("trade_hist_exp"), expanded=False):
        if rm.trade_history:
            hist_rows = []
            for t_item in reversed(rm.trade_history):
                row = {
                    "Time":   t_item["time"].strftime("%Y-%m-%d %H:%M") if isinstance(t_item["time"], datetime) else str(t_item["time"]),
                    "Symbol": t_item.get("symbol", "—"),
                    "Action": t_item.get("action", "—"),
                    "Price":  f"${t_item.get('price', t_item.get('exit', 0)):.2f}",
                    "Shares": f"{t_item.get('shares', 0):.2f}",
                    "PnL":    f"${t_item.get('pnl', 0):+.2f}" if "pnl" in t_item else "—",
                }
                hist_rows.append(row)
            st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)
        else:
            st.info(t("no_trades"))

    # ── Sector Heatmap ────────────────────────────────────────
    with st.expander(t("sector_hm_exp"), expanded=False):
        dem = DemeterAgent(ds)
        scs = dem.all_sector_scores()
        if scs:
            df_s = pd.DataFrame(list(scs.items()), columns=["Sector", "Score"])
            df_s = df_s.sort_values("Score", ascending=False)
            df_s["Status"] = df_s["Score"].apply(
                lambda x: "Strong" if x >= 65 else ("Neutral" if x >= 45 else "Weak"))
            df_s["Color"]  = df_s["Score"].apply(score_color)

            fig_hm = go.Figure(go.Bar(
                x=df_s["Score"], y=df_s["Sector"], orientation="h",
                marker_color=df_s["Color"].tolist(),
                text=[f"{v:.1f}" for v in df_s["Score"]],
                textposition="outside",
            ))
            fig_hm.add_vline(x=50, line=dict(color="#37474f", dash="dot", width=1))
            fig_hm.update_layout(
                title="Sector Scores (Demeter)", height=360, **_PLOT_LAYOUT)
            st.plotly_chart(fig_hm, use_container_width=True)
