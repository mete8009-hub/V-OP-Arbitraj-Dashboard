
"""
Veri bağlantı test sayfası — v2
Terminal kullanmadan spot, VİOP ve özellikle temettü parse sorununu teşhis eder.
"""

from datetime import datetime
import inspect
import re

import pandas as pd
import pytz
import streamlit as st

from src.data_fetcher import DataFetcher, DividendFetcher


st.set_page_config(page_title="Veriyi Test Et", page_icon="🔎", layout="wide")

st.title("🔎 Veri Bağlantı Testi")
st.caption("Terminal kullanmadan spot, VİOP ve temettü veri kaynaklarını test eder.")

symbol = st.text_input("Test sembolü", value="AKBNK").strip().upper() or "AKBNK"

if st.button("Cache temizle / testi yeniden başlat"):
    st.cache_data.clear()
    st.rerun()

st.write("Test zamanı:", datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%Y-%m-%d %H:%M:%S"))

fetcher = DataFetcher()
div_fetcher = DividendFetcher()

st.header("1) Proje fonksiyonları testi")

c1, c2, c3 = st.columns(3)

with c1:
    try:
        spots = fetcher.fetch_all_spot_prices()
        st.metric("Spot adet", len(spots))
        st.write({k: spots.get(k) for k in [symbol, "AKBNK", "THYAO", "PGSUS"] if spots.get(k) is not None})
    except Exception as e:
        st.error(f"Spot hata: {e}")

with c2:
    try:
        viops = fetcher.fetch_viop_for_symbol(symbol)
        st.metric(f"{symbol} VİOP adet", len(viops))
        st.write(dict(list(viops.items())[:10]))
    except Exception as e:
        st.error(f"VİOP hata: {e}")

with c3:
    try:
        divs = div_fetcher.fetch_dividends(symbol)
        st.metric(f"{symbol} temettü adet", len(divs))
        st.write(divs[:10])
    except Exception as e:
        st.error(f"Temettü hata: {e}")

st.header("2) Temettü parser teşhis")

st.write("DividendFetcher class:", str(DividendFetcher))
st.write("DividendFetcher dosyası:", inspect.getfile(DividendFetcher))

version = getattr(__import__("src.data_fetcher", fromlist=["DIVIDEND_FETCHER_VERSION"]), "DIVIDEND_FETCHER_VERSION", "VERSION_YOK")
st.write("DividendFetcher version:", version)

if hasattr(div_fetcher, "debug_fetch_dividend_html"):
    dbg = div_fetcher.debug_fetch_dividend_html(symbol)
    st.subheader("debug_fetch_dividend_html sonucu")
    st.json({k: v for k, v in dbg.items() if k not in ["sample", "parsed_rows"]})
    st.write("Parsed rows:")
    st.write(dbg.get("parsed_rows", [])[:10])
    st.text_area("Ham sayfa örneği", value=dbg.get("sample", ""), height=250)
else:
    st.warning("debug_fetch_dividend_html bulunamadı. Bu, data_fetcher.py dosyasının güncel final v3 olmadığını gösterir.")

st.header("3) Yorum")
st.info(
    "AKBNK temettü adet 0 ise ve version VERSION_YOK görünüyorsa, src/data_fetcher.py yanlış dosya veya eski sürümdür. "
    "Version DIVIDEND_FINAL_2026_04_30_V3 görünüp adet yine 0 ise, ham sayfa örneğinde Temettü Gerçekleşen/Planlanan bölümü gelip gelmediğine bak."
)
