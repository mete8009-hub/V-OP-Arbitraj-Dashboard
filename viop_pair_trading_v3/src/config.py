"""
Yapılandırma — sembol listesi, vade tarihleri, yardımcı fonksiyonlar.
"""
from datetime import date

# Görseldeki dashboard'da kullanılan hisse listesi (sıralı)
DASHBOARD_STOCKS = [
    "AEFES", "AKBNK", "AKSEN", "ALARK", "ARCLK", "ASELS", "ASTOR",
    "BIMAS", "BRSAN", "CIMSA", "DOAS", "DOHOL", "EKGYO", "ENJSA",
    "ENKAI", "EREGL", "FROTO", "GARAN", "GUBRF", "HALKB", "HEKTS",
    "ISCTR", "KCHOL", "KONTR", "KRDMD", "MGROS", "ODAS", "OYAKC",
    "PETKM", "PGSUS", "SAHOL", "SASA", "SISE", "SOKM", "TAVHL",
    "TCELL", "THYAO", "TKFEN", "TOASO", "TRALT", "TRMET", "TSKB",
    "TTKOM", "TUPRS", "ULKER", "VAKBN", "VESTL", "YKBNK",
]

# 2026 VİOP vade sonu tarihleri
EXPIRY_DATES_2026 = {
    1:  date(2026, 1, 30),
    2:  date(2026, 2, 27),
    3:  date(2026, 3, 31),
    4:  date(2026, 4, 30),
    5:  date(2026, 5, 29),
    6:  date(2026, 6, 30),
    7:  date(2026, 7, 31),
    8:  date(2026, 8, 31),
    9:  date(2026, 9, 30),
    10: date(2026, 10, 30),
    11: date(2026, 11, 27),
    12: date(2026, 12, 31),
}
EXPIRY_DATES_2027 = {
    1:  date(2027, 1, 29),
    2:  date(2027, 2, 26),
    3:  date(2027, 3, 31),
    4:  date(2027, 4, 30),
    5:  date(2027, 5, 31),
    6:  date(2027, 6, 30),
}

ALL_EXPIRIES = {
    **{(m, 2026): d for m, d in EXPIRY_DATES_2026.items()},
    **{(m, 2027): d for m, d in EXPIRY_DATES_2027.items()},
}

# Komisyon varsayımları
SPOT_COMMISSION_RATE = 0.0002
VIOP_COMMISSION_RATE = 0.0003

# Güncellenme aralığı (saniye)
REFRESH_INTERVAL_SEC = 15

# Temettü ve KAP cache (uzun TTL — sık değişmez)
DIVIDEND_CACHE_TTL_SEC = 3600  # 1 saat

# AYLAR (Türkçe görüntü)
MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def get_viop_code(symbol: str, month: int, year: int) -> str:
    """F_AKBNK0426 gibi VİOP kontrat kodu üretir."""
    return f"F_{symbol}{month:02d}{str(year)[-2:]}"


def get_active_contract_months(today: date, count: int = 3) -> list:
    """Bugünden sonra ilk `count` aktif vadeyi döndürür."""
    months = []
    y, m = today.year, today.month
    while len(months) < count:
        key = (m, y)
        expiry = ALL_EXPIRIES.get(key)
        if expiry and expiry > today:
            months.append((m, y))
        m += 1
        if m > 12:
            m = 1
            y += 1
        if y > 2027:
            break
    return months


def days_to_maturity(today: date, expiry: date) -> int:
    return (expiry - today).days
