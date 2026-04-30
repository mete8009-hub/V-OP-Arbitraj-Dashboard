"""Statistical pair trading analizi.

Bu modül BIST hisseleri için:
- log fiyat regresyonu ile hedge ratio,
- Engle-Granger koentegrasyon testi,
- spread ADF testi,
- z-score,
- half-life,
- basit z-score mean-reversion backtesti
üretir.

Not: Bu bir yatırım tavsiyesi motoru değildir. Veri kalitesi, işlem maliyeti,
short/ödünç erişimi, teminat ve execution koşulları ayrıca kontrol edilmelidir.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from itertools import combinations
import math
from typing import Iterable, Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, coint


TRADING_DAYS = 252


@dataclass(frozen=True)
class PairTradingConfig:
    min_obs: int = 252
    min_corr: float = 0.65
    max_coint_pvalue: float = 0.10
    max_adf_pvalue: float = 0.10
    z_window: int = 60
    entry_z: float = 2.0
    exit_z: float = 0.5
    stop_z: float = 3.5
    transaction_cost_bps: float = 10.0
    min_trades: int = 2
    min_half_life: float = 0.5
    max_half_life: float = 90.0
    max_pairs: int = 5000

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_float(x, default=np.nan) -> float:
    try:
        y = float(x)
        return y if np.isfinite(y) else default
    except Exception:
        return default


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return np.nan
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def _half_life(spread: pd.Series) -> float:
    s = pd.Series(spread).dropna()
    if len(s) < 30:
        return np.nan
    lagged = s.shift(1).dropna()
    delta = s.diff().dropna()
    df = pd.concat([delta.rename("delta"), lagged.rename("lagged")], axis=1).dropna()
    if len(df) < 30:
        return np.nan
    try:
        model = sm.OLS(df["delta"], sm.add_constant(df["lagged"])).fit()
        beta = _safe_float(model.params.get("lagged"))
        if not np.isfinite(beta) or beta >= 0:
            return np.nan
        return float(-math.log(2) / beta)
    except Exception:
        return np.nan


def _zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window).mean()
    std = series.rolling(window).std(ddof=0)
    z = (series - mean) / std.replace(0, np.nan)
    return z.replace([np.inf, -np.inf], np.nan)


def _signal_from_z(z: float, a: str, b: str, entry_z: float) -> str:
    if not np.isfinite(z):
        return "Veri yetersiz"
    if z <= -entry_z:
        return f"{a} Long / {b} Short"
    if z >= entry_z:
        return f"{a} Short / {b} Long"
    return "Aktif sinyal yok"


def backtest_zscore_pair(
    price_a: pd.Series,
    price_b: pd.Series,
    alpha: float,
    hedge_ratio: float,
    config: PairTradingConfig,
) -> dict:
    """Basit z-score mean-reversion backtesti.

    Pozisyon yönü:
    +1 = A long / B short
    -1 = A short / B long
     0 = pozisyon yok

    İşlem maliyeti gross exposure üzerinden yaklaşık uygulanır.
    """
    df = pd.concat([price_a.rename("a"), price_b.rename("b")], axis=1).dropna()
    df = df[(df["a"] > 0) & (df["b"] > 0)].copy()
    if len(df) < max(config.min_obs, config.z_window + 5):
        return {
            "total_return_pct": np.nan,
            "annual_return_pct": np.nan,
            "sharpe": np.nan,
            "max_drawdown_pct": np.nan,
            "trade_count": 0,
            "win_rate_pct": np.nan,
            "avg_holding_days": np.nan,
        }

    log_a = np.log(df["a"])
    log_b = np.log(df["b"])
    spread = log_a - (alpha + hedge_ratio * log_b)
    z = _zscore(spread, config.z_window)

    ret_a = df["a"].pct_change().fillna(0.0)
    ret_b = df["b"].pct_change().fillna(0.0)

    beta_abs = abs(float(hedge_ratio)) if np.isfinite(hedge_ratio) else 1.0
    gross = 1.0 + beta_abs
    w_a = 1.0 / gross
    w_b = beta_abs / gross

    positions = []
    strategy_returns = []
    current_pos = 0
    prev_pos = 0
    entry_equity = None
    entry_idx = None
    trade_returns = []
    holding_days = []
    equity_value = 1.0

    cost_rate = float(config.transaction_cost_bps) / 10000.0

    for i in range(len(df)):
        if i == 0:
            positions.append(0)
            strategy_returns.append(0.0)
            continue

        # Bugünkü getiri, dünkü kapanışta görülen z-score sinyaline göre alınır.
        signal_z = z.iloc[i - 1]
        prev_pos = current_pos

        if np.isfinite(signal_z):
            if current_pos == 0:
                if signal_z <= -config.entry_z:
                    current_pos = 1
                    entry_equity = equity_value
                    entry_idx = i
                elif signal_z >= config.entry_z:
                    current_pos = -1
                    entry_equity = equity_value
                    entry_idx = i
            else:
                exit_by_mean = abs(signal_z) <= config.exit_z
                exit_by_stop = abs(signal_z) >= config.stop_z
                if exit_by_mean or exit_by_stop:
                    if entry_equity is not None and entry_equity > 0:
                        trade_returns.append(equity_value / entry_equity - 1.0)
                    if entry_idx is not None:
                        holding_days.append(i - entry_idx)
                    current_pos = 0
                    entry_equity = None
                    entry_idx = None

        pair_ret = current_pos * (w_a * ret_a.iloc[i] - w_b * ret_b.iloc[i])
        turnover = abs(current_pos - prev_pos)
        net_ret = pair_ret - turnover * cost_rate
        strategy_returns.append(float(net_ret))
        positions.append(current_pos)
        equity_value *= (1.0 + float(net_ret))

    out = pd.DataFrame(index=df.index)
    out["position"] = positions
    out["strategy_return"] = strategy_returns
    out["equity"] = (1.0 + out["strategy_return"]).cumprod()

    valid_ret = out["strategy_return"].dropna()
    total_return = float(out["equity"].iloc[-1] - 1.0) if not out.empty else np.nan
    ann_return = (1.0 + total_return) ** (TRADING_DAYS / max(len(out), 1)) - 1.0 if np.isfinite(total_return) else np.nan
    vol = valid_ret.std(ddof=0) * math.sqrt(TRADING_DAYS)
    sharpe = ann_return / vol if vol and np.isfinite(vol) and vol > 0 else np.nan
    max_dd = _max_drawdown(out["equity"])
    wins = [x for x in trade_returns if x > 0]
    win_rate = len(wins) / len(trade_returns) if trade_returns else np.nan

    return {
        "total_return_pct": total_return * 100 if np.isfinite(total_return) else np.nan,
        "annual_return_pct": ann_return * 100 if np.isfinite(ann_return) else np.nan,
        "sharpe": sharpe,
        "max_drawdown_pct": max_dd * 100 if np.isfinite(max_dd) else np.nan,
        "trade_count": int(len(trade_returns)),
        "win_rate_pct": win_rate * 100 if np.isfinite(win_rate) else np.nan,
        "avg_holding_days": float(np.mean(holding_days)) if holding_days else np.nan,
        "equity_curve": out["equity"],
        "position": out["position"],
        "rolling_z": z,
        "spread": spread,
    }


def _score_pair(row: dict, config: PairTradingConfig) -> float:
    coint_p = row.get("coint_pvalue", np.nan)
    adf_p = row.get("adf_pvalue", np.nan)
    z = abs(row.get("current_z", np.nan))
    sharpe = row.get("sharpe", np.nan)
    half = row.get("half_life_days", np.nan)
    corr = abs(row.get("corr_log_price", np.nan))
    trades = row.get("trade_count", 0)
    max_dd = abs(row.get("max_drawdown_pct", np.nan))

    def clip01(v):
        if not np.isfinite(v):
            return 0.0
        return float(max(0.0, min(1.0, v)))

    coint_component = clip01((config.max_coint_pvalue - coint_p) / max(config.max_coint_pvalue, 1e-9))
    adf_component = clip01((config.max_adf_pvalue - adf_p) / max(config.max_adf_pvalue, 1e-9))
    z_component = clip01(z / max(config.entry_z * 1.5, 1e-9))
    sharpe_component = clip01((sharpe + 0.25) / 2.25)  # -0.25 -> 0, 2.0 -> 1
    corr_component = clip01((corr - config.min_corr) / max(1.0 - config.min_corr, 1e-9))
    trade_component = clip01(trades / max(config.min_trades * 3, 1))
    dd_component = 1.0 - clip01((max_dd - 5.0) / 35.0) if np.isfinite(max_dd) else 0.0

    half_component = 0.0
    if np.isfinite(half):
        if config.min_half_life <= half <= config.max_half_life:
            # 10-30 gün arası en verimli kabul edilir; uçlara gittikçe puan azalır.
            center = 20.0
            half_component = 1.0 - min(abs(half - center) / max(config.max_half_life - center, center - config.min_half_life), 1.0)

    score = (
        22 * coint_component
        + 14 * adf_component
        + 18 * z_component
        + 18 * sharpe_component
        + 10 * half_component
        + 8 * corr_component
        + 5 * trade_component
        + 5 * dd_component
    )
    return round(float(score), 2)


def analyze_pair(
    prices: pd.DataFrame,
    symbol_a: str,
    symbol_b: str,
    config: PairTradingConfig | None = None,
) -> Optional[dict]:
    config = config or PairTradingConfig()
    if symbol_a not in prices.columns or symbol_b not in prices.columns:
        return None

    df = prices[[symbol_a, symbol_b]].dropna().copy()
    df = df[(df[symbol_a] > 0) & (df[symbol_b] > 0)]
    if len(df) < config.min_obs:
        return None

    y = np.log(df[symbol_a].astype(float))
    x = np.log(df[symbol_b].astype(float))

    try:
        model = sm.OLS(y, sm.add_constant(x)).fit()
        alpha = _safe_float(model.params.iloc[0])
        hedge_ratio = _safe_float(model.params.iloc[1])
        spread = y - (alpha + hedge_ratio * x)
        coint_score, coint_pvalue, _ = coint(y, x)
        adf_pvalue = adfuller(spread.dropna(), autolag="AIC")[1]
    except Exception:
        return None

    corr_log = y.corr(x)
    corr_ret = df[symbol_a].pct_change().corr(df[symbol_b].pct_change())
    half = _half_life(spread)
    rolling_z = _zscore(spread, config.z_window)
    current_z = _safe_float(rolling_z.dropna().iloc[-1]) if not rolling_z.dropna().empty else np.nan

    bt = backtest_zscore_pair(
        df[symbol_a],
        df[symbol_b],
        alpha=alpha,
        hedge_ratio=hedge_ratio,
        config=config,
    )

    row = {
        "Pair": f"{symbol_a}/{symbol_b}",
        "A": symbol_a,
        "B": symbol_b,
        "Obs": int(len(df)),
        "Start": df.index.min().strftime("%Y-%m-%d"),
        "End": df.index.max().strftime("%Y-%m-%d"),
        "corr_log_price": _safe_float(corr_log),
        "corr_return": _safe_float(corr_ret),
        "hedge_ratio": hedge_ratio,
        "alpha": alpha,
        "coint_pvalue": _safe_float(coint_pvalue),
        "adf_pvalue": _safe_float(adf_pvalue),
        "half_life_days": _safe_float(half),
        "current_z": current_z,
        "signal": _signal_from_z(current_z, symbol_a, symbol_b, config.entry_z),
        "total_return_pct": _safe_float(bt.get("total_return_pct")),
        "annual_return_pct": _safe_float(bt.get("annual_return_pct")),
        "sharpe": _safe_float(bt.get("sharpe")),
        "max_drawdown_pct": _safe_float(bt.get("max_drawdown_pct")),
        "trade_count": int(bt.get("trade_count", 0) or 0),
        "win_rate_pct": _safe_float(bt.get("win_rate_pct")),
        "avg_holding_days": _safe_float(bt.get("avg_holding_days")),
    }
    row["score"] = _score_pair(row, config)
    return row


def scan_pairs(
    prices: pd.DataFrame,
    symbols: Iterable[str] | None = None,
    config: PairTradingConfig | None = None,
    apply_filters: bool = True,
) -> pd.DataFrame:
    """Tüm ikili kombinasyonları tarar ve skorlanmış sonuç döndürür."""
    config = config or PairTradingConfig()
    if prices is None or prices.empty:
        return pd.DataFrame()

    if symbols is None:
        symbols = list(prices.columns)
    symbols = [s for s in symbols if s in prices.columns]
    if len(symbols) < 2:
        return pd.DataFrame()

    pairs = list(combinations(symbols, 2))
    if len(pairs) > config.max_pairs:
        pairs = pairs[: config.max_pairs]

    rows = []
    for a, b in pairs:
        row = analyze_pair(prices, a, b, config=config)
        if not row:
            continue

        if apply_filters:
            if abs(row["corr_log_price"]) < config.min_corr:
                continue
            if row["coint_pvalue"] > config.max_coint_pvalue:
                continue
            if row["adf_pvalue"] > config.max_adf_pvalue:
                continue
            if row["trade_count"] < config.min_trades:
                continue
            half = row["half_life_days"]
            if np.isfinite(half) and not (config.min_half_life <= half <= config.max_half_life):
                continue

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    sort_cols = ["score", "sharpe", "total_return_pct", "current_z"]
    existing = [c for c in sort_cols if c in df.columns]
    return df.sort_values(existing, ascending=[False] * len(existing)).reset_index(drop=True)


def build_pair_detail(
    prices: pd.DataFrame,
    symbol_a: str,
    symbol_b: str,
    config: PairTradingConfig | None = None,
) -> dict:
    """Seçili pair için grafiklerde kullanılacak spread/z/equity serilerini döndürür."""
    config = config or PairTradingConfig()
    row = analyze_pair(prices, symbol_a, symbol_b, config=config)
    if row is None:
        return {}

    df = prices[[symbol_a, symbol_b]].dropna().copy()
    y = np.log(df[symbol_a])
    x = np.log(df[symbol_b])
    spread = y - (row["alpha"] + row["hedge_ratio"] * x)
    bt = backtest_zscore_pair(
        df[symbol_a],
        df[symbol_b],
        alpha=row["alpha"],
        hedge_ratio=row["hedge_ratio"],
        config=config,
    )
    return {
        "row": row,
        "spread": spread,
        "rolling_z": bt.get("rolling_z"),
        "equity_curve": bt.get("equity_curve"),
        "position": bt.get("position"),
    }
