"""
Temettü verileri.

İlk versiyonda manuel sözlük + KAP'tan haftalık güncelleme.
İleride Fintables MCP entegrasyonu ile otomatize edilecek.
"""
from datetime import date
from typing import Optional

# Manuel temettü takvimi (Excel'deki "DIVIDENDS" tablosu)
# Format: {symbol: {"amount": brüt_TL_per_share, "ex_date": dağıtım_tarihi}}
# NOT: Bu liste yöneticinin paylaştığı dashboard'daki "DIVIDENDS" panelinden
# alınmıştır. Gerçek hayatta KAP'tan veya Fintables MCP'den otomatik çekilir.

DIVIDEND_CALENDAR_2026 = {
    # Mayıs ayı temettüleri
    "AEFES": {"amount": 0.0, "ex_date": date(2026, 5, 15)},   # placeholder
    "ALARK": {"amount": 0.0, "ex_date": date(2026, 5, 20)},   # placeholder
    "MGROS": {"amount": 0.0, "ex_date": date(2026, 5, 22)},   # placeholder
    # Haziran ayı temettüleri
    "BIMAS": {"amount": 0.0, "ex_date": date(2026, 6, 10)},
    "EKGYO": {"amount": 0.0, "ex_date": date(2026, 6, 15)},
    "EREGL": {"amount": 0.0, "ex_date": date(2026, 6, 18)},
    "SISE":  {"amount": 0.0, "ex_date": date(2026, 6, 25)},
}


def get_dividend_for_period(symbol: str, today: date, expiry: date) -> float:
    """
    Bugün ile vade arasında ex-temettü tarihi varsa, brüt tutarı döndür.
    Yoksa 0 döner.
    """
    info = DIVIDEND_CALENDAR_2026.get(symbol)
    if not info:
        return 0.0
    ex_date = info["ex_date"]
    if today < ex_date <= expiry:
        return float(info["amount"])
    return 0.0


def get_dividend_calendar_view() -> dict[str, list[str]]:
    """Sağ paneldeki ay-bazlı temettü listesi için."""
    by_month = {}
    for sym, info in DIVIDEND_CALENDAR_2026.items():
        month = info["ex_date"].strftime("%B")
        by_month.setdefault(month, []).append(sym)
    return by_month
