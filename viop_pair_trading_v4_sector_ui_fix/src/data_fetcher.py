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


DIVIDEND_FETCHER_VERSION = "DIVIDEND_FINAL_2026_04_30_V3"


class DividendFetcher:
    """
    Temettü kayıtlarını İş Yatırım şirket kartından çeker.

    Örn. kaynak satır:
    AKBNK 26.03.2026 3,11 2,2018 220,18 187,15 11.449.360.000 20

    Parsed:
    ex_date = 26.03.2026
    rate    = 3,11
    amount  = 2,2018  # Hisse Başı TL
    """

    COMPANY_CARD_URL = (
        "https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/"
        "sirket-karti.aspx"
    )

    def __init__(self, timeout: int = 20):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.timeout = timeout

    def fetch_dividends(self, symbol: str) -> list:
        from datetime import datetime as dt

        symbol = str(symbol or "").strip().upper()
        if not symbol:
            return []

        try:
            r = self.session.get(
                self.COMPANY_CARD_URL,
                params={"hisse": symbol},
                timeout=self.timeout,
            )
        except Exception as e:
            log.warning("Dividend request failed for %s: %s", symbol, e)
            return []

        if r.status_code != 200:
            log.warning("Dividend HTTP %s for %s", r.status_code, symbol)
            return []

        text = _clean_text(r.text)

        # Bölümü ayırmaya çalış. Ayıramazsa tüm text üzerinden arar.
        low = text.lower()
        marker_positions = [
            low.find("temettü gerçekleşen/planlanan"),
            low.find("temettu gerceklesen/planlanan"),
            low.find("temettü gerçekleşen"),
            low.find("temettu gerceklesen"),
        ]
        valid_positions = [p for p in marker_positions if p >= 0]
        if valid_positions:
            text = text[min(valid_positions):]

        # Türkçe sayı: 3,11 | 2,2018 | 220,18 | 11.449.360.000 | 65,00
        num = r"-?\d+(?:\.\d{3})*(?:,\d+)?|-?\d+(?:,\d+)?"

        # En dayanıklı pattern:
        # SYMBOL DATE RATE AMOUNT ...
        pattern = re.compile(
            rf"\b{re.escape(symbol)}\b\s+"
            rf"(\d{{2}}[./]\d{{2}}[./]\d{{4}})\s+"
            rf"({num})\s+"
            rf"({num})",
            flags=re.IGNORECASE,
        )

        rows = []
        for m in pattern.finditer(text):
            date_str = m.group(1).replace("/", ".")
            rate_raw = m.group(2)
            amount_raw = m.group(3)

            try:
                ex_date = dt.strptime(date_str, "%d.%m.%Y").date()
            except Exception:
                continue

            rate = _parse_tr_number(rate_raw) or 0.0
            amount = _parse_tr_number(amount_raw)

            # Hisse başı temettü için geniş ama mantıklı filtre.
            # 11.449.360.000 gibi toplam temettüleri yakalamamak için üst sınır koyuyoruz.
            if amount is None or amount <= 0 or amount > 10000:
                continue

            rows.append({
                "ex_date": ex_date,
                "amount": float(amount),
                "rate": float(rate),
            })

        # Duplicate temizle: İş Yatırım sayfası bazen aynı tabloyu iki kez basabiliyor.
        unique = {}
        for row in rows:
            key = (row["ex_date"], round(row["amount"], 6))
            unique[key] = row

        return sorted(unique.values(), key=lambda x: x["ex_date"], reverse=True)

    def fetch_dividends_bulk(self, symbols: list) -> dict:
        from concurrent.futures import ThreadPoolExecutor

        clean = []
        for s in symbols or []:
            s = str(s or "").strip().upper()
            if s and s not in clean:
                clean.append(s)

        def _one(sym):
            return sym, self.fetch_dividends(sym)

        out = {}
        # Az paralellik: blok riskini azaltır.
        with ThreadPoolExecutor(max_workers=4) as ex:
            for sym, rows in ex.map(_one, clean):
                out[sym] = rows
        return out

    def debug_fetch_dividend_html(self, symbol: str = "AKBNK") -> dict:
        """
        Sadece teşhis sayfası için. App ana akışı bunu kullanmaz.
        """
        symbol = str(symbol or "").strip().upper()
        try:
            r = self.session.get(
                self.COMPANY_CARD_URL,
                params={"hisse": symbol},
                timeout=self.timeout,
            )
            text = _clean_text(r.text)
            low = text.lower()
            contains_marker = ("temettü gerçekleşen" in low) or ("temettu gerceklesen" in low)
            contains_symbol = symbol.lower() in low
            sample = ""
            idx = low.find("temettü gerçekleşen")
            if idx < 0:
                idx = low.find(symbol.lower())
            if idx >= 0:
                sample = text[max(0, idx - 250): idx + 1200]
            return {
                "version": DIVIDEND_FETCHER_VERSION,
                "status_code": r.status_code,
                "url": r.url,
                "contains_marker": contains_marker,
                "contains_symbol": contains_symbol,
                "parsed_rows": self.fetch_dividends(symbol),
                "sample": sample,
            }
        except Exception as e:
            return {
                "version": DIVIDEND_FETCHER_VERSION,
                "error": str(e),
            }

