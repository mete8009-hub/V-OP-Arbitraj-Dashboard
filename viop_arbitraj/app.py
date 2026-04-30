"""
VİOP Arbitraj Dashboard
=======================
BIST 30 hisseleri için spot vs VİOP arbitraj getirisini canlı gösterir.

Çalıştırmak için:
    streamlit run app.py

Veri kaynağı: İş Yatırım public ajax endpoint'leri
Yenileme: 15 saniyede bir otomatik (Streamlit cache TTL)
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, date, timedelta
import pytz

from src.config import (
    BIST30_STOCKS,
    EXPIRY_DATES_2026,
    REFRESH_INTERVAL_SEC,
    get_viop_code,
    get_active_contract_months,
    days_to_maturity,
)
from src.data_fetcher import DataFetcher
from src.arbitrage import calculate_arbitrage, ArbitrageResult
from src.dividends import get_dividend_for_period, get_dividend_calendar_view

# ----------------------------------------------------------------------------
# Sayfa yapılandırması
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="VİOP Arbitraj Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom CSS - Excel görünümünü taklit et
st.markdown("""
<style>
    .main > div { padding-top: 1rem; }
    .header-cell {
        background-color: #f5f5f5;
        padding: 8px;
        border: 1px solid #d0d0d0;
        text-align: center;
        font-size: 12px;
        font-weight: 600;
    }
    .header-cell-blue { background-color: #4a7ba6; color: white; }
    .header-cell-yellow { background-color: #fff2cc; }
    .header-cell-green { background-color: #d5e8d4; }
    div[data-testid="metric-container"] {
        background-color: #f8f9fa;
        border: 1px solid #e0e0e0;
        padding: 8px;
        border-radius: 4px;
    }
    .dividend-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
    }
    .dividend-table th {
        background-color: #c00000;
        color: white;
        padding: 6px;
        text-align: center;
    }
    .dividend-table td {
        border: 1px solid #d0d0d0;
        padding: 4px 8px;
        text-align: center;
    }
    .stats-table th {
        background-color: #4a7ba6;
        color: white;
    }
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Veri çekme — cache'li (15 saniyede bir yenilenir)
# ----------------------------------------------------------------------------
@st.cache_data(ttl=REFRESH_INTERVAL_SEC, show_spinner=False)
def fetch_market_data():
    """Spot ve VİOP fiyatlarını paralel çek. Cache TTL = 15s."""
    fetcher = DataFetcher()
    spots = fetcher.fetch_all_spot_prices()
    viops = fetcher.fetch_all_viop_prices()
    return spots, viops, datetime.now(pytz.timezone("Europe/Istanbul"))


def compute_all_arbitrages(
    spots: dict, viops: dict, today: date, contract_months: list
) -> dict[str, list[ArbitrageResult]]:
    """
    Tüm hisseler için, tüm aktif vadelerde arbitraj sonuçlarını hesapla.
    Returns: {(month, year): [ArbitrageResult, ...]}
    """
    results = {}
    for month, year in contract_months:
        expiry = EXPIRY_DATES_2026.get(month)
        if not expiry:
            continue
        period_results = []
        for symbol in BIST30_STOCKS:
            spot = spots.get(symbol)
            viop_code = get_viop_code(symbol, month, year)
            viop = viops.get(viop_code)
            div = get_dividend_for_period(symbol, today, expiry)
            res = calculate_arbitrage(symbol, spot, viop, expiry, today, dividend=div)
            period_results.append(res)
        results[(month, year)] = period_results
    return results


# ----------------------------------------------------------------------------
# Üst başlık tablosu (Excel'in en üstündeki tarih satırı)
# ----------------------------------------------------------------------------
def render_header_strip(today: date, contract_months: list):
    """Today, T+2, vade ayları, expiry, DTM gösterimi."""
    t_plus_2 = today + timedelta(days=2)
    cols = st.columns([1, 1, 1.2, 1.2, 0.6, 1.2, 1.2, 0.6, 1.2, 1.2, 0.6])

    headers = ["Today", "T+2"]
    values = [today.strftime("%d.%m.%Y"), t_plus_2.strftime("%d.%m.%Y")]
    months_tr = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
                 "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

    for month, year in contract_months:
        expiry = EXPIRY_DATES_2026.get(month, today)
        t2_expiry = expiry + timedelta(days=2)
        dtm = days_to_maturity(today, expiry)
        headers.extend([months_tr[month - 1], "T+2 Expiry", "DTM"])
        values.extend([
            expiry.strftime("%d.%m.%Y"),
            t2_expiry.strftime("%d.%m.%Y"),
            str(max(dtm, 0)),
        ])

    for i, (h, v) in enumerate(zip(headers, values)):
        with cols[i]:
            css_class = "header-cell"
            if h in ("Today", "T+2"):
                css_class += " header-cell-blue"
            elif "Expiry" in h:
                css_class += " header-cell-yellow"
            elif h == "DTM":
                css_class += " header-cell-green"
            st.markdown(
                f'<div class="{css_class}"><strong>{h}</strong><br/>{v}</div>',
                unsafe_allow_html=True,
            )


# ----------------------------------------------------------------------------
# Bar chart — Excel'deki yatay/dikey bar görünümü
# ----------------------------------------------------------------------------
def render_arbitrage_chart(results: list[ArbitrageResult], title: str):
    """Hisseler için yıllıklandırılmış arbitraj getirisi bar chart."""
    symbols = [r.symbol for r in results]
    returns = [r.annualized_return for r in results]
    colors = [
        "#c00000" if r.is_active and r.annualized_return != 0 else "#cccccc"
        for r in results
    ]
    text_labels = [
        f"{r.annualized_return:.1f}%" if r.is_active else "N/A"
        for r in results
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=symbols,
        y=returns,
        marker_color=colors,
        text=text_labels,
        textposition="outside",
        textangle=-90,
        textfont=dict(size=10, color="#c00000"),
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Yıllık Getiri: %{y:.2f}%<br>"
            "<extra></extra>"
        ),
        width=0.05,  # ince çizgi görünümü Excel'deki gibi
    ))

    # Excel'deki gibi yatay tire ekle (her bar'ın tepesinde)
    fig.add_trace(go.Scatter(
        x=symbols,
        y=returns,
        mode="markers",
        marker=dict(symbol="line-ew", size=20, color="#c00000", line_width=3),
        showlegend=False,
        hoverinfo="skip",
    ))

    fig.update_layout(
        title=dict(
            text=f"<b style='color:#c00000'>{title}</b>",
            x=0.5,
            font=dict(size=16),
        ),
        xaxis=dict(
            tickangle=-90,
            tickfont=dict(size=10),
            showgrid=True,
            gridcolor="#e8e8e8",
            griddash="dot",
        ),
        yaxis=dict(
            tickformat=".0%",
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
        showlegend=False,
    )
    # Y ekseni yüzde olarak göster
    fig.update_yaxes(tickformat=".0f", ticksuffix="%")

    return fig


# ----------------------------------------------------------------------------
# Sağ panel: Temettü takvimi + İstatistikler
# ----------------------------------------------------------------------------
def render_right_panel(results_by_period: dict, contract_months: list):
    """Dashboard'un sağ tarafındaki özet kutular."""
    months_tr = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
                 "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

    # ---- Temettü tablosu ----
    st.markdown("### 💰 Temettü Takvimi")
    div_view = get_dividend_calendar_view()
    div_html = '<table class="dividend-table"><thead><tr>'
    month_labels = []
    for m, y in contract_months:
        month_labels.append(months_tr[m - 1])
    for label in month_labels:
        div_html += f"<th>{label}</th>"
    div_html += "</tr></thead><tbody>"
    max_rows = max([len(div_view.get(m, [])) for m in month_labels] + [1])
    for i in range(max_rows):
        div_html += "<tr>"
        for label in month_labels:
            stocks = div_view.get(label, [])
            cell = stocks[i] if i < len(stocks) else ("No DIV" if i == 0 and not stocks else "")
            div_html += f"<td>{cell}</td>"
        div_html += "</tr>"
    div_html += "</tbody></table>"
    st.markdown(div_html, unsafe_allow_html=True)

    st.markdown("---")

    # ---- En yüksek getiri tabloları (her vade için top 3) ----
    for (month, year), period_results in results_by_period.items():
        active = [r for r in period_results if r.is_active and r.annualized_return > 0]
        active.sort(key=lambda x: x.annualized_return, reverse=True)
        top3 = active[:3]

        st.markdown(f"#### {months_tr[month - 1]} {year}")
        if not top3:
            st.markdown("_Aktif arbitraj fırsatı yok_")
            continue

        df = pd.DataFrame([{
            "MAX": r.symbol,
            "INTEREST": f"{r.annualized_return:.1f}%",
            "SPREAD": f"{r.spread_pct:.2f}%",
        } for r in top3])
        st.dataframe(df, hide_index=True, use_container_width=True)

    st.markdown("---")

    # ---- Ortalama getiriler ----
    for (month, year), period_results in results_by_period.items():
        active_returns = [r.annualized_return for r in period_results if r.is_active]
        avg = sum(active_returns) / len(active_returns) if active_returns else 0.0
        st.metric(
            label=f"{months_tr[month - 1]} Ortalama",
            value=f"{avg:.2f}%",
        )


# ----------------------------------------------------------------------------
# ANA UYGULAMA
# ----------------------------------------------------------------------------
def main():
    # Otomatik yenileme
    st_autorefresh = st.empty()
   from streamlit_autorefresh import st_autorefresh
   st_autorefresh(interval=REFRESH_INTERVAL_SEC * 1000, key="data_refresh")

    # Bugünün tarihi (İstanbul TZ)
    tz = pytz.timezone("Europe/Istanbul")
    now_ist = datetime.now(tz)
    today = now_ist.date()
    contract_months = get_active_contract_months(today)

    # Veri çek
    with st.spinner("Veri çekiliyor..."):
        spots, viops, last_update = fetch_market_data()

    # Veri durumu kontrolü
    if not spots and not viops:
        st.error(
            "⚠️ Veri kaynaklarına erişilemiyor. "
            "İş Yatırım API'si geçici olarak yanıt vermiyor olabilir. "
            "15 saniye sonra tekrar denenecek."
        )
        st.info(
            "**Olası çözümler:**\n"
            "- İnternet bağlantınızı kontrol edin\n"
            "- Birkaç dakika bekleyip tekrar deneyin\n"
            "- src/data_fetcher.py içindeki endpoint'leri güncelleyin"
        )
        return

    # Hesapla
    results_by_period = compute_all_arbitrages(spots, viops, today, contract_months)

    # Üst başlık şeridi
    render_header_strip(today, contract_months)
    st.markdown("---")

    # Ana içerik: solda chart'lar, sağda özet
    main_col, side_col = st.columns([4, 1.2])

    with main_col:
        months_tr = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
                     "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        # İlk iki vade için bar chart
        for (month, year), period_results in list(results_by_period.items())[:2]:
            title = f"{months_tr[month - 1]} {year} Arbitrage Returns"
            fig = render_arbitrage_chart(period_results, title)
            st.plotly_chart(fig, use_container_width=True)

    with side_col:
        render_right_panel(results_by_period, contract_months)

    # Footer
    st.markdown("---")
    cols = st.columns(3)
    with cols[0]:
        st.caption(f"🕐 Son güncelleme: {last_update.strftime('%H:%M:%S')}")
    with cols[1]:
        st.caption(f"🔄 Otomatik yenileme: {REFRESH_INTERVAL_SEC}sn")
    with cols[2]:
        st.caption(f"📊 {len(spots)} spot · {len(viops)} VİOP fiyatı")


if __name__ == "__main__":
    main()
