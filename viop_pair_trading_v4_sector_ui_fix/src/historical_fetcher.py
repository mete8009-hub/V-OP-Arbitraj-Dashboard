"""Tarihsel fiyat verisi çekme katmanı.

İlk versiyon yfinance kullanır. BIST hisseleri için semboller otomatik olarak
`.IS` uzantısına çevrilir. Üretim ortamında bu dosyanın içi Foreks/Matriks/
Refinitiv veya kurum içi fiyat veritabanı ile değiştirilebilir.
"""
from __future__ import annotations

from datetime import date
import logging
from typing import Iterable

import pandas as pd

log = logging.getLogger(__name__)


def normalize_bist_symbol(symbol: str) -> str:
    """AKBNK.IS veya AKBNK gibi girdiyi AKBNK formatına normalize eder."""
    s = str(symbol or "").strip().upper()
    if s.endswith(".IS"):
        s = s[:-3]
    return "".join(ch for ch in s if ch.isalnum())


def to_yfinance_ticker(symbol: str) -> str:
    """AKBNK -> AKBNK.IS; AKBNK.IS -> AKBNK.IS."""
    s = str(symbol or "").strip().upper()
    if not s:
        return s
    if s.endswith(".IS"):
        return s
    return f"{normalize_bist_symbol(s)}.IS"


def _extract_close_from_yfinance(raw: pd.DataFrame, yf_tickers: list[str]) -> pd.DataFrame:
    """yf.download çıktısından Close/Adj Close tablosunu güvenli şekilde çıkarır."""
    if raw is None or raw.empty:
        return pd.DataFrame()

    # Çoklu sembol indirmelerinde kolonlar genellikle MultiIndex gelir.
    if isinstance(raw.columns, pd.MultiIndex):
        levels = raw.columns.names
        last_level_values = set(map(str, raw.columns.get_level_values(-1)))
        first_level_values = set(map(str, raw.columns.get_level_values(0)))

        if "Close" in last_level_values:
            close = raw.xs("Close", axis=1, level=-1)
        elif "Adj Close" in last_level_values:
            close = raw.xs("Adj Close", axis=1, level=-1)
        elif "Close" in first_level_values:
            close = raw.xs("Close", axis=1, level=0)
        elif "Adj Close" in first_level_values:
            close = raw.xs("Adj Close", axis=1, level=0)
        else:
            # Son çare: her ticker altında Close aramaya çalış.
            close_cols = [c for c in raw.columns if any(str(x).lower() == "close" for x in c)]
            close = raw[close_cols].copy()
            close.columns = [next((x for x in c if str(x).upper().endswith(".IS")), c[0]) for c in close_cols]
    else:
        # Tek sembol indirmesinde düz kolon gelebilir.
        if "Close" in raw.columns:
            close = raw[["Close"]].copy()
        elif "Adj Close" in raw.columns:
            close = raw[["Adj Close"]].copy()
        else:
            return pd.DataFrame()
        close.columns = [yf_tickers[0]]

    # Kolonları AKBNK formatına geri çevir.
    rename_map = {}
    for c in close.columns:
        clean = normalize_bist_symbol(str(c))
        if clean:
            rename_map[c] = clean
    close = close.rename(columns=rename_map)
    close = close.loc[:, ~close.columns.duplicated()].copy()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close = close.sort_index()
    close = close.apply(pd.to_numeric, errors="coerce")
    close = close.dropna(axis=1, how="all")
    return close


def fetch_yfinance_close(
    symbols: Iterable[str],
    years: int = 3,
    end: date | None = None,
) -> pd.DataFrame:
    """BIST hisseleri için düzeltilmiş kapanış fiyatlarını döndürür.

    Parameters
    ----------
    symbols:
        AKBNK, GARAN gibi BIST sembolleri.
    years:
        Geriye dönük yıl sayısı. 1, 3, 5, 10 gibi.
    end:
        Opsiyonel bitiş tarihi.
    """
    import yfinance as yf

    clean_symbols = sorted({normalize_bist_symbol(s) for s in symbols if normalize_bist_symbol(s)})
    if not clean_symbols:
        return pd.DataFrame()

    yf_tickers = [to_yfinance_ticker(s) for s in clean_symbols]
    end_ts = pd.Timestamp(end or pd.Timestamp.today().date()) + pd.Timedelta(days=1)
    # Ufak tampon: tatil/veri boşluğu için birkaç gün değil, birkaç hafta kazandırır.
    start_ts = end_ts - pd.DateOffset(years=int(years), months=1)

    try:
        raw = yf.download(
            tickers=yf_tickers,
            start=start_ts.strftime("%Y-%m-%d"),
            end=end_ts.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
            group_by="ticker",
            threads=True,
        )
    except Exception as exc:
        log.warning("yfinance download failed: %s", exc)
        return pd.DataFrame()

    close = _extract_close_from_yfinance(raw, yf_tickers)
    keep = [s for s in clean_symbols if s in close.columns]
    return close[keep].dropna(how="all") if keep else pd.DataFrame()
