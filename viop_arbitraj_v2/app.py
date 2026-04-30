"""
VİOP Arbitraj Dashboard
=======================
İş Yatırım'dan canlı spot + VİOP fiyatları çeker, KAP'tan otomatik temettü çeker,
yıllıklandırılmış arbitraj getirisini bar chart olarak gösterir.

Çalıştırmak için:
    streamlit run app.py
"""
from datetime import datetime, date, timedelta
import logging

import pandas as pd
import plotly.graph_objects as go
import pytz
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from src.config import (
    DASHBOARD_STOCKS,
    ALL_EXPIRIES,
    REFRESH_INTERVAL_SEC,
    DIVIDEND_CACHE_TTL_SEC,
    MONTHS_TR,
    get_viop_code,
    get_active_contract_months,
    days_to_maturity,
)
from src.data_fetcher import DataFetcher, DividendFetcher
from src.arbitrage import calculate_arbitrage, ArbitrageResult

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ============================================================================
# Sayfa kurulumu
# ============================================================================
st.set_page_config(
    page_title="VİOP Arbitraj Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# CSS - Excel görünümü
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; max-width: 100%; }
    [data-testid="stHeader"] { height: 0; }
    [data-testid="stToolbar"] { right: 1rem; }

    .header-strip {
        display: grid;
        gap: 0;
        margin-bottom: 1rem;
        font-family: 'Segoe UI', sans-serif;
        font-size: 11px;
        border: 2px solid #4a7ba6;
    }
    .header-cell {
        padding: 6px 4px;
        border-right: 1px solid #d0d0d0;
        text-align: center;
        line-height: 1.3;
    }
    .header-cell:last-child { border-right: none; }
    .header-blue { background: #4a7ba6; color: white; font-weight: 600; }
    .header-yellow { background: #fff2cc; }
    .header-green { background: #d5e8d4; }
    .header-light { background: #f5f5f5; }

    .panel-title {
        background: #c00000;
        color: white;
        padding: 6px;
        text-align: center;
        font-weight: 700;
        font-size: 13px;
        margin-top: 8px;
    }
    .panel-title-blue {
        background: #4a7ba6;
        color: white;
        padding: 6px;
        text-align: center;
        font-weight: 700;
        font-size: 13px;
        margin-top: 8px;
    }
    .stat-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 11px;
    }
    .stat-table th {
        background: #4a7ba6;
        color: white;
        padding: 4px;
        font-size: 10px;
    }
    .stat-table td {
        border: 1px solid #d0d0d0;
        padding: 4px 6px;
        text-align: center;
    }
    .div-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 11px;
    }
    .div-table th {
        padding: 4px;
        font-size: 10px;
        background: #4a7ba6;
        color: white;
    }
    .div-table td {
        border: 1px solid #d0d0d0;
        padding: 3px 6px;
        text-align: center;
    }
    .avg-box {
        background: #f5f5f5;
        border: 1px solid #d0d0d0;
        padding: 8px 12px;
        margin-top: 6px;
        display: flex;
        justify-content: space-between;
        font-size: 12px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# Auto-refresh — HER 15 SANİYEDE BİR otomatik yenile
# ============================================================================
# Streamlit-autorefresh (meta refresh DEĞİL — Streamlit Cloud uyumlu)
refresh_count = st_autorefresh(
    interval=REFRESH_INTERVAL_SEC * 1000,
    key="viop_arbitraj_autorefresh",
    limit=None,
)


# ============================================================================
# Veri çekme — cache'li
# ============================================================================
@st.cache_data(ttl=REFRESH_INTERVAL_SEC, show_spinner=False)
def cached_fetch_market_data():
    fetcher = DataFetcher()
    spots = fetcher.fetch_all_spot_prices()
    viops = fetcher.fetch_all_viop_prices(DASHBOARD_STOCKS)
    return spots, viops


@st.cache_data(ttl=DIVIDEND_CACHE_TTL_SEC, show_spinner=False)
def cached_fetch_dividends():
    """Temettü verisi 1 saatte bir yenilenir — sürekli sorgulamaya gerek yok."""
    fetcher = DividendFetcher()
    return fetcher.fetch_dividends_bulk(DASHBOARD_STOCKS)


def get_dividend_for_period(div_data: dict, symbol: str, today: date, expiry: date) -> float:
    """Bugün ile vade arasında ex-tarih varsa, brüt tutarı topla."""
    rows = div_data.get(symbol, [])
    total = 0.0
    for r in rows:
        ex = r.get("ex_date")
        amt = r.get("amount", 0.0)
        if ex and today < ex <= expiry:
            total += amt
    return total


def get_dividend_calendar_view(div_data: dict, contract_months: list) -> dict:
    """
    Sağ paneldeki ay-bazlı temettü listesi.
    {(month, year): [symbol1, symbol2, ...]}
    """
    out = {key: [] for key in contract_months}
    today = datetime.now(pytz.timezone("Europe/Istanbul")).date()
    for sym, rows in div_data.items():
        for r in rows:
            ex = r.get("ex_date")
            if not ex or ex < today:
                continue
            key = (ex.month, ex.year)
            if key in out and sym not in out[key]:
                out[key].append(sym)
    return out


# ============================================================================
# Hesaplama
# ============================================================================
def compute_all_arbitrages(spots, viops, divs, today, contract_months):
    results = {}
    for month, year in contract_months:
        expiry = ALL_EXPIRIES.get((month, year))
        if not expiry:
            continue
        period = []
        for sym in DASHBOARD_STOCKS:
            spot = spots.get(sym)
            code = get_viop_code(sym, month, year)
            viop = viops.get(code)
            div_amount = get_dividend_for_period(divs, sym, today, expiry)
            res = calculate_arbitrage(sym, spot, viop, expiry, today, dividend=div_amount)
            period.append(res)
        results[(month, year)] = period
    return results


# ============================================================================
# UI — Header strip
# ============================================================================
def render_header_strip(today, contract_months):
    """Excel'in en üstündeki tarih satırı."""
    t_plus_2 = today + timedelta(days=2)

    # Hücre yapısı
    cells = [
        ("Today", today.strftime("%d.%m.%Y"), "header-blue"),
        ("T+2", t_plus_2.strftime("%d.%m.%Y"), "header-blue"),
    ]
    for month, year in contract_months:
        expiry = ALL_EXPIRIES.get((month, year))
        if not expiry:
            continue
        t2_expiry = expiry + timedelta(days=2)
        dtm = days_to_maturity(today, expiry)
        cells.extend([
            (MONTHS_TR[month - 1], expiry.strftime("%d.%m.%Y"), "header-light"),
            ("T+2 Expiry", t2_expiry.strftime("%d.%m.%Y"), "header-yellow"),
            ("DTM", str(max(dtm, 0)), "header-green"),
        ])

    # Grid template - eşit genişlik
    cols_count = len(cells)
    grid_template = f"repeat({cols_count}, 1fr)"
    html = f'<div class="header-strip" style="grid-template-columns: {grid_template};">'
    for label, value, cls in cells:
        html += (
            f'<div class="header-cell {cls}">'
            f'<div style="font-weight:600">{label}</div>'
            f'<div>{value}</div></div>'
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


# ============================================================================
# UI — Bar chart
# ============================================================================
def render_arbitrage_chart(results, title: str):
    symbols = [r.symbol for r in results]
    returns = [r.annualized_return for r in results]
    text_labels = [
        f"{r.annualized_return:.1f}%" if r.is_active and abs(r.annualized_return) > 0.05 else "0.0%"
        for r in results
    ]

    fig = go.Figure()

    # Çubuk yerine ince line + tepe noktada işaretçi (Excel görünümü)
    for i, (sym, ret, label) in enumerate(zip(symbols, returns, text_labels)):
        fig.add_trace(go.Scatter(
            x=[sym, sym],
            y=[0, ret],
            mode="lines",
            line=dict(color="#c00000", width=2),
            showlegend=False,
            hoverinfo="skip",
        ))

    # Tepe noktada yatay tire (Excel'deki tire benzeri)
    fig.add_trace(go.Scatter(
        x=symbols,
        y=returns,
        mode="markers",
        marker=dict(symbol="line-ew", size=14, color="#c00000",
                    line=dict(width=4, color="#c00000")),
        showlegend=False,
        text=[f"{r.symbol}: {r.annualized_return:.2f}% (DTM:{r.dtm})" for r in results],
        hovertemplate="%{text}<extra></extra>",
    ))

    # Etiketler — bar tepelerinde
    fig.add_trace(go.Scatter(
        x=symbols,
        y=[r + (3 if r >= 0 else -3) for r in returns],
        mode="text",
        text=text_labels,
        textfont=dict(size=10, color="#c00000"),
        textposition="middle center",
        showlegend=False,
        hoverinfo="skip",
    ))

    fig.update_layout(
        title=dict(
            text=f"<b style='color:#c00000;font-size:18px'>{title}</b>",
            x=0.5,
            xanchor="center",
        ),
        xaxis=dict(
            tickangle=-90,
            tickfont=dict(size=10),
            showgrid=True,
            gridcolor="#e8e8e8",
            griddash="dot",
        ),
        yaxis=dict(
            tickformat=".0f",
            ticksuffix="%",
            tickfont=dict(size=10),
            showgrid=True,
            gridcolor="#e8e8e8",
            zeroline=True,
            zerolinecolor="black",
            zerolinewidth=1,
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=380,
        margin=dict(l=40, r=20, t=50, b=80),
    )
    return fig


# ============================================================================
# UI — Sağ panel
# ============================================================================
def render_right_panel(results_by_period, contract_months, div_calendar):
    # Temettü tablosu
    st.markdown('<div class="panel-title">DIVIDENDS</div>', unsafe_allow_html=True)
    div_html = '<table class="div-table"><thead><tr>'
    for m, y in contract_months:
        div_html += f'<th>{MONTHS_TR[m - 1]}</th>'
    div_html += "</tr></thead><tbody>"

    max_rows = max([len(div_calendar.get(k, [])) for k in contract_months] + [3])
    for i in range(max_rows):
        div_html += "<tr>"
        for k in contract_months:
            stocks = div_calendar.get(k, [])
            if not stocks and i == 0:
                div_html += "<td>No DIV</td>"
            elif i < len(stocks):
                div_html += f"<td>{stocks[i]}</td>"
            else:
                div_html += "<td>&nbsp;</td>"
        div_html += "</tr>"
    div_html += "</tbody></table>"
    st.markdown(div_html, unsafe_allow_html=True)

    # Her vade için top 3
    averages = []
    for (month, year), period_results in results_by_period.items():
        active = [r for r in period_results if r.is_active]
        positive = sorted([r for r in active if r.annualized_return > 0],
                          key=lambda x: x.annualized_return, reverse=True)
        top3 = positive[:3]

        st.markdown(
            f'<div class="panel-title-blue">{MONTHS_TR[month - 1]} {year}</div>',
            unsafe_allow_html=True,
        )

        if not top3:
            st.markdown(
                '<div style="text-align:center;font-size:11px;padding:8px;'
                'border:1px solid #d0d0d0;background:#fafafa">'
                'Aktif arbitraj fırsatı yok</div>',
                unsafe_allow_html=True,
            )
        else:
            tbl = '<table class="stat-table"><thead><tr>'
            tbl += '<th>MAX</th><th>INTEREST</th><th>SPREAD</th></tr></thead><tbody>'
            for r in top3:
                tbl += (
                    f'<tr><td><b>{r.symbol}</b></td>'
                    f'<td>{r.annualized_return:.1f}%</td>'
                    f'<td>{r.spread_pct:.2f}%</td></tr>'
                )
            tbl += "</tbody></table>"
            st.markdown(tbl, unsafe_allow_html=True)

        # Ortalama
        if active:
            avg = sum(r.annualized_return for r in active) / len(active)
        else:
            avg = 0.0
        averages.append((MONTHS_TR[month - 1], avg))

    # Ortalamalar bloğu
    for label, avg in averages:
        st.markdown(
            f'<div class="avg-box"><span>{label} Avrg.</span>'
            f'<span style="color:#c00000">{avg:.2f}%</span></div>',
            unsafe_allow_html=True,
        )


# ============================================================================
# ANA UYGULAMA
# ============================================================================
def main():
    tz = pytz.timezone("Europe/Istanbul")
    now_ist = datetime.now(tz)
    today = now_ist.date()
    contract_months = get_active_contract_months(today, count=3)

    # Veri çekimi
    with st.spinner("Canlı veri çekiliyor..."):
        try:
            spots, viops = cached_fetch_market_data()
        except Exception as e:
            st.error(f"Spot/VİOP veri hatası: {e}")
            spots, viops = {}, {}

        try:
            divs = cached_fetch_dividends()
        except Exception as e:
            log.warning(f"Dividend fetch failed: {e}")
            divs = {}

    # Veri kontrolü
    if not spots and not viops:
        st.warning(
            "⚠️ İş Yatırım API'sine şu an erişilemiyor. "
            f"{REFRESH_INTERVAL_SEC} saniye sonra tekrar denenecek."
        )
        st.info(
            "**Not:** Bu, geçici bir ağ sorunu olabilir. "
            "Uzun süre devam ederse, `src/data_fetcher.py` içindeki endpoint'leri "
            "İş Yatırım sitesini F12 ile inceleyerek güncelleyin."
        )
        return

    # Hesapla
    div_calendar = get_dividend_calendar_view(divs, contract_months)
    results_by_period = compute_all_arbitrages(spots, viops, divs, today, contract_months)

    # ---- LAYOUT ----
    render_header_strip(today, contract_months)

    main_col, side_col = st.columns([4, 1.4], gap="medium")

    with main_col:
        # İlk 2 vadenin chart'ı (görseldeki gibi)
        for (month, year), period_results in list(results_by_period.items())[:2]:
            title = f"{MONTHS_TR[month - 1]} Arbitrage Returns"
            fig = render_arbitrage_chart(period_results, title)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with side_col:
        render_right_panel(results_by_period, contract_months, div_calendar)

    # Footer
    st.markdown("---")
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        st.caption(f"🕐 Güncelleme: {now_ist.strftime('%d.%m.%Y %H:%M:%S')}")
    with f2:
        st.caption(f"🔄 Otomatik yenileme: {REFRESH_INTERVAL_SEC}s")
    with f3:
        st.caption(f"📊 {len(spots)} spot / {len(viops)} VİOP")
    with f4:
        total_div_stocks = sum(1 for v in divs.values() if v)
        st.caption(f"💰 {total_div_stocks} hisse temettü")


if __name__ == "__main__":
    main()
