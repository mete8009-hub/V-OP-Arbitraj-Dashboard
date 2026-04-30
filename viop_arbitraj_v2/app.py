"""
VİOP / Spot Pair Arbitraj Dashboard
===================================

Bu dosya eski app.py yerine kopyalanabilir.

Ana özellikler:
- Vadeli pay piyasası dayanaklarını tarar: Spot hisse ↔ aynı hissenin VİOP kontratı.
- Sidebar'dan izlenecek dayanaklar, vade sayısı ve top-N değiştirilebilir.
- Özel pair analizi yapar:
    * Spot ↔ VİOP
    * Spot ↔ Spot
    * VİOP ↔ VİOP
    * Farklı dayanaklar: örn. THYAO spot ↔ F_PGSUS0526
- Spot/VİOP sembolleri dropdown üzerinden seçilebilir.

Not:
Aynı dayanak dışındaki eşleşmeler klasik risksiz arbitraj değildir; relative-value/spread analizidir.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
import logging
import re
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
import pytz
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from src.arbitrage import calculate_arbitrage
from src.config import (
    ALL_EXPIRIES,
    DASHBOARD_STOCKS,
    DIVIDEND_CACHE_TTL_SEC,
    MONTHS_TR,
    REFRESH_INTERVAL_SEC,
    SPOT_COMMISSION_RATE,
    VIOP_COMMISSION_RATE,
    days_to_maturity,
    get_active_contract_months,
    get_viop_code,
)
from src.data_fetcher import DataFetcher, DividendFetcher

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

IST = pytz.timezone("Europe/Istanbul")

# -----------------------------------------------------------------------------
# VİOP pay vadeli dayanak evreni
# -----------------------------------------------------------------------------
# Buradaki liste bilerek geniş tutuldu. Veri kaynağında olmayan semboller zaten fiyat
# üretmez. Pair seçimi özel analiz ekranındaki dropdown menülerinden yapılır.
COMMON_VIOP_UNDERLYINGS = [
    "AEFES", "AGHOL", "AKBNK", "AKSEN", "ALARK", "ARCLK", "ASELS", "ASTOR",
    "BIMAS", "BRSAN", "CCOLA", "CIMSA", "DOAS", "DOHOL", "EKGYO", "ENJSA",
    "ENKAI", "EREGL", "FROTO", "GARAN", "GUBRF", "HALKB", "HEKTS", "ISCTR",
    "ISDMR", "KCHOL", "KONTR", "KORDS", "KOZAA", "KOZAL", "KRDMD", "MGROS",
    "ODAS", "OYAKC", "PETKM", "PGSUS", "SAHOL", "SASA", "SISE", "SOKM",
    "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO", "TRALT", "TRMET", "TSKB",
    "TTKOM", "TUPRS", "ULKER", "VAKBN", "VESTL", "YKBNK",
]

DEFAULT_UNDERLYINGS = sorted(set(DASHBOARD_STOCKS + COMMON_VIOP_UNDERLYINGS))
DEFAULT_FOCUS = [
    "AKBNK", "GARAN", "ISCTR", "YKBNK", "THYAO", "PGSUS", "EREGL", "SISE",
    "ASELS", "KCHOL", "TUPRS", "BIMAS", "FROTO", "SAHOL", "TCELL",
]

# -----------------------------------------------------------------------------
# Sayfa ayarı
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="VİOP / Spot Pair Arbitraj",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    /* Main canvas: force a clean light workspace even if the browser/app theme is dark */
    [data-testid="stAppViewContainer"] {
        background: #f5f7fb !important;
    }
    [data-testid="stMain"] {
        background: #f5f7fb !important;
    }
    .block-container {
        padding-top: 1.1rem;
        padding-bottom: 2rem;
        max-width: 1520px;
        color: #111827 !important;
    }

    /* Keep all main-area native text readable on the light background */
    .block-container h1,
    .block-container h2,
    .block-container h3,
    .block-container h4,
    .block-container h5,
    .block-container h6,
    .block-container p,
    .block-container label,
    .block-container span,
    .block-container div {
        color: #111827;
    }

    [data-testid="stHeader"] {
        background: transparent !important;
    }

    /* Native metric cards */
    .block-container div[data-testid="stMetric"] {
        background: #ffffff !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 14px !important;
        padding: 14px 16px !important;
        box-shadow: 0 1px 4px rgba(15, 23, 42, 0.06) !important;
    }
    .block-container div[data-testid="stMetric"] label,
    .block-container div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
        color: #6b7280 !important;
        font-size: 12px !important;
    }
    .block-container div[data-testid="stMetricValue"] {
        color: #111827 !important;
        font-weight: 800 !important;
    }
    .block-container div[data-testid="stMetricDelta"] {
        color: #047857 !important;
    }

    /* Tabs and dataframe readability */
    .block-container button[role="tab"] {
        color: #111827 !important;
        font-weight: 650 !important;
    }
    .block-container div[data-testid="stDataFrame"] {
        background: #ffffff !important;
        border-radius: 12px !important;
    }

    /* Info boxes should stay readable */
    .block-container [data-testid="stAlert"] * {
        color: #111827 !important;
    }


    /* Force Streamlit dropdowns to stay readable on light canvas */
    .block-container [data-testid="stSelectbox"] [data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 10px !important;
        color: #111827 !important;
        box-shadow: none !important;
    }
    .block-container [data-testid="stSelectbox"] [data-baseweb="select"] span,
    .block-container [data-testid="stSelectbox"] [data-baseweb="select"] div,
    .block-container [data-testid="stSelectbox"] [data-baseweb="select"] input {
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
    }
    .block-container [data-testid="stSelectbox"] svg {
        color: #111827 !important;
        fill: #111827 !important;
    }

    /* Dropdown menu/popover readability */
    div[data-baseweb="popover"],
    div[data-baseweb="popover"] * {
        color: #111827 !important;
    }
    div[data-baseweb="popover"] ul,
    div[data-baseweb="popover"] [role="listbox"],
    div[data-baseweb="popover"] [data-baseweb="menu"] {
        background-color: #ffffff !important;
        color: #111827 !important;
    }
    div[data-baseweb="popover"] li,
    div[data-baseweb="popover"] [role="option"] {
        background-color: #ffffff !important;
        color: #111827 !important;
    }
    div[data-baseweb="popover"] li:hover,
    div[data-baseweb="popover"] [role="option"]:hover {
        background-color: #eef2ff !important;
        color: #111827 !important;
    }

    /* Inputs/number inputs used in advanced controls */
    .block-container [data-testid="stTextInput"] input,
    .block-container [data-testid="stNumberInput"] input {
        background-color: #ffffff !important;
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
        border: 1px solid #cbd5e1 !important;
    }

    /* Selection color: prevents the aggressive blue block look when text is accidentally selected */
    ::selection {
        background: #dbeafe;
        color: #111827;
    }
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Yardımcı fonksiyonlar
# -----------------------------------------------------------------------------
def now_ist() -> datetime:
    return datetime.now(IST)


def normalize_symbol(x: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "", str(x or "").strip().upper())


def parse_manual_symbols(text: str) -> List[str]:
    if not text:
        return []
    raw = re.split(r"[,;\n\s]+", text.upper())
    return [normalize_symbol(x) for x in raw if normalize_symbol(x)]


def fmt_pct(x: Optional[float]) -> str:
    if x is None or pd.isna(x):
        return "-"
    return f"{x:,.2f}%"


def fmt_price(x: Optional[float]) -> str:
    if x is None or pd.isna(x):
        return "-"
    return f"{x:,.2f}"


def get_dividend_for_period(div_data: dict, symbol: str, today: date, expiry: date) -> float:
    rows = div_data.get(symbol, []) or []
    total = 0.0
    for r in rows:
        ex = r.get("ex_date")
        amt = float(r.get("amount", 0.0) or 0.0)
        if ex and today < ex <= expiry:
            total += amt
    return total


def get_dividend_calendar_view(div_data: dict, contract_months: list) -> dict:
    out = {key: [] for key in contract_months}
    today = now_ist().date()
    for sym, rows in (div_data or {}).items():
        for r in rows or []:
            ex = r.get("ex_date")
            if not ex or ex < today:
                continue
            key = (ex.month, ex.year)
            if key in out and sym not in out[key]:
                out[key].append(sym)
    return out


def parse_viop_contract(code: str, candidates: Iterable[str]) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """F_AKBNK0526 -> (AKBNK, 5, 2026)."""
    c = normalize_symbol(code)
    if not c.startswith("F_"):
        c = "F_" + c if c.startswith("F") and not c.startswith("F_") else c
    if not c.startswith("F_"):
        return None, None, None

    body = c[2:]
    m = re.search(r"(\d{4})$", body)
    if not m:
        return None, None, None
    mm_yy = m.group(1)
    month = int(mm_yy[:2])
    year = 2000 + int(mm_yy[2:])
    prefix = body[:-4]

    candidate_set = sorted(set(candidates), key=len, reverse=True)
    for sym in candidate_set:
        if prefix == sym:
            return sym, month, year
    return prefix or None, month, year


def expiry_from_contract(code: str, candidates: Iterable[str]) -> Optional[date]:
    _sym, month, year = parse_viop_contract(code, candidates)
    if month and year:
        return ALL_EXPIRIES.get((month, year))
    return None


def infer_underlying_from_contract(code: str, candidates: Iterable[str]) -> Optional[str]:
    sym, _m, _y = parse_viop_contract(code, candidates)
    return sym


def make_contract_options(underlyings: List[str], contract_months: List[Tuple[int, int]]) -> List[str]:
    opts = []
    for sym in underlyings:
        for month, year in contract_months:
            opts.append(get_viop_code(sym, month, year))
    return sorted(set(opts))


def effective_commission(instrument_type: str) -> float:
    return SPOT_COMMISSION_RATE if instrument_type == "Spot" else VIOP_COMMISSION_RATE


# -----------------------------------------------------------------------------
# Cache'li veri çekme
# -----------------------------------------------------------------------------
@st.cache_data(ttl=REFRESH_INTERVAL_SEC, show_spinner=False)
def cached_fetch_market_data(symbols_tuple: Tuple[str, ...]) -> Tuple[Dict[str, float], Dict[str, float]]:
    symbols = list(symbols_tuple)
    fetcher = DataFetcher()
    spots = fetcher.fetch_all_spot_prices()
    viops = fetcher.fetch_all_viop_prices(symbols)
    return spots or {}, viops or {}


@st.cache_data(ttl=DIVIDEND_CACHE_TTL_SEC, show_spinner=False)
def cached_fetch_dividends(symbols_tuple: Tuple[str, ...]) -> dict:
    fetcher = DividendFetcher()
    return fetcher.fetch_dividends_bulk(list(symbols_tuple)) or {}


def fetch_missing_viop_contract(contract_code: str, viops: Dict[str, float], underlyings: List[str]) -> Dict[str, float]:
    """Manuel girilen kontrat seçili evrende yoksa tek dayanak için yeniden dene."""
    c = normalize_symbol(contract_code)
    if c in viops:
        return viops
    underlying = infer_underlying_from_contract(c, underlyings)
    if not underlying:
        return viops
    try:
        fetched = DataFetcher().fetch_viop_for_symbol(underlying) or {}
        viops.update(fetched)
    except Exception as exc:
        log.warning("Manual VIOP fetch failed for %s: %s", c, exc)
    return viops


# -----------------------------------------------------------------------------
# Hesaplama fonksiyonları
# -----------------------------------------------------------------------------
def build_same_underlying_df(
    spots: Dict[str, float],
    viops: Dict[str, float],
    divs: dict,
    today: date,
    contract_months: List[Tuple[int, int]],
    selected_symbols: List[str],
) -> pd.DataFrame:
    rows = []
    for month, year in contract_months:
        expiry = ALL_EXPIRIES.get((month, year))
        if not expiry:
            continue
        for sym in selected_symbols:
            spot = spots.get(sym)
            code = get_viop_code(sym, month, year)
            viop = viops.get(code)
            dividend = get_dividend_for_period(divs, sym, today, expiry)
            r = calculate_arbitrage(sym, spot, viop, expiry, today, dividend=dividend)
            if not r.is_active:
                continue
            rows.append(
                {
                    "Spot Hisse": sym,
                    "VİOP Kontrat": code,
                    "Vade": f"{MONTHS_TR[month - 1]} {year}",
                    "Vade Tarihi": expiry,
                    "DTM": r.dtm,
                    "Spot Fiyat": r.spot_price,
                    "VİOP Fiyat": r.viop_price,
                    "Temettü": r.dividend,
                    "Spread TL": r.spread,
                    "Spread %": r.spread_pct,
                    "Yıllık Getiri %": r.annualized_return,
                    "Pair": f"{sym} Spot / {code}",
                    "İşlem Mantığı": "Spot Al / VİOP Sat",
                }
            )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.sort_values("Yıllık Getiri %", ascending=False).reset_index(drop=True)


def resolve_price(
    inst_type: str,
    symbol: str,
    spots: Dict[str, float],
    viops: Dict[str, float],
    underlyings: List[str],
) -> Tuple[Optional[float], str, Optional[str], Optional[date]]:
    """Fiyatı veri sözlüğünden bulur. Dönüş: fiyat, temiz sembol, dayanak, expiry."""
    clean = normalize_symbol(symbol)
    if inst_type == "Spot":
        return spots.get(clean), clean, clean, None

    # VİOP tarafı
    if not clean.startswith("F_"):
        clean = "F_" + clean[1:] if clean.startswith("F") else clean
    if clean not in viops:
        viops = fetch_missing_viop_contract(clean, viops, underlyings)
    underlying = infer_underlying_from_contract(clean, underlyings)
    expiry = expiry_from_contract(clean, underlyings)
    return viops.get(clean), clean, underlying, expiry


def calculate_custom_pair(
    long_type: str,
    long_symbol: str,
    short_type: str,
    short_symbol: str,
    long_price: float,
    short_price: float,
    divs: dict,
    today: date,
    holding_days: int,
    underlyings: List[str],
    include_dividends: bool = True,
) -> dict:
    long_sym_clean = normalize_symbol(long_symbol)
    short_sym_clean = normalize_symbol(short_symbol)

    long_underlying = long_sym_clean if long_type == "Spot" else infer_underlying_from_contract(long_sym_clean, underlyings)
    short_underlying = short_sym_clean if short_type == "Spot" else infer_underlying_from_contract(short_sym_clean, underlyings)

    long_comm = effective_commission(long_type)
    short_comm = effective_commission(short_type)

    long_cost = long_price * (1 + long_comm)
    short_proceeds = short_price * (1 - short_comm)

    dividend_adj = 0.0
    maturity_date = today + timedelta(days=max(holding_days, 1))

    if include_dividends:
        # Long spot ise temettü alınır; short spot ise temettü borcu doğar.
        if long_type == "Spot" and long_underlying:
            dividend_adj += get_dividend_for_period(divs, long_underlying, today, maturity_date)
        if short_type == "Spot" and short_underlying:
            dividend_adj -= get_dividend_for_period(divs, short_underlying, today, maturity_date)

    spread_tl = short_proceeds + dividend_adj - long_cost
    spread_pct = (spread_tl / long_price) * 100 if long_price else 0.0
    annualized = spread_pct * (365 / max(holding_days, 1))

    is_same_underlying = bool(long_underlying and short_underlying and long_underlying == short_underlying)
    is_classic_spot_future = is_same_underlying and {long_type, short_type} == {"Spot", "VİOP"}

    return {
        "Long Bacak": f"{long_type} {long_sym_clean}",
        "Short Bacak": f"{short_type} {short_sym_clean}",
        "Long Fiyat": long_price,
        "Short Fiyat": short_price,
        "Long Komisyon": long_comm,
        "Short Komisyon": short_comm,
        "Dividend Adj.": dividend_adj,
        "Spread TL": spread_tl,
        "Spread %": spread_pct,
        "Yıllıklandırılmış %": annualized,
        "Holding Gün": holding_days,
        "Aynı Dayanak mı?": "Evet" if is_same_underlying else "Hayır",
        "Klasik Spot-VİOP Arbitraj mı?": "Evet" if is_classic_spot_future else "Hayır",
        "Long Dayanak": long_underlying or "-",
        "Short Dayanak": short_underlying or "-",
    }


# -----------------------------------------------------------------------------
# Grafik ve tablo render
# -----------------------------------------------------------------------------
def render_top_bar_chart(
    df: pd.DataFrame,
    title: str,
    top_n: int,
    value_col: str = "Yıllık Getiri %",
    label_col: str = "Pair",
    positive_only: bool = False,
) -> go.Figure:
    if df.empty or value_col not in df.columns:
        fig = go.Figure()
        fig.update_layout(
            title=dict(text=title, font=dict(color="#111827")),
            height=360,
            paper_bgcolor="white",
            plot_bgcolor="white",
            font=dict(color="#111827"),
            annotations=[
                dict(
                    text="Gösterilecek veri yok",
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font=dict(size=14, color="#6b7280"),
                )
            ],
        )
        return fig

    work = df.copy()
    if positive_only:
        work = work[work[value_col] > 0]
    work = work.sort_values(value_col, ascending=False).head(top_n)
    work = work.iloc[::-1]

    colors = ["#047857" if v >= 0 else "#b91c1c" for v in work[value_col]]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=work[value_col],
            y=work[label_col],
            orientation="h",
            marker_color=colors,
            text=[f"{v:.1f}%" for v in work[value_col]],
            textposition="outside",
            cliponaxis=False,
            customdata=work[["Spot Fiyat", "VİOP Fiyat", "Spread %", "DTM"]].values
            if all(c in work.columns for c in ["Spot Fiyat", "VİOP Fiyat", "Spread %", "DTM"])
            else None,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Yıllık Getiri: %{x:.2f}%<br>"
                "Spot: %{customdata[0]:.2f}<br>"
                "VİOP: %{customdata[1]:.2f}<br>"
                "Spread: %{customdata[2]:.2f}%<br>"
                "DTM: %{customdata[3]}<extra></extra>"
            )
            if all(c in work.columns for c in ["Spot Fiyat", "VİOP Fiyat", "Spread %", "DTM"])
            else "<b>%{y}</b><br>%{x:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", x=0.01, xanchor="left"),
        height=max(380, 36 * max(len(work), 7)),
        margin=dict(l=10, r=80, t=52, b=34),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(color="#111827", size=12),
        title_font=dict(color="#111827", size=16),
        xaxis=dict(
            title="Yıllıklandırılmış Getiri (%)",
            title_font=dict(color="#374151"),
            tickfont=dict(color="#374151"),
            showgrid=True,
            gridcolor="#e5e7eb",
            zeroline=True,
            zerolinecolor="#9ca3af",
        ),
        yaxis=dict(title="", automargin=True, tickfont=dict(color="#374151", size=12)),
    )
    return fig


def render_metric_card(label: str, value: str, note: str = "") -> None:
    """Metric card rendered with native Streamlit components to avoid theme/color conflicts."""
    st.metric(label, value)
    if note:
        st.caption(note)


def render_header_pills(today: date, contract_months: List[Tuple[int, int]], selected_count: int) -> None:
    """Compact top status row rendered with native Streamlit metrics."""
    items = [
        ("Bugün", today.strftime("%d.%m.%Y")),
        ("T+2", (today + timedelta(days=2)).strftime("%d.%m.%Y")),
        ("Dayanak", str(selected_count)),
    ]
    for month, year in contract_months:
        expiry = ALL_EXPIRIES.get((month, year))
        if expiry:
            items.append((
                f"{MONTHS_TR[month - 1]} {year}",
                f"{expiry.strftime('%d.%m.%Y')} | DTM {max(days_to_maturity(today, expiry), 0)}",
            ))

    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        with col:
            st.metric(label, value)


def display_df(df: pd.DataFrame, height: int = 420) -> None:
    if df.empty:
        st.info("Gösterilecek veri yok.")
        return
    styled = df.copy()
    numeric_cols = [
        "Spot Fiyat", "VİOP Fiyat", "Temettü", "Spread TL", "Spread %",
        "Yıllık Getiri %", "Long Fiyat", "Short Fiyat", "Dividend Adj.",
        "Yıllıklandırılmış %",
    ]
    for col in numeric_cols:
        if col in styled.columns:
            styled[col] = pd.to_numeric(styled[col], errors="coerce").round(2)
    st.dataframe(styled, use_container_width=True, hide_index=True, height=height)


# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
st.sidebar.title("Kontroller")

mode = st.sidebar.radio(
    "Analiz Modu",
    ["Aynı Dayanak Taraması", "Özel Pair Analizi"],
    index=0,
)

auto_refresh = st.sidebar.toggle("Otomatik yenile", value=True)
refresh_sec = st.sidebar.slider("Yenileme aralığı", 10, 120, int(REFRESH_INTERVAL_SEC), step=5)
if auto_refresh:
    st_autorefresh(interval=refresh_sec * 1000, key="viop_pair_dashboard_refresh")

st.sidebar.divider()
st.sidebar.subheader("Dayanak Evreni")
all_candidate_underlyings = sorted(set(DEFAULT_UNDERLYINGS))

use_full_universe = st.sidebar.toggle(
    "Tüm vadeli pay dayanak evrenini tara",
    value=False,
    help="Açık olursa geniş evren taranır. Kapalı olursa seçtiğin hisseler taranır; daha hızlıdır.",
)

if use_full_universe:
    selected_underlyings = all_candidate_underlyings
else:
    selected_underlyings = st.sidebar.multiselect(
        "Taranacak dayanak hisseler",
        options=all_candidate_underlyings,
        default=[x for x in DEFAULT_FOCUS if x in all_candidate_underlyings],
        help="Aynı dayanak taramasında Spot Hisse ↔ aynı hissenin VİOP kontratı hesaplanır.",
    )

if not selected_underlyings:
    selected_underlyings = ["AKBNK"]

st.sidebar.caption(f"Aktif tarama evreni: {len(selected_underlyings)} dayanak")

contract_count = st.sidebar.slider("Aktif vade sayısı", 1, 5, 3)
top_n = st.sidebar.slider("Grafikte gösterilecek maksimum pair", 5, 30, 12)
positive_only = st.sidebar.toggle("Grafikte sadece pozitifleri göster", value=False)

# -----------------------------------------------------------------------------
# Veri çek
# -----------------------------------------------------------------------------
today = now_ist().date()
contract_months = get_active_contract_months(today, count=contract_count)
viop_contract_options = make_contract_options(selected_underlyings, contract_months)

with st.spinner("Spot, VİOP ve temettü verileri çekiliyor..."):
    spots, viops = cached_fetch_market_data(tuple(sorted(selected_underlyings)))
    divs = cached_fetch_dividends(tuple(sorted(selected_underlyings)))

# Spot seçenekleri: veri kaynağından gelen tüm spot semboller + seçili dayanaklar
spot_options = sorted(set(spots.keys()) | set(selected_underlyings))
# VİOP seçenekleri: veri kaynağından gelen gerçek kontratlar + üretilen kontratlar
viop_options = sorted(set(viops.keys()) | set(viop_contract_options))

# -----------------------------------------------------------------------------
# Başlık
# -----------------------------------------------------------------------------
st.title("VİOP / Spot Pair Arbitraj Dashboard")
st.caption(
    "Spot hisse, vadeli pay kontratı ve özel pair/spread analizleri. "
    "Aynı dayanak dışındaki eşleşmeler klasik arbitraj değil, relative-value analizidir."
)

render_header_pills(today, contract_months, len(selected_underlyings))

c1, c2, c3, c4 = st.columns(4)
with c1:
    render_metric_card("Spot fiyat adedi", str(len(spots)), "İş Yatırım spot evreni")
with c2:
    render_metric_card("VİOP fiyat adedi", str(len(viops)), "Seçili dayanaklardan çekilen kontratlar")
with c3:
    render_metric_card("Temettü kaydı", str(sum(len(v or []) for v in divs.values())), "Seçili evren içinde")
with c4:
    render_metric_card("Son güncelleme", now_ist().strftime("%H:%M:%S"), "Europe/Istanbul")

if len(spots) == 0 or len(viops) == 0:
    st.warning(
        "Spot veya VİOP verisi boş görünüyor. Veri Testi sayfasından endpoint detaylarını kontrol et. "
        "Veri geldikten sonra bu ekran otomatik dolacaktır."
    )

# -----------------------------------------------------------------------------
# Mod 1: Aynı dayanak taraması
# -----------------------------------------------------------------------------
if mode == "Aynı Dayanak Taraması":
    st.subheader("Aynı Dayanak Spot ↔ VİOP Taraması")
    st.info(
        "Bu mod klasik tarama modudur: her satırda spot hisse alınır, "
        "aynı dayanağın ilgili VİOP kontratı satılır. Örn: AKBNK Spot ↔ F_AKBNK0526."
    )

    scan_df = build_same_underlying_df(
        spots=spots,
        viops=viops,
        divs=divs,
        today=today,
        contract_months=contract_months,
        selected_symbols=selected_underlyings,
    )

    if scan_df.empty:
        st.error("Seçili evren için hesaplanabilir pair bulunamadı. Dayanak listesini veya veri bağlantısını kontrol et.")
    else:
        # Özet
        best = scan_df.iloc[0]
        avg_ret = scan_df["Yıllık Getiri %"].mean()
        med_ret = scan_df["Yıllık Getiri %"].median()
        positive_count = int((scan_df["Yıllık Getiri %"] > 0).sum())

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("En yüksek pair", best["Pair"], f"{best['Yıllık Getiri %']:.2f}%")
        with m2:
            st.metric("Ortalama yıllık getiri", f"{avg_ret:.2f}%")
        with m3:
            st.metric("Medyan yıllık getiri", f"{med_ret:.2f}%")
        with m4:
            st.metric("Pozitif pair", f"{positive_count}/{len(scan_df)}")

        # Vade bazlı tablar
        tabs = st.tabs([f"{MONTHS_TR[m - 1]} {y}" for m, y in contract_months] + ["Tüm Detay Tablo"])

        for idx, (month, year) in enumerate(contract_months):
            vade_label = f"{MONTHS_TR[month - 1]} {year}"
            vade_df = scan_df[scan_df["Vade"] == vade_label].copy()
            with tabs[idx]:
                if vade_df.empty:
                    st.info(f"{vade_label} için veri yok.")
                    continue

                left, right = st.columns([1.65, 1.0], gap="large")
                with left:
                    fig = render_top_bar_chart(
                        vade_df,
                        title=f"{vade_label} - Top {top_n} Spot/VİOP Fırsatı",
                        top_n=top_n,
                        positive_only=positive_only,
                    )
                    st.plotly_chart(fig, use_container_width=True)

                with right:
                    st.subheader("Top Pair Tablosu")
                    cols = [
                        "Spot Hisse", "VİOP Kontrat", "Spot Fiyat", "VİOP Fiyat",
                        "Temettü", "Spread %", "Yıllık Getiri %", "DTM",
                    ]
                    display_df(vade_df[cols].head(top_n), height=430)

        with tabs[-1]:
            st.subheader("Tüm Hesaplanabilir Pairler")
            display_cols = [
                "Pair", "Vade", "Spot Fiyat", "VİOP Fiyat", "Temettü", "Spread TL",
                "Spread %", "Yıllık Getiri %", "DTM", "İşlem Mantığı",
            ]
            display_df(scan_df[display_cols], height=560)
            csv = scan_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "CSV indir",
                data=csv,
                file_name=f"viop_spot_arbitraj_{today.strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

# -----------------------------------------------------------------------------
# Mod 2: Özel pair analizi
# -----------------------------------------------------------------------------
else:
    st.subheader("Özel Pair Analizi")
    st.warning(
        "Önemli: AKBNK Spot ↔ F_AKBNK0526 aynı dayanak olduğu için klasik spot-vadeli arbitrajdır. "
        "THYAO Spot ↔ F_PGSUS0526, Spot ↔ Spot veya VİOP ↔ VİOP eşleşmeleri ise fiyat/spread karşılaştırmasıdır; "
        "bunları risksiz arbitraj gibi yorumlama."
    )

    left_cfg, right_cfg = st.columns(2, gap="large")

    with left_cfg:
        st.markdown("### 1. Bacak: Long / Alınacak")
        long_type = st.radio("Long enstrüman tipi", ["Spot", "VİOP"], horizontal=True, key="long_type")
        if long_type == "Spot":
            default_idx = spot_options.index("THYAO") if "THYAO" in spot_options else 0
            long_choice = st.selectbox("Long spot hisse", spot_options, index=default_idx, key="long_spot_select")
            long_symbol = normalize_symbol(long_choice)
        else:
            default_contract = get_viop_code("AKBNK", contract_months[0][0], contract_months[0][1]) if contract_months else "F_AKBNK0526"
            default_idx = viop_options.index(default_contract) if default_contract in viop_options else 0
            long_choice = st.selectbox("Long VİOP kontratı", viop_options, index=default_idx, key="long_viop_select")
            long_symbol = normalize_symbol(long_choice)

    with right_cfg:
        st.markdown("### 2. Bacak: Short / Satılacak")
        short_type = st.radio("Short enstrüman tipi", ["Spot", "VİOP"], horizontal=True, key="short_type", index=1)
        if short_type == "Spot":
            default_idx = spot_options.index("PGSUS") if "PGSUS" in spot_options else 0
            short_choice = st.selectbox("Short spot hisse", spot_options, index=default_idx, key="short_spot_select")
            short_symbol = normalize_symbol(short_choice)
        else:
            default_contract = get_viop_code("PGSUS", contract_months[0][0], contract_months[0][1]) if contract_months else "F_PGSUS0526"
            default_idx = viop_options.index(default_contract) if default_contract in viop_options else 0
            short_choice = st.selectbox("Short VİOP kontratı", viop_options, index=default_idx, key="short_viop_select")
            short_symbol = normalize_symbol(short_choice)

    long_price, long_clean, long_underlying, long_expiry = resolve_price(
        long_type, long_symbol, spots, viops, selected_underlyings
    )
    short_price, short_clean, short_underlying, short_expiry = resolve_price(
        short_type, short_symbol, spots, viops, selected_underlyings
    )

    # Otomatik holding günü: VİOP varsa en yakın vade; yoksa manuel 30 gün.
    candidate_expiries = [x for x in [long_expiry, short_expiry] if x is not None and x > today]
    auto_expiry = min(candidate_expiries) if candidate_expiries else None
    auto_days = max((auto_expiry - today).days, 1) if auto_expiry else 30

    st.divider()
    settings_col1, settings_col2, settings_col3 = st.columns(3)
    with settings_col1:
        holding_days = st.number_input(
            "Holding / vade günü",
            min_value=1,
            max_value=730,
            value=int(auto_days),
            step=1,
            help="Yıllıklandırma için kullanılır. VİOP seçilirse otomatik en yakın vade önerilir.",
        )
    with settings_col2:
        include_dividends = st.toggle("Spot temettü etkisini dahil et", value=True)
    with settings_col3:
        allow_manual_price = st.toggle("Fiyatı manuel override et", value=False)

    if allow_manual_price:
        p1, p2 = st.columns(2)
        with p1:
            long_price = st.number_input("Long fiyat override", min_value=0.0, value=float(long_price or 0.0), step=0.01)
        with p2:
            short_price = st.number_input("Short fiyat override", min_value=0.0, value=float(short_price or 0.0), step=0.01)

    # Veri kontrol
    if not long_price or not short_price:
        st.error(
            f"Fiyat bulunamadı. Long: {long_type} {long_clean} -> {long_price}, "
            f"Short: {short_type} {short_clean} -> {short_price}. "
            "Sembolü kontrol et veya manuel fiyat override kullan."
        )
    else:
        result = calculate_custom_pair(
            long_type=long_type,
            long_symbol=long_clean,
            short_type=short_type,
            short_symbol=short_clean,
            long_price=float(long_price),
            short_price=float(short_price),
            divs=divs,
            today=today,
            holding_days=int(holding_days),
            underlyings=selected_underlyings,
            include_dividends=include_dividends,
        )

        # Üst metrikler
        r1, r2, r3, r4 = st.columns(4)
        with r1:
            st.metric("Spread TL", f"{result['Spread TL']:.2f}")
        with r2:
            st.metric("Spread %", f"{result['Spread %']:.2f}%")
        with r3:
            st.metric("Yıllıklandırılmış", f"{result['Yıllıklandırılmış %']:.2f}%")
        with r4:
            st.metric("Klasik arbitraj mı?", result["Klasik Spot-VİOP Arbitraj mı?"])

        if result["Klasik Spot-VİOP Arbitraj mı?"] == "Hayır":
            st.warning(
                "Bu eşleşme aynı dayanaklı Spot/VİOP arbitrajı değil. "
                "Sonucu relative-value / spread göstergesi olarak oku."
            )
        else:
            st.success(
                "Bu eşleşme aynı dayanaklı Spot/VİOP yapısıdır. "
                "Temettü ve komisyon varsayımlarıyla yıllıklandırılmış taşıma/spread hesaplanmıştır."
            )

        # Detay tablo
        detail_df = pd.DataFrame([result])
        st.subheader("Pair Detayı")
        display_df(detail_df, height=120)

        # Bacak fiyat tablosu
        leg_df = pd.DataFrame(
            [
                {
                    "Bacak": "Long / Al",
                    "Tip": long_type,
                    "Sembol": long_clean,
                    "Dayanak": long_underlying or "-",
                    "Fiyat": float(long_price),
                    "Vade": long_expiry.strftime("%d.%m.%Y") if long_expiry else "-",
                    "Komisyon Varsayımı": effective_commission(long_type),
                },
                {
                    "Bacak": "Short / Sat",
                    "Tip": short_type,
                    "Sembol": short_clean,
                    "Dayanak": short_underlying or "-",
                    "Fiyat": float(short_price),
                    "Vade": short_expiry.strftime("%d.%m.%Y") if short_expiry else "-",
                    "Komisyon Varsayımı": effective_commission(short_type),
                },
            ]
        )
        st.subheader("Bacaklar")
        display_df(leg_df, height=120)

        # Basit waterfall benzeri grafik
        spread_fig = go.Figure()
        spread_fig.add_trace(
            go.Bar(
                x=["Long maliyet", "Short tahsilat", "Temettü etkisi", "Net spread"],
                y=[
                    -float(long_price) * (1 + effective_commission(long_type)),
                    float(short_price) * (1 - effective_commission(short_type)),
                    result["Dividend Adj."],
                    result["Spread TL"],
                ],
                marker_color=["#b91c1c", "#047857", "#2563eb", "#374151"],
                text=[
                    f"-{float(long_price) * (1 + effective_commission(long_type)):.2f}",
                    f"{float(short_price) * (1 - effective_commission(short_type)):.2f}",
                    f"{result['Dividend Adj.']:.2f}",
                    f"{result['Spread TL']:.2f}",
                ],
                textposition="outside",
            )
        )
        spread_fig.update_layout(
            title="Pair Spread Bileşenleri",
            paper_bgcolor="white",
            plot_bgcolor="white",
            height=360,
            margin=dict(l=30, r=30, t=60, b=40),
            yaxis=dict(showgrid=True, gridcolor="#e5e7eb", zeroline=True, zerolinecolor="#9ca3af"),
            font=dict(color="#111827"),
            xaxis=dict(tickfont=dict(color="#374151")),
        )
        st.plotly_chart(spread_fig, use_container_width=True)

# -----------------------------------------------------------------------------
# Alt bilgi
# -----------------------------------------------------------------------------
st.caption(
    f"Varsayımlar: Spot komisyon = {SPOT_COMMISSION_RATE:.4%}, "
    f"VİOP komisyon = {VIOP_COMMISSION_RATE:.4%}. "
    "Veri kaynağı public web verisi olduğu için gecikme/eksik kontrat riski olabilir. "
    "Üretim kullanımında kurum içi lisanslı veri servisi tercih edilmelidir."
)
