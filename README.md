# US Momentum Backtest

A small personal project I built to test a fairly simple question: can a monthly momentum rule on liquid US large caps behave reasonably after adding a few risk filters and trading costs?

The model is deliberately simple. I wanted something I could understand end to end before adding more complicated signals.

## Rules

The current version:

- downloads adjusted price and volume data with `yfinance`
- calculates 3, 6 and 12 month momentum
- filters out names below their 200 day moving average
- removes very volatile names, deep recent drawdowns and illiquid stocks
- ranks the remaining stocks by average momentum rank
- holds the top 10
- uses inverse 90 day volatility for position sizing, with a 20% cap per name
- rebalances monthly
- charges 10 bps one way based on portfolio turnover
- compares the result with SPY

The latest target weights can also be passed to a separate Alpaca paper-trading script. It only connects to a paper account.

## Files

- `main.py` - data download, signals, portfolio construction and backtest
- `paper_trade.py` - simple Alpaca paper rebalance
- `requirements.txt` - Python dependencies
- `run_all.bat` - convenience script for Windows

The backtest writes its files to `results/`, including the daily equity curve, monthly weights, turnover and a summary table.

## Run

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

For the paper rebalance, set the Alpaca paper keys in the shell and then run:

```bat
set APCA_API_KEY_ID=YOUR_PAPER_KEY
set APCA_API_SECRET_KEY=YOUR_PAPER_SECRET
python paper_trade.py
```

## Things I would not treat as solved

This is a research/learning backtest, not a production strategy.

The stock universe is a fixed list of current large-cap names, so historical results have survivorship/selection bias. Data comes from yfinance, execution is simplified, and the cost model does not capture spread or market impact. The paper-trading script also sizes orders from the last saved model price rather than a full execution engine.

Those are the main things I would fix before using the project for more serious research.