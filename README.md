# us-momentum-1

Author: ptat

This repo is a simple monthly momentum model for US large-cap stocks.

What it does:
- downloads price and volume data with yfinance
- computes 3-month, 6-month, and 12-month momentum
- uses MA200, volatility, drawdown, and dollar-volume filters
- ranks names by momentum
- builds a portfolio with inverse-volatility weights
- rebalances monthly
- includes transaction cost in the backtest
- compares performance with SPY
- exports the latest target weights for Alpaca paper trading

Files:
- `main.py`: runs the backtest and saves outputs in `results/`
- `paper_trade.py`: reads `results/weights_latest.csv` and sends paper orders to Alpaca
- `run_all.bat`: runs the model and then runs the paper-trading rebalance

Outputs from `main.py`:
- `results/daily_results.csv`
- `results/monthly_weights.csv`
- `results/weights_latest.csv`
- `results/turnover.csv`
- `results/summary.csv`
- `results/equity_curve.png`

## Run locally

Open Command Prompt in this folder and run:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Run Alpaca paper rebalance

Before running `paper_trade.py`, set your paper keys in Command Prompt:

```bat
set APCA_API_KEY_ID=YOUR_PAPER_KEY
set APCA_API_SECRET_KEY=YOUR_PAPER_SECRET
python paper_trade.py
```

## Notes

This is a small personal project for research and learning. It uses a fixed stock list and simple assumptions. In the future, I will try improving data quality, adding more realistic backtesting assumptions (slippage, execution lag, etc) and systematically testing new strategy variations.
