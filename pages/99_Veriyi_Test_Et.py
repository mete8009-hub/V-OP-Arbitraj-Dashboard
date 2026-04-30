"""
Streamlit diagnostic page for VİOP Arbitraj Dashboard.
Upload this file to: pages/99_Veriyi_Test_Et.py
Then open the Streamlit app and select 'Veriyi Test Et' from the sidebar.
"""
import json
import traceback
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

from src.data_fetcher import DataFetcher, DividendFetcher, DEFAULT_HEADERS
from src.config import DASHBOARD_STOCKS

st.set_page_config(page_title="Veri Testi", page_icon="🔎", layout="wide")
st.title("🔎 Veri Bağlantı Testi")
st.caption("Terminal kullanmadan spot, VİOP ve temettü veri kaynaklarını test eder.")

TEST_SYMBOL = st.selectbox("Test sembolü", ["AKBNK", "THYAO", "GARAN", "ISCTR", "YKBNK", "ASELS", "TUPRS"])

SPOT_ENDPOINTS = [
    (
        "SPOT XU100 / IndexHisseSenedi endeks=01",
        "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/IndexHisseSenedi",
        {"endeks": "01"},
    ),
    (
        "SPOT XU030 / IndexHisseSenedi endeks=08",
        "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/IndexHisseSenedi",
        {"endeks": "08"},
    ),
]

VIOP_ENDPOINT = (
    "VİOP / ViopHisse",
    "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/ViopHisse",
    {"hisse": TEST_SYMBOL},
)

DIVIDEND_ENDPOINT = (
    "Temettü / sermaye-artirimlari-ve-temettuler",
    "https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/sermaye-artirimlari-ve-temettuler.aspx",
    {"hisse": TEST_SYMBOL},
)


def raw_get(name, url, params):
    row = {"name": name, "url": url, "params": params}
    try:
        r = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=15)
        row["status_code"] = r.status_code
        row["content_type"] = r.headers.get("content-type", "")
        row["final_url"] = r.url
        row["text_head"] = r.text[:1000]
        try:
            js = r.json()
            row["json_type"] = type(js).__name__
            if isinstance(js, dict):
                row["json_keys"] = list(js.keys())[:20]
                val = js.get("value")
                row["value_type"] = type(val).__name__
                row["value_len"] = len(val) if hasattr(val, "__len__") else None
                row["value_sample"] = val[:3] if isinstance(val, list) else val
            elif isinstance(js, list):
                row["value_len"] = len(js)
                row["value_sample"] = js[:3]
        except Exception as e:
            row["json_error"] = str(e)
    except Exception as e:
        row["error"] = str(e)
        row["traceback"] = traceback.format_exc()
    return row


if st.button("Testi Çalıştır", type="primary"):
    st.write(f"Test zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    st.subheader("1) Ham endpoint testi")
    raw_rows = []
    for endpoint in SPOT_ENDPOINTS + [VIOP_ENDPOINT, DIVIDEND_ENDPOINT]:
        raw_rows.append(raw_get(*endpoint))

    summary = pd.DataFrame([
        {
            "name": r.get("name"),
            "status_code": r.get("status_code"),
            "content_type": r.get("content_type"),
            "value_len": r.get("value_len"),
            "json_error": r.get("json_error"),
            "error": r.get("error"),
        }
        for r in raw_rows
    ])
    st.dataframe(summary, use_container_width=True)

    with st.expander("Ham yanıt detayları"):
        for r in raw_rows:
            st.markdown(f"### {r.get('name')}")
            st.write("URL:", r.get("final_url", r.get("url")))
            st.write("Status:", r.get("status_code"), "Content-Type:", r.get("content_type"))
            if "value_sample" in r:
                st.write("JSON sample:")
                st.json(r["value_sample"])
            st.write("Text head:")
            st.code(r.get("text_head", ""), language="text")

    st.subheader("2) Proje fonksiyonları testi")
    fetcher = DataFetcher()
    div_fetcher = DividendFetcher()

    col1, col2, col3 = st.columns(3)
    with col1:
        try:
            spots = fetcher.fetch_all_spot_prices()
            st.metric("Spot adet", len(spots))
            sample = {s: spots.get(s) for s in ["AKBNK", "GARAN", "THYAO", TEST_SYMBOL] if spots.get(s) is not None}
            st.json(sample)
        except Exception as e:
            st.error(f"Spot hata: {e}")
            st.code(traceback.format_exc(), language="text")
    with col2:
        try:
            viops = fetcher.fetch_viop_for_symbol(TEST_SYMBOL)
            st.metric(f"{TEST_SYMBOL} VİOP adet", len(viops))
            st.json(dict(list(viops.items())[:10]))
        except Exception as e:
            st.error(f"VİOP hata: {e}")
            st.code(traceback.format_exc(), language="text")
    with col3:
        try:
            divs = div_fetcher.fetch_dividends(TEST_SYMBOL)
            st.metric(f"{TEST_SYMBOL} temettü adet", len(divs))
            st.write(divs[:5])
        except Exception as e:
            st.error(f"Temettü hata: {e}")
            st.code(traceback.format_exc(), language="text")

    st.subheader("3) Sonuç yorumu")
    st.markdown(
        """
        - Spot adet 0 ise: spot endpoint veya erişim engeli sorunu var.
        - Spot dolu, VİOP 0 ise: VİOP endpoint/kod formatı sorunu var.
        - Status 403/406/429 ise: veri kaynağı Streamlit Cloud IP'sini veya header'ı reddediyor olabilir.
        - Status 200 ama JSON sample boşsa: endpoint doğru ama parametre veya response alan adları değişmiş olabilir.
        """
    )
