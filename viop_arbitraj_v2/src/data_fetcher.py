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
    İş Yatırım şirket kartındaki "Temettü Gerçekleşen/Planlanan" bölümünü
    basit ve dayanıklı regex ile parse eder.

    Ana kaynak:
      https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/sirket-karti.aspx?hisse=AKBNK

    Çekilen alan:
      Kod Dağ. Tarihi Temettü Verim Hisse Başı TL ...
      AKBNK 26.03.2026 3,11 2,2018 ...

    amount = Hisse Başı TL
    rate   = Temettü Verim (%)
    """

    COMPANY_CARD_URL = (
        "https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/"
        "sirket-karti.aspx"
    )

    LEGACY_DIVIDEND_URL = (
        "https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/"
        "sermaye-artirimlari-ve-temettuler.aspx"
    )

    def __init__(self, timeout: int = 20):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.timeout = timeout

    def fetch_dividends(self, symbol: str) -> list:
        symbol = str(symbol or "").strip().upper()
        if not symbol:
            return []

        urls = [
            self.COMPANY_CARD_URL,
            self.LEGACY_DIVIDEND_URL,
        ]

        for url in urls:
            try:
                r = self.session.get(url, params={"hisse": symbol}, timeout=self.timeout)
                if r.status_code != 200:
                    log.warning("Dividend HTTP %s for %s from %s", r.status_code, symbol, url)
                    continue

                rows = self._parse_dividends_from_html(r.text, symbol)
                if rows:
                    return rows

            except Exception as e:
                log.warning("Dividend fetch failed for %s from %s: %s", symbol, url, e)

        return []

    def fetch_dividends_bulk(self, symbols: list) -> dict:
        from concurrent.futures import ThreadPoolExecutor

        clean_symbols = []
        for s in symbols or []:
            s = str(s or "").strip().upper()
            if s and s not in clean_symbols:
                clean_symbols.append(s)

        def _one(sym: str):
            return sym, self.fetch_dividends(sym)

        out = {}
        # Fazla paralellik İş Yatırım tarafında blok riskini artırır.
        with ThreadPoolExecutor(max_workers=4) as ex:
            for sym, rows in ex.map(_one, clean_symbols):
                out[sym] = rows
        return out

    @staticmethod
    def _dedupe_sort(rows: list) -> list:
        uniq = {}
        for r in rows:
            ex = r.get("ex_date")
            amount = r.get("amount")
            if not ex or amount is None:
                continue
            try:
                amount = float(amount)
            except Exception:
                continue
            if amount <= 0:
                continue

            key = (ex, round(amount, 6))
            uniq[key] = {
                "ex_date": ex,
                "amount": amount,
                "rate": float(r.get("rate") or 0.0),
            }

        return sorted(uniq.values(), key=lambda x: x["ex_date"])

    @staticmethod
    def _parse_dividends_from_html(html: str, symbol: str) -> list:
        from datetime import datetime as dt

        symbol = str(symbol or "").strip().upper()
        rows = []

        text = _clean_text(html)

        # Sadece ilgili bölüme odaklan. Bulamazsa tüm text üzerinde devam eder.
        lowered = text.lower()
        start_candidates = [
            lowered.find("temettü gerçekleşen/planlanan"),
            lowered.find("temettu gerceklesen/planlanan"),
            lowered.find("temettü gerçekleşen"),
            lowered.find("temettu gerceklesen"),
        ]
        starts = [i for i in start_candidates if i >= 0]
        if starts:
            start = min(starts)
            block = text[start:]
        else:
            block = text

        # İş Yatırım sayfasındaki ana format:
        # AKBNK 26.03.2026 3,11 2,2018 220,18 187,15 11.449.360.000 20
        tr_num = r"(?:-?\d{1,3}(?:\.\d{3})*,\d{1,6}|-?\d+,\d{1,6}|-?\d+\.\d{1,6}|-?\d+)"
        direct_pattern = re.compile(
            rf"\b{re.escape(symbol)}\b\s+"
            rf"(\d{{2}}[./]\d{{2}}[./]\d{{4}})\s+"
            rf"({tr_num})\s+"
            rf"({tr_num})",
            flags=re.I,
        )

        for m in direct_pattern.finditer(block):
            date_s = m.group(1).replace("/", ".")
            rate_s = m.group(2)
            amount_s = m.group(3)

            try:
                ex_date = dt.strptime(date_s, "%d.%m.%Y").date()
            except Exception:
                continue

            rate = _parse_tr_number(rate_s) or 0.0
            amount = _parse_tr_number(amount_s)

            # Hisse başı temettü makul aralıkta olmalı. 0-10.000 TL aralığı yeterince geniş.
            if amount and 0 < amount < 10000:
                rows.append({
                    "ex_date": ex_date,
                    "amount": amount,
                    "rate": rate,
                })

        if rows:
            return DividendFetcher._dedupe_sort(rows)

        # Fallback 1: tablo parse. HTML yapısı değişirse işe yarar.
        try:
            tables = pd.read_html(StringIO(html), decimal=",", thousands=".")
        except Exception:
            tables = []

        for df in tables:
            df = df.copy()
            df.columns = [
                " ".join([str(x) for x in c if str(x) != "nan"]).strip()
                if isinstance(c, tuple) else str(c).strip()
                for c in df.columns
            ]

            cols = list(df.columns)
            low_join = " ".join(c.lower() for c in cols)

            if not any(k in low_join for k in ["temett", "hisse baş", "hisse basi", "dağ", "dag"]):
                continue

            symbol_col = next((c for c in cols if c.lower() in {"kod", "sembol", "hisse"} or "kod" in c.lower()), None)
            date_col = next((c for c in cols if any(k in c.lower() for k in ["tarih", "dağ", "dag"])), None)
            amount_col = next((c for c in cols if "hisse" in c.lower() and ("tl" in c.lower() or "baş" in c.lower() or "basi" in c.lower())), None)
            rate_col = next((c for c in cols if "verim" in c.lower()), None)

            if not date_col or not amount_col:
                continue

            for _, row in df.iterrows():
                if symbol_col:
                    raw_symbol = str(row.get(symbol_col, "")).strip().upper()
                    if symbol not in raw_symbol:
                        continue

                date_raw = str(row.get(date_col, ""))
                dm = re.search(r"(\d{2})[./](\d{2})[./](\d{4})", date_raw)
                if not dm:
                    continue

                try:
                    d, m, y = map(int, dm.groups())
                    ex_date = dt(y, m, d).date()
                except Exception:
                    continue

                amount = _parse_tr_number(row.get(amount_col))
                rate = _parse_tr_number(row.get(rate_col)) if rate_col else 0.0

                if amount and 0 < amount < 10000:
                    rows.append({
                        "ex_date": ex_date,
                        "amount": amount,
                        "rate": rate or 0.0,
                    })

        if rows:
            return DividendFetcher._dedupe_sort(rows)

        # Fallback 2: satır satır tarama.
        for line in re.split(r"(?=\b[A-Z]{3,6}\b\s+\d{2}[./]\d{2}[./]\d{4})", block):
            if not re.search(rf"\b{re.escape(symbol)}\b", line):
                continue
            m = direct_pattern.search(line)
            if not m:
                continue

            try:
                ex_date = dt.strptime(m.group(1).replace("/", "."), "%d.%m.%Y").date()
            except Exception:
                continue

            amount = _parse_tr_number(m.group(3))
            rate = _parse_tr_number(m.group(2)) or 0.0

            if amount and 0 < amount < 10000:
                rows.append({
                    "ex_date": ex_date,
                    "amount": amount,
                    "rate": rate,
                })

        return DividendFetcher._dedupe_sort(rows)

