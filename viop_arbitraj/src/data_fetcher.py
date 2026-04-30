"""
Veri çekme katmanı.

Spot fiyatlar için: İş Yatırım intraday endpoint (toplum tarafından on yıldır kullanılıyor, stabil)
VİOP fiyatlar için: İş Yatırım VİOP endpoint

Eğer İş Yatırım çalışmazsa, fallback olarak Mynet/BIST scraping kullanılır.
"""
import requests
from typing import Optional
from datetime import datetime
import logging

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Referer": "https://www.isyatirim.com.tr/",
    "X-Requested-With": "XMLHttpRequest",
}

# İş Yatırım'ın toplum bilinen ajax endpoint'leri
# Bu endpoint'ler İş Yatırım'ın kendi web sitesinin arka planda kullandığı endpoint'ler
SPOT_PRICE_URL = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/MarketData"
ALL_STOCKS_URL = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/StockListByExchange"
VIOP_LIST_URL = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/ViopList"


class DataFetcher:
    """İş Yatırım API'sinden BIST hisseleri ve VİOP kontratları için fiyat çeker."""

    def __init__(self, timeout: int = 10):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.timeout = timeout

    def fetch_all_spot_prices(self) -> dict[str, float]:
        """
        Tüm BIST hisselerinin son fiyatlarını tek seferde çek.
        Returns: {"AKBNK": 65.85, "GARAN": 145.20, ...}

        İş Yatırım'ın "BorsaIstanbulPanel" endpoint'i tüm hisseleri JSON olarak döner.
        """
        url = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/MarketData"
        params = {"endeks": "tum"}
        try:
            r = self.session.get(url, params=params, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            prices = {}
            # İş Yatırım yanıt formatı: {"value": [{"sembol": "AKBNK", "son": 65.85, ...}, ...]}
            items = data.get("value", data) if isinstance(data, dict) else data
            for item in items:
                symbol = item.get("sembol") or item.get("kod")
                price = item.get("son") or item.get("sonFiyat") or item.get("kapanis")
                if symbol and price:
                    prices[symbol.upper()] = float(price)
            return prices
        except Exception as e:
            log.error(f"Spot fiyat çekme hatası: {e}")
            return {}

    def fetch_spot_price(self, symbol: str) -> Optional[float]:
        """Tek bir hissenin son fiyatını çek (yedek metod)."""
        url = (
            "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/"
            f"Data.aspx/HisseTekil?hisse={symbol}"
        )
        try:
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict):
                price = data.get("son") or data.get("value", {}).get("son")
                return float(price) if price else None
            return None
        except Exception as e:
            log.warning(f"{symbol} spot fiyat hatası: {e}")
            return None

    def fetch_all_viop_prices(self) -> dict[str, float]:
        """
        Tüm aktif VİOP kontratlarının fiyatlarını tek seferde çek.
        Returns: {"F_AKBNK0426": 66.45, "F_AKBNK0526": 67.20, ...}
        """
        url = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/ViopMarketData"
        try:
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            prices = {}
            items = data.get("value", data) if isinstance(data, dict) else data
            for item in items:
                code = item.get("sembol") or item.get("kod")
                price = item.get("son") or item.get("sonFiyat")
                if code and price:
                    prices[code.upper()] = float(price)
            return prices
        except Exception as e:
            log.error(f"VİOP fiyat çekme hatası: {e}")
            return {}

    def fetch_viop_price(self, contract_code: str) -> Optional[float]:
        """Tek bir VİOP kontratının fiyatını çek."""
        url = (
            "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/"
            f"Data.aspx/ViopTekil?sembol={contract_code}"
        )
        try:
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict):
                price = data.get("son") or data.get("value", {}).get("son")
                return float(price) if price else None
        except Exception as e:
            log.warning(f"{contract_code} VİOP fiyat hatası: {e}")
        return None


# ----------------------------------------------------------------------------
# FALLBACK: BorsaDirekt / Mynet scraping (İş Yatırım çalışmazsa devreye girer)
# ----------------------------------------------------------------------------
class FallbackFetcher:
    """İş Yatırım erişilemezse alternatif kaynak."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_spot_via_mynet(self, symbol: str) -> Optional[float]:
        """Mynet finans'tan tek hisse fiyatı."""
        import re
        url = f"https://finans.mynet.com/borsa/hisseler/{symbol.lower()}/"
        try:
            r = self.session.get(url, timeout=10)
            r.raise_for_status()
            # Mynet HTML'inde son fiyat genellikle <strong class="price up/down">XX.YY</strong>
            m = re.search(r'class="price\s*(?:up|down|equal)?"[^>]*>([\d.,]+)</', r.text)
            if m:
                return float(m.group(1).replace(",", "."))
        except Exception as e:
            log.warning(f"Mynet fallback {symbol}: {e}")
        return None
