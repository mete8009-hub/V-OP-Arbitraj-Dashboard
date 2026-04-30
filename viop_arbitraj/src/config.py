"""
Yapılandırma: BIST 30 hisseleri, VİOP kontrat kodları, vade tarihleri.

VIOP vade tarihleri her ayın son iş gününden bir önceki gündür.
Format: F_HISSE_KOD_AYYIL → F_AKBNK0426 (Nisan 2026)

Resmi vade kodları:
- F: Futures
- HISSE: hisse sembolü (AKBNK, AEFES, vb.)
- AAYIL: AY (2 hane) + YIL (2 hane). Örn: 0426 = Nisan 2026
"""
from datetime import date

# BIST 30 endeksindeki hisseler (görseldeki dashboard'da gösterilen liste)
BIST30_STOCKS = [
    "AEFES", "AKBNK", "AKSEN", "ALARK", "ARCLK", "ASELS", "ASTOR",
    "BIMAS", "BRSAN", "CIMSA", "DOAS", "DOHOL", "EKGYO", "ENJSA",
    "ENKAI", "EREGL", "FROTO", "GARAN", "GUBRF", "HALKB", "HEKTS",
    "ISCTR", "KCHOL", "KONTR", "KRDMD", "MGROS", "ODAS", "OYAKC",
    "PETKM", "PGSUS", "SAHOL", "SASA", "SISE", "SOKM", "TAVHL",
    "TCELL", "THYAO", "TKFEN", "TOASO", "TRALT", "TRMET", "TSKB",
    "TTKOM", "TUPRS", "ULKER", "VAKBN", "VESTL", "YKBNK"
]

# 2026 yılı VİOP vade sonu tarihleri (her ayın son iş günü)
# Kaynak: Borsa İstanbul VİOP takvimi
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

# Komisyon ve maliyet varsayımları (yıllıklandırılmış getirinin "net" hesabı için)
SPOT_COMMISSION_RATE = 0.0002   # %0.02
VIOP_COMMISSION_RATE = 0.0003   # %0.03 (kontrat başına)
T_PLUS = 2  # T+2 takas

# Yenileme aralığı (saniye) — Streamlit cache TTL
REFRESH_INTERVAL_SEC = 15

def get_viop_code(symbol: str, expiry_month: int, expiry_year: int) -> str:
    """
    VİOP kontrat kodunu üret.
    Örn: AKBNK + 04 + 26 → F_AKBNK0426
    """
    return f"F_{symbol}{expiry_month:02d}{str(expiry_year)[-2:]}"

def get_active_contract_months(today: date) -> list[tuple[int, int]]:
    """
    Bugün için aktif olan ilk 3 vade ayını döndür.
    Returns: [(month, year), ...] — yakın, orta, uzak vade
    """
    months = []
    y, m = today.year, today.month
    for _ in range(3):
        # Eğer içinde bulunduğumuz ayın expiry'si geçmişse, bir sonraki aya geç
        if y == 2026 and m in EXPIRY_DATES_2026:
            if today > EXPIRY_DATES_2026[m]:
                m += 1
                if m > 12:
                    m = 1
                    y += 1
        months.append((m, y))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months

def days_to_maturity(today: date, expiry: date) -> int:
    """Vade sonuna kalan gün sayısı."""
    return (expiry - today).days
