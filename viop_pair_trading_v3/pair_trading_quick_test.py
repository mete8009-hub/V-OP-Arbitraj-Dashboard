"""Pair trading motoru için offline hızlı test.

İnternet gerekmez; sentetik koentegre iki seri üretip motorun çalıştığını kontrol eder.

    python pair_trading_quick_test.py
"""
import numpy as np
import pandas as pd

from src.pair_trading import PairTradingConfig, build_pair_detail, scan_pairs


def main():
    np.random.seed(42)
    idx = pd.date_range("2020-01-01", periods=800, freq="B")
    common_trend = np.cumsum(np.random.normal(0, 0.01, len(idx))) + 5

    # AAA ve BBB bilinçli olarak koentegre tasarlanmıştır.
    aaa = np.exp(0.30 + 1.15 * common_trend + np.random.normal(0, 0.015, len(idx)))
    bbb = np.exp(common_trend + np.random.normal(0, 0.015, len(idx)))
    ccc = np.exp(np.cumsum(np.random.normal(0, 0.02, len(idx))) + 4)

    prices = pd.DataFrame({"AAA": aaa, "BBB": bbb, "CCC": ccc}, index=idx)
    cfg = PairTradingConfig(
        min_obs=250,
        min_corr=0.50,
        max_coint_pvalue=0.20,
        max_adf_pvalue=0.20,
        min_trades=0,
    )

    result = scan_pairs(prices, ["AAA", "BBB", "CCC"], config=cfg)
    print(result[["Pair", "score", "coint_pvalue", "current_z", "hedge_ratio", "sharpe", "trade_count"]].head())

    detail = build_pair_detail(prices, "AAA", "BBB", config=cfg)
    assert detail and len(detail["spread"]) > 0 and len(detail["equity_curve"]) > 0
    print("\n✅ Pair trading motoru çalışıyor.")


if __name__ == "__main__":
    main()
