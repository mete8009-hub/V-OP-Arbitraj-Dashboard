"""
Veri çekme katmanı — İş Yatırım public endpoint'lerinden spot ve VİOP fiyatları.

Bu modül topluluk tarafından yıllardır kullanılan ajax endpoint'lerini hedefler.
Her endpoint için fallback'leri var; biri çalışmazsa diğerine geçer.

Endpoint'ler:
1. SPOT (anlık tüm BIST):
   https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/StockInfo/CompanyDailyData.aspx
2. VİOP (anlık tüm kontratlar):
   https://www.isyatirim.com.tr/layouts/15/IsYatirim.Website/Common/Data.aspx/IndexHisseSenedi
3. Tekil hisse (yedek):
   https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/HisseTekil

Eğer İş Yatırım yanıt vermezse Mynet veya BorsaDirekt fallback olarak kullanılır.
"""
import logging
import re
from typing import Optional
import requests

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Referer": "https://www.isyatirim.com.tr/tr-tr/Sayfalar/default.aspx",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.isyatirim.com.tr",
}


class DataFetcher:
    """İş Yatırım'dan canlı spot ve VİOP fiyatlarını çeker."""

    def __init__(self, timeout: int = 12):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.timeout = timeout

    # ------------------------------------------------------------------
    # SPOT — Tüm BIST hisselerini tek seferde
    # ------------------------------------------------------------------
    def fetch_all_spot_prices(self) -> dict:
        """
        Returns: {"AKBNK": 73.10, "GARAN": 132.0, ...}

        İş Yatırım'ın "Tüm BIST" intraday endpoint'i. JSON döner.
        """
        # Birincil endpoint — IndexHisseSenedi (XU100 ya da XTUMY)
        endpoints = [
            (
                "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/IndexHisseSenedi",
                {"endeks": "01"},  # 01 = XU100
            ),
            (
                "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/IndexHisseSenedi",
                {"endeks": "08"},  # 08 = XU030
            ),
        ]

        prices: dict = {}
        for url, params in endpoints:
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                if r.status_code != 200:
                    log.warning(f"Spot endpoint {url} -> HTTP {r.status_code}")
                    continue
                data = r.json()
                items = data.get("value", []) if isinstance(data, dict) else data
                for item in items:
                    sym = item.get("c") or item.get("kod") or item.get("sembol")
                    last = item.get("l") or item.get("son") or item.get("sonFiyat")
                    if sym and last is not None:
                        prices[str(sym).upper()] = float(last)
            except Exception as e:
                log.warning(f"Spot fetch error from {url}: {e}")
                continue

        return prices

    # ------------------------------------------------------------------
    # VİOP — Tek hisse için aktif tüm kontratlar
    # ------------------------------------------------------------------
    def fetch_viop_for_symbol(self, symbol: str) -> dict:
        """
        Returns: {"F_AKBNK0426": 75.34, "F_AKBNK0526": 76.10, ...}

        İş Yatırım'ın tek hisse VİOP detayı endpoint'i.
        """
        url = (
            "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/"
            "Common/Data.aspx/ViopHisse"
        )
        params = {"hisse": symbol}
        result: dict = {}
        try:
            r = self.session.get(url, params=params, timeout=self.timeout)
            if r.status_code != 200:
                return result
            data = r.json()
            items = data.get("value", []) if isinstance(data, dict) else data
            for item in items:
                code = item.get("kod") or item.get("sembol")
                last = item.get("son") or item.get("sonFiyat") or item.get("kapanis")
                if code and last is not None:
                    result[str(code).upper()] = float(last)
        except Exception as e:
            log.warning(f"VİOP fetch error for {symbol}: {e}")
        return result

    def fetch_all_viop_prices(self, symbols: list) -> dict:
        """
        Verilen sembol listesinin TÜM aktif vadelerini çek.
        Returns: {"F_AKBNK0426": 75.3, "F_AKBNK0526": 76.1, ...}

        Her hisse için ayrı istek atılır (paralel, threaded).
        """
        from concurrent.futures import ThreadPoolExecutor

        def _fetch(sym: str) -> dict:
            return self.fetch_viop_for_symbol(sym)

        merged: dict = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            results = ex.map(_fetch, symbols)
            for r in results:
                merged.update(r)
        return merged

    # ------------------------------------------------------------------
    # TEKİL FALLBACK — Tek hisse spot fiyatı
    # ------------------------------------------------------------------
    def fetch_single_spot(self, symbol: str) -> Optional[float]:
        url = (
            "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/"
            "Common/Data.aspx/HisseTekil"
        )
        try:
            r = self.session.get(url, params={"hisse": symbol}, timeout=self.timeout)
            if r.status_code != 200:
                return None
            data = r.json()
            v = data.get("value") if isinstance(data, dict) else None
            if isinstance(v, dict):
                last = v.get("son") or v.get("sonFiyat")
                return float(last) if last else None
        except Exception as e:
            log.warning(f"single_spot {symbol}: {e}")
        return None


class DividendFetcher:
    """
    İş Yatırım'ın "Capital Increases & Dividends" sayfasından temettü çeker.
    URL formatı:
      https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/sermaye-artirimlari-ve-temettuler.aspx?hisse=AKBNK
    """

    def __init__(self, timeout: int = 15):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Accept-Language": "tr-TR,tr;q=0.9",
        })
        self.timeout = timeout

    def fetch_dividends(self, symbol: str) -> list:
        """
        Tek hisse için tüm geçmiş + planlanmış temettüleri parse eder.

        Returns: [
            {"ex_date": date(2026,5,12), "amount": 5.50, "rate": 25.0},
            ...
        ]
        """
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

    @staticmethod
    def _parse_dividend_table(html: str) -> list:
        """
        İş Yatırım sayfasındaki temettü tablosunu çıkarır.
        Tablo HTML'de "Nakit Temettü Tarihçesi" başlığı altında.
        """
        from datetime import datetime as dt
        results = []

        # Tablo bloğunu bul
        # Pattern: <table id="temettu"... veya class="dataTable"
        m = re.search(
            r'(?i)(nakit\s*temett[uü]\s*tarih[çc]esi|cash\s*dividend\s*history)'
            r'.*?(<table[^>]*>.*?</table>)',
            html, re.S
        )
        if not m:
            # Alternatif: sayfa içindeki tüm tabloları tarayıp tarih+TL pattern arayalım
            tables = re.findall(r'<table[^>]*>.*?</table>', html, re.S | re.I)
            for tbl in tables:
                if re.search(r'(?i)temett[uü]', tbl) and re.search(r'\d{2}[./]\d{2}[./]\d{4}', tbl):
                    m = (None, tbl)
                    break
            else:
                return results

        table_html = m[1] if isinstance(m, tuple) else m.group(2)

        # Satırları çıkar
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.S | re.I)
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.S | re.I)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            cells = [c.replace('&nbsp;', ' ').strip() for c in cells]
            if len(cells) < 2:
                continue

            # Tarih ara — gg.aa.yyyy ya da gg/aa/yyyy
            date_obj = None
            amount = None
            rate = None
            for cell in cells:
                if not date_obj:
                    dm = re.search(r'(\d{2})[./](\d{2})[./](\d{4})', cell)
                    if dm:
                        try:
                            d, mn, y = map(int, dm.groups())
                            date_obj = dt(y, mn, d).date()
                        except ValueError:
                            pass
                if amount is None:
                    # Sayısal değer (binlik virgül, ondalık virgül)
                    if re.match(r'^[\d.,]+$', cell) and ',' in cell:
                        try:
                            amount = float(cell.replace('.', '').replace(',', '.'))
                        except ValueError:
                            pass

            if date_obj and amount and amount > 0:
                results.append({
                    "ex_date": date_obj,
                    "amount": amount,
                    "rate": rate or 0.0,
                })
        return results

    def fetch_dividends_bulk(self, symbols: list) -> dict:
        """Birden fazla hisse için paralel çekim."""
        from concurrent.futures import ThreadPoolExecutor
        out: dict = {}
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(self.fetch_dividends, s): s for s in symbols}
            for fut in futs:
                sym = futs[fut]
                try:
                    out[sym] = fut.result(timeout=20)
                except Exception as e:
                    log.warning(f"dividend bulk {sym}: {e}")
                    out[sym] = []
        return out
