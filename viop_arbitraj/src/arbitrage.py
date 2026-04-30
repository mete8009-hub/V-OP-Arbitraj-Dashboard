"""
Arbitraj getirisi hesaplama.

Temel formül:
    Net VIOP = VIOP_fiyat - Temettü_brüt
    Spread = Net VIOP - Spot
    Yıllıklandırılmış getiri = (Spread / Spot) × (365 / DTM) × 100

Komisyon dahil net hesap için spot al/sat ve viop al/sat komisyonları düşülür.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class ArbitrageResult:
    symbol: str
    spot_price: float
    viop_price: float
    dividend: float          # vade öncesi düşülecek brüt temettü
    expiry: date
    dtm: int                 # days to maturity
    spread: float            # absolute spread (TL)
    spread_pct: float        # spread / spot
    annualized_return: float # %
    is_active: bool          # iki fiyat da var mı?

    @property
    def display_color(self) -> str:
        if not self.is_active:
            return "gray"
        if self.annualized_return > 0:
            return "green"
        return "red"


def calculate_arbitrage(
    symbol: str,
    spot_price: Optional[float],
    viop_price: Optional[float],
    expiry: date,
    today: date,
    dividend: float = 0.0,
    spot_commission: float = 0.0002,
    viop_commission: float = 0.0003,
) -> ArbitrageResult:
    """Tek bir hisse + vade için arbitraj getirisini hesapla."""
    dtm = (expiry - today).days

    if not spot_price or not viop_price or spot_price <= 0 or dtm <= 0:
        return ArbitrageResult(
            symbol=symbol,
            spot_price=spot_price or 0.0,
            viop_price=viop_price or 0.0,
            dividend=dividend,
            expiry=expiry,
            dtm=max(dtm, 0),
            spread=0.0,
            spread_pct=0.0,
            annualized_return=0.0,
            is_active=False,
        )

    # Komisyonları içeren etkin maliyet
    effective_buy_cost = spot_price * (1 + spot_commission)
    effective_sell_proceeds = viop_price * (1 - viop_commission)

    # Vade öncesi temettü dağıtılırsa, VİOP fiyatı temettü kadar düşeceği için
    # arbitraj kapatma anında elde edilen tutara temettü eklenmiş olur.
    # Net spread = (VİOP - komisyon) + temettü - (spot + komisyon)
    spread = effective_sell_proceeds + dividend - effective_buy_cost
    spread_pct = spread / spot_price
    annualized = spread_pct * (365.0 / dtm) * 100.0

    return ArbitrageResult(
        symbol=symbol,
        spot_price=spot_price,
        viop_price=viop_price,
        dividend=dividend,
        expiry=expiry,
        dtm=dtm,
        spread=spread,
        spread_pct=spread_pct * 100.0,
        annualized_return=annualized,
        is_active=True,
    )
