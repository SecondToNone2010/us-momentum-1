import os
import math
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt

# Simple momentum pipeline for US large-cap stocks
# - fixed universe
# - monthly rebalance
# - liquidity filter
# - MA200 / volatility / drawdown filters
# - momentum 3m / 6m / 12m ranking
# - inverse volatility weighting
# - transaction cost by turnover

TICKERS = [
    "AAPL","MSFT","AMZN","GOOGL","META","NVDA","BRK-B","LLY","JPM","V",
    "XOM","UNH","COST","PG","MA","HD","ABBV","CVX","MRK","KO",
    "BAC","PEP","AVGO","ADBE","WMT","CRM","AMD","MCD","CSCO","TMO",
    "ACN","DHR","LIN","ABT","NFLX","WFC","INTU","DIS","TXN","QCOM",
    "NKE","AMGN","PM","INTC","CAT","UNP","SPGI","LOW","IBM","GS"
]
BENCHMARK = "SPY"
START_DATE = "2018-01-01"
END_DATE = None
TOP_N = 10
MIN_NAMES = 5
COST_RATE = 0.001  # 10 bps one-way applied on turnover
MAX_WEIGHT = 0.20
MAX_VOL = 0.60
MIN_DOLLAR_VOLUME = 20_000_000
MAX_DRAWDOWN = -0.35


def download_data(tickers, start, end=None):
    raw = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    return raw


def split_fields(raw, tickers):
    close = pd.DataFrame(index=raw.index)
    volume = pd.DataFrame(index=raw.index)

    for t in tickers:
        if t in raw.columns.get_level_values(0):
            block = raw[t].copy()
            if "Close" in block.columns and "Volume" in block.columns:
                close[t] = block["Close"]
                volume[t] = block["Volume"]

    close = close.sort_index().ffill()
    volume = volume.sort_index().fillna(0)
    close = close.dropna(axis=1, how="all")
    volume = volume[close.columns]
    return close, volume


def compute_features(close, volume):
    daily_ret = close.pct_change()
    mom_3 = close / close.shift(63) - 1
    mom_6 = close / close.shift(126) - 1
    mom_12 = close / close.shift(252) - 1
    ma200 = close.rolling(200).mean()
    vol_90 = daily_ret.rolling(90).std() * np.sqrt(252)

    rolling_max_126 = close.rolling(126).max()
    drawdown_6m = close / rolling_max_126 - 1

    dollar_volume = close * volume
    adv_20 = dollar_volume.rolling(20).mean()

    return {
        "daily_ret": daily_ret,
        "mom_3": mom_3,
        "mom_6": mom_6,
        "mom_12": mom_12,
        "ma200": ma200,
        "vol_90": vol_90,
        "drawdown_6m": drawdown_6m,
        "adv_20": adv_20,
    }


def inverse_vol_weights(vol_series, cap=MAX_WEIGHT):
    inv = 1 / vol_series.replace(0, np.nan)
    inv = inv.replace([np.inf, -np.inf], np.nan).dropna()
    if inv.empty:
        return inv

    w = inv / inv.sum()

    # simple iterative cap
    for _ in range(10):
        if w.max() <= cap + 1e-10:
            break
        over = w[w > cap]
        under = w[w < cap]
        if under.empty:
            w = w.clip(upper=cap)
            w = w / w.sum()
            break
        excess = (over - cap).sum()
        w[over.index] = cap
        under_total = w[under.index].sum()
        if under_total > 0:
            w[under.index] = w[under.index] + excess * (w[under.index] / under_total)
        w = w / w.sum()

    return w


def compute_metrics(strategy_returns, benchmark_returns):
    strategy_returns = strategy_returns.dropna()
    benchmark_returns = benchmark_returns.reindex(strategy_returns.index).fillna(0)

    nav = (1 + strategy_returns).cumprod()
    bench_nav = (1 + benchmark_returns).cumprod()

    n = len(strategy_returns)
    ann_return = nav.iloc[-1] ** (252 / n) - 1 if n > 0 else np.nan
    ann_vol = strategy_returns.std() * np.sqrt(252)
    sharpe = ann_return / ann_vol if ann_vol and ann_vol > 0 else np.nan
    max_dd = (nav / nav.cummax() - 1).min()

    bench_ann_return = bench_nav.iloc[-1] ** (252 / n) - 1 if n > 0 else np.nan
    bench_ann_vol = benchmark_returns.std() * np.sqrt(252)
    bench_sharpe = bench_ann_return / bench_ann_vol if bench_ann_vol and bench_ann_vol > 0 else np.nan
    bench_max_dd = (bench_nav / bench_nav.cummax() - 1).min()

    summary = pd.DataFrame(
        {
            "metric": [
                "total_return",
                "annual_return",
                "annual_volatility",
                "sharpe",
                "max_drawdown",
                "benchmark_total_return",
                "benchmark_annual_return",
                "benchmark_annual_volatility",
                "benchmark_sharpe",
                "benchmark_max_drawdown",
            ],
            "value": [
                nav.iloc[-1] - 1,
                ann_return,
                ann_vol,
                sharpe,
                max_dd,
                bench_nav.iloc[-1] - 1,
                bench_ann_return,
                bench_ann_vol,
                bench_sharpe,
                bench_max_dd,
            ],
        }
    )
    return nav, bench_nav, summary


def main():
    os.makedirs("results", exist_ok=True)

    tickers = TICKERS + [BENCHMARK]
    print("Downloading data...")
    raw = download_data(tickers, START_DATE, END_DATE)
    close_all, volume_all = split_fields(raw, tickers)

    benchmark_close = close_all[BENCHMARK].copy().dropna()
    close = close_all.drop(columns=[BENCHMARK], errors="ignore")
    volume = volume_all.drop(columns=[BENCHMARK], errors="ignore")

    features = compute_features(close, volume)
    benchmark_returns = benchmark_close.pct_change().fillna(0)

    month_ends = close.resample("M").last().index

    current_weights = pd.Series(0.0, index=close.columns)
    portfolio_daily_returns = []
    weights_records = []
    daily_records = []
    turnover_records = []

    for i in range(12, len(month_ends) - 1):
        rebalance_date = month_ends[i]
        next_rebalance_date = month_ends[i + 1]

        tradable = close.index[close.index <= rebalance_date]
        if len(tradable) == 0:
            continue
        last_trade_date = tradable[-1]

        score_df = pd.DataFrame(index=close.columns)
        score_df["close"] = close.loc[last_trade_date]
        score_df["mom_3"] = features["mom_3"].loc[last_trade_date]
        score_df["mom_6"] = features["mom_6"].loc[last_trade_date]
        score_df["mom_12"] = features["mom_12"].loc[last_trade_date]
        score_df["ma200"] = features["ma200"].loc[last_trade_date]
        score_df["vol_90"] = features["vol_90"].loc[last_trade_date]
        score_df["drawdown_6m"] = features["drawdown_6m"].loc[last_trade_date]
        score_df["adv_20"] = features["adv_20"].loc[last_trade_date]

        score_df = score_df.replace([np.inf, -np.inf], np.nan).dropna()
        if score_df.empty:
            continue

        filtered = score_df[
            (score_df["close"] > score_df["ma200"]) &
            (score_df["vol_90"] < MAX_VOL) &
            (score_df["drawdown_6m"] > MAX_DRAWDOWN) &
            (score_df["adv_20"] > MIN_DOLLAR_VOLUME)
        ].copy()

        if len(filtered) < MIN_NAMES:
            target_weights = pd.Series(0.0, index=close.columns)
        else:
            filtered["rank_3"] = filtered["mom_3"].rank(ascending=False, method="average")
            filtered["rank_6"] = filtered["mom_6"].rank(ascending=False, method="average")
            filtered["rank_12"] = filtered["mom_12"].rank(ascending=False, method="average")
            filtered["score"] = -(filtered["rank_3"] + filtered["rank_6"] + filtered["rank_12"]) / 3
            selected = filtered.sort_values("score", ascending=False).head(TOP_N).copy()
            w = inverse_vol_weights(selected["vol_90"], cap=MAX_WEIGHT)
            target_weights = pd.Series(0.0, index=close.columns)
            target_weights.loc[w.index] = w.values

            for symbol, weight in w.items():
                weights_records.append(
                    {
                        "date": last_trade_date,
                        "symbol": symbol,
                        "weight": float(weight),
                        "close": float(selected.loc[symbol, "close"]),
                        "mom_3": float(selected.loc[symbol, "mom_3"]),
                        "mom_6": float(selected.loc[symbol, "mom_6"]),
                        "mom_12": float(selected.loc[symbol, "mom_12"]),
                        "vol_90": float(selected.loc[symbol, "vol_90"]),
                        "drawdown_6m": float(selected.loc[symbol, "drawdown_6m"]),
                        "adv_20": float(selected.loc[symbol, "adv_20"]),
                    }
                )

        turnover = (target_weights - current_weights).abs().sum()
        turnover_records.append({"date": last_trade_date, "turnover": float(turnover)})

        period_mask = (close.index > rebalance_date) & (close.index <= next_rebalance_date)
        period_returns = features["daily_ret"].loc[period_mask].fillna(0)
        if not period_returns.empty:
            gross = period_returns.mul(target_weights, axis=1).sum(axis=1)
            if len(gross) > 0:
                gross.iloc[0] = gross.iloc[0] - turnover * COST_RATE
            for d, r in gross.items():
                portfolio_daily_returns.append(r)
                daily_records.append({"date": d, "strategy_return": float(r)})

        current_weights = target_weights.copy()

    strategy_returns = pd.Series(portfolio_daily_returns, index=pd.to_datetime([r["date"] for r in daily_records]))
    strategy_returns = strategy_returns.sort_index()

    nav, bench_nav, summary = compute_metrics(strategy_returns, benchmark_returns)

    daily_df = pd.DataFrame(index=nav.index)
    daily_df["strategy_return"] = strategy_returns
    daily_df["strategy_nav"] = nav
    daily_df["benchmark_return"] = benchmark_returns.reindex(nav.index).fillna(0)
    daily_df["benchmark_nav"] = bench_nav.reindex(nav.index)
    daily_df.to_csv("results/daily_results.csv")

    weights_df = pd.DataFrame(weights_records)
    if not weights_df.empty:
        weights_df.to_csv("results/monthly_weights.csv", index=False)
        latest_date = weights_df["date"].max()
        latest_weights = weights_df[weights_df["date"] == latest_date][["symbol", "weight", "close"]].copy()
        latest_weights = latest_weights[latest_weights["weight"] > 0].sort_values("weight", ascending=False)
        latest_weights.to_csv("results/weights_latest.csv", index=False)
        print("Saved latest weights to results/weights_latest.csv")

    turnover_df = pd.DataFrame(turnover_records)
    if not turnover_df.empty:
        avg_turnover = turnover_df["turnover"].mean()
        summary = pd.concat([
            summary,
            pd.DataFrame({"metric": ["average_turnover"], "value": [avg_turnover]})
        ], ignore_index=True)
        turnover_df.to_csv("results/turnover.csv", index=False)

    summary.to_csv("results/summary.csv", index=False)

    plt.figure(figsize=(10, 5))
    plt.plot(nav.index, nav.values, label="Strategy")
    plt.plot(bench_nav.index, bench_nav.values, label="SPY")
    plt.legend()
    plt.title("Equity Curve")
    plt.tight_layout()
    plt.savefig("results/equity_curve.png", dpi=150)
    plt.close()

    print("Done. Check the results folder.")


if __name__ == "__main__":
    main()
