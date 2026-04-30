"""
Veri çekme katmanı — İş Yatırım HTML sayfalarından spot ve VİOP fiyatları.

Bu versiyon eski JSON/Ajax endpoint'lerine bağlı değildir.
İş Yatırım'ın görünen sayfalarında zaten tablo olarak yayınlanan veriyi okur:
- Spot: https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/default.aspx
- VİOP: https://www.isyatirim.com.tr/tr-tr/analiz/Sayfalar/viop.aspx

Not: Bu veriler İş Yatırım sitesindeki uyarıya göre genel bilgilendirme amaçlıdır ve BIST/Matriks kaynaklı gecikmeli olabilir.
"""
from __future__ import annotations

import html as ihtml
import logging
import re
from io import StringIO
from typing import Optional

import pandas as pd
import requests

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Referer": "https://www.isyatirim.com.tr/",
}

SPOT_PAGE_URL = "https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/default.aspx"
VIOP_PAGE_URL = "https://www.isyatirim.com.tr/tr-tr/analiz/Sayfalar/viop.aspx"

MONTH_MAP = {
    "ocak": 1,
    "subat": 2, "şubat": 2,
    "mart": 3,
    "nisan": 4,
    "mayis": 5, "mayıs": 5,
    "haziran": 6,
    "temmuz": 7,
    "agustos": 8, "ağustos": 8,
    "eylul": 9, "eylül": 9,
    "ekim": 10,
    "kasim": 11, "kasım": 11,
    "aralik": 12, "aralık": 12,
}


def _parse_tr_number(value) -> Optional[float]:
    """Türkçe sayı formatını float'a çevirir: '1.234,56' -> 1234.56."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not pd.isna(value):
        return float(value)
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "-"}:
        return None
    s = re.sub(r"[^0-9,\.\-]", "", s)
    if not s:
        return None
    # Türkçe format: binlik nokta, ondalık virgül
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _clean_text(html: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = ihtml.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text


def _viop_code_from_contract_name(contract_name: str) -> Optional[str]:
    """
    'AKBNK Mayis 2026 Vadeli' -> 'F_AKBNK0526'
    'XU030 Yakin Vade (Gunduz) / F_XU0300426' -> 'F_XU0300426'
    """
    if not contract_name:
        return None
    txt = str(contract_name).strip()

    direct = re.search(r"\b(F_[A-Z0-9]+\d{4})\b", txt, flags=re.I)
    if direct:
        return direct.group(1).upper()

    m = re.search(
        r"\b([A-Z][A-Z0-9]{2,6})\s+"
        r"(Ocak|Subat|Şubat|Mart|Nisan|Mayis|Mayıs|Haziran|Temmuz|Agustos|Ağustos|Eylul|Eylül|Ekim|Kasim|Kasım|Aralik|Aralık)\s+"
        r"(20\d{2})\s+Vadeli",
        txt,
        flags=re.I,
    )
    if not m:
        return None
    symbol, month_name, year = m.groups()
    month = MONTH_MAP.get(month_name.lower())
    if not month:
        return None
    return f"F_{symbol.upper()}{month:02d}{str(year)[-2:]}"


class DataFetcher:
    """İş Yatırım'ın görünen HTML tablolarından spot ve VİOP fiyatlarını çeker."""

    def __init__(self, timeout: int = 20):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.timeout = timeout

    def _get_html(self, url: str) -> str:
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        return r.text

    # ------------------------------------------------------------------
    # SPOT — Hisse Senetleri sayfasındaki görünür tablo
    # ------------------------------------------------------------------
    def fetch_all_spot_prices(self) -> dict:
        """Returns: {'AKBNK': 73.10, 'GARAN': 132.0, ...}"""
        prices: dict[str, float] = {}
        try:
            html = self._get_html(SPOT_PAGE_URL)
        except Exception as e:
            log.warning(f"Spot page fetch error: {e}")
            return prices

        # 1) Önce HTML tablolarını pandas ile dene.
        try:
            tables = pd.read_html(StringIO(html), decimal=",", thousands=".")
            for df in tables:
                cols = [str(c).strip() for c in df.columns]
                low_cols = [c.lower() for c in cols]
                if not any("hisse" in c for c in low_cols):
                    continue
                price_col = None
                sym_col = None
                for c in cols:
                    cl = c.lower()
                    if "hisse" in cl:
                        sym_col = c
                    if "son" in cl and "fiyat" in cl:
                        price_col = c
                if sym_col is None or price_col is None:
                    continue
                for _, row in df.iterrows():
                    sym_raw = str(row.get(sym_col, "")).strip().upper()
                    m = re.search(r"\b([A-Z][A-Z0-9]{2,5})\b", sym_raw)
                    price = _parse_tr_number(row.get(price_col))
                    if m and price and price > 0:
                        prices[m.group(1)] = price
            if prices:
                return prices
        except Exception as e:
            log.info(f"pandas read_html spot fallback'a geçiyor: {e}")

        # 2) Fallback: sayfanın düz metninden tablo satırlarını yakala.
        text = _clean_text(html)
        pattern = re.compile(
            r"\b([A-Z][A-Z0-9]{2,5})\b\s+"
            r"(\d{1,3}(?:\.\d{3})*,\d{2})\s+"
            r"[-+]?\d{1,3},\d{2}\s+"
            r"[-+]?\d{1,3},\d{2}\s+"
            r"\d",
            flags=re.I,
        )
        for sym, price_s in pattern.findall(text):
            price = _parse_tr_number(price_s)
            if price and price > 0:
                prices[sym.upper()] = price
        return prices

    # ------------------------------------------------------------------
    # VİOP — VİOP sayfasındaki görünür Pay Vadeli İşlem Ana Pazarı tablosu
    # ------------------------------------------------------------------
    def fetch_all_viop_prices(self, symbols: list | None = None) -> dict:
        """Returns: {'F_AKBNK0426': 73.04, 'F_AKBNK0526': 75.05, ...}"""
        target_symbols = {s.upper() for s in symbols} if symbols else None
        viops: dict[str, float] = {}
        try:
            html = self._get_html(VIOP_PAGE_URL)
        except Exception as e:
            log.warning(f"VİOP page fetch error: {e}")
            return viops

        # 1) Önce pandas tabloları.
        try:
            tables = pd.read_html(StringIO(html), decimal=",", thousands=".")
            for df in tables:
                cols = [str(c).strip() for c in df.columns]
                low_cols = [c.lower() for c in cols]
                if not any("kontrat" in c for c in low_cols):
                    continue
                contract_col = next((c for c in cols if "kontrat" in c.lower()), None)
                price_col = next((c for c in cols if "son" in c.lower() and "fiyat" in c.lower()), None)
                if not contract_col or not price_col:
                    continue
                for _, row in df.iterrows():
                    contract = str(row.get(contract_col, "")).strip()
                    code = _viop_code_from_contract_name(contract)
                    price = _parse_tr_number(row.get(price_col))
                    if not code or not price or price <= 0:
                        continue
                    # Sadece pay vadeli kontratlar: F_AKBNK0526 gibi.
                    m = re.match(r"F_([A-Z][A-Z0-9]{2,6})\d{4}$", code)
                    if not m:
                        continue
                    if target_symbols and m.group(1).upper() not in target_symbols:
                        continue
                    viops[code] = price
            if viops:
                return viops
        except Exception as e:
            log.info(f"pandas read_html VİOP fallback'a geçiyor: {e}")

        # 2) Fallback: düz metinden yakala.
        text = _clean_text(html)
        month_names = "Ocak|Subat|Şubat|Mart|Nisan|Mayis|Mayıs|Haziran|Temmuz|Agustos|Ağustos|Eylul|Eylül|Ekim|Kasim|Kasım|Aralik|Aralık"
        pattern = re.compile(
            rf"\b([A-Z][A-Z0-9]{{2,6}})\s+({month_names})\s+(20\d{{2}})\s+Vadeli\s+"
            r"(\d{1,3}(?:\.\d{3})*,\d{2,4})\s+",
            flags=re.I,
        )
        for sym, month_name, year, price_s in pattern.findall(text):
            sym = sym.upper()
            if target_symbols and sym not in target_symbols:
                continue
            month = MONTH_MAP.get(month_name.lower())
            price = _parse_tr_number(price_s)
            if month and price and price > 0:
                code = f"F_{sym}{month:02d}{str(year)[-2:]}"
                viops[code] = price
        return viops

    def fetch_viop_for_symbol(self, symbol: str) -> dict:
        symbol = symbol.upper()
        return {k: v for k, v in self.fetch_all_viop_prices([symbol]).items() if k.startswith(f"F_{symbol}")}

    def fetch_single_spot(self, symbol: str) -> Optional[float]:
        return self.fetch_all_spot_prices().get(symbol.upper())


class DividendFetcher:
    """
    İş Yatırım'ın sermaye artırımı / temettü sayfasından temettü çeker.
    Mevcut dashboard için temettü yoksa 0 kabul edilir; spot + VİOP akışını bloklamaz.
    """

    def __init__(self, timeout: int = 20):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.timeout = timeout

    def fetch_dividends(self, symbol: str) -> list:
        url = (
            "https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/"
            "sermaye-artirimlari-ve-temettuler.aspx"
        )
        try:
            r = self.session.get(url, params={"hisse": symbol}, timeout=self.timeout)
            if r.status_code != 200:
                return []
            html = r.text
        except Exception as e:
            log.warning(f"Dividend fetch {symbol}: {e}")
            return []
        return self._parse_dividend_table(html)

    def fetch_dividends_bulk(self, symbols: list) -> dict:
        from concurrent.futures import ThreadPoolExecutor

        def _one(sym: str):
            return sym, self.fetch_dividends(sym)

        out = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            for sym, rows in ex.map(_one, symbols):
                out[sym] = rows
        return out

    @staticmethod
    def _parse_dividend_table(html: str) -> list:
        from datetime import datetime as dt

        results = []
        # Bütün tabloları dene; tarih ve sayısal tutar içeren satırları çek.
        try:
            tables = pd.read_html(StringIO(html), decimal=",", thousands=".")
            for df in tables:
                for _, row in df.iterrows():
                    date_obj = None
                    amount = None
                    for val in row.values:
                        s = str(val)
                        if date_obj is None:
                            dm = re.search(r"(\d{2})[./](\d{2})[./](\d{4})", s)
                            if dm:
                                try:
                                    d, m, y = map(int, dm.groups())
                                    date_obj = dt(y, m, d).date()
                                except ValueError:
                                    pass
                        if amount is None:
                            num = _parse_tr_number(s)
                            # Temettü tutarı genelde çok büyük olmayan pozitif bir sayıdır.
                            if num and 0 < num < 1000:
                                amount = num
                    if date_obj and amount:
                        results.append({"ex_date": date_obj, "amount": amount, "rate": 0.0})
        except Exception:
            pass

        if results:
            # Aynı kayıtlar tekrar gelirse sadeleştir.
            uniq = {}
            for r in results:
                uniq[(r["ex_date"], r["amount"])] = r
            return sorted(uniq.values(), key=lambda x: x["ex_date"])

        # Regex fallback
        text = _clean_text(html)
        for dm in re.finditer(r"(\d{2})[./](\d{2})[./](\d{4}).{0,80}?(\d{1,3}(?:\.\d{3})*,\d{2,6})", text):
            try:
                d, m, y = map(int, dm.group(1, 2, 3))
                amount = _parse_tr_number(dm.group(4))
                if amount and 0 < amount < 1000:
                    results.append({"ex_date": dt(y, m, d).date(), "amount": amount, "rate": 0.0})
            except Exception:
                continue
        return sorted(results, key=lambda x: x["ex_date"])
