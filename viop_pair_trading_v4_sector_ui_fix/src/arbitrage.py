"""Arbitraj getirisi hesaplama."""
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class ArbitrageResult:
    symbol: str
    spot_price: float
    viop_price: float
    dividend: float
    expiry: date
    dtm: int
    spread: float
    spread_pct: float
    annualized_return: float
    is_active: bool


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
    """
    Yıllıklandırılmış arbitraj getirisi.

    Mantık:
      - Spot al + komisyon -> efektif maliyet
      - VİOP sat - komisyon -> efektif tahsilat (vade sonu)
      - Vade öncesi temettü dağıtılırsa eklenir (yatırımcı temettüyü alır)
      - Spread = efektif tahsilat + temettü - efektif maliyet
      - Yıllık = (spread / spot) * (365 / DTM)
    """
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

    cost = spot_price * (1 + spot_commission)
    proceeds = viop_price * (1 - viop_commission)
    spread = proceeds + dividend - cost
    spread_pct = (spread / spot_price) * 100.0
    annualized = spread_pct * (365.0 / dtm)

    return ArbitrageResult(
        symbol=symbol,
        spot_price=spot_price,
        viop_price=viop_price,
        dividend=dividend,
        expiry=expiry,
        dtm=dtm,
        spread=spread,
        spread_pct=spread_pct,
        annualized_return=annualized,
        is_active=True,
    )
