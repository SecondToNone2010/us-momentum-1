import os
import math
import time
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

WEIGHTS_FILE = "results/weights_latest.csv"
PAUSE_SECONDS = 1


def load_target_weights(path):
    if not os.path.exists(path):
        raise FileNotFoundError("weights_latest.csv not found. Run main.py first.")
    df = pd.read_csv(path)
    df = df[df["weight"] > 0].copy()
    if df.empty:
        raise ValueError("weights_latest.csv is empty.")
    return df


def get_client():
    api_key = os.getenv("APCA_API_KEY_ID")
    secret_key = os.getenv("APCA_API_SECRET_KEY")
    if not api_key or not secret_key:
        raise ValueError("Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY.")
    return TradingClient(api_key, secret_key, paper=True)


def get_current_positions(client):
    positions = {}
    for p in client.get_all_positions():
        positions[p.symbol] = float(p.qty)
    return positions


def submit_market_order(client, symbol, qty, side):
    if qty <= 0:
        return
    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.DAY,
    )
    result = client.submit_order(order_data=order)
    print(f"Submitted {side.value} order: {symbol} {qty}")
    return result


def main():
    target = load_target_weights(WEIGHTS_FILE)
    client = get_client()

    account = client.get_account()
    equity = float(account.equity)
    print("Account status:", account.status)
    print("Equity:", equity)
    print("Cash:", account.cash)

    current_positions = get_current_positions(client)
    target_symbols = set(target["symbol"])
    current_symbols = set(current_positions)

    # Close symbols no longer in target
    for symbol in sorted(current_symbols - target_symbols):
        qty = int(abs(current_positions[symbol]))
        if qty > 0:
            submit_market_order(client, symbol, qty, OrderSide.SELL)
            time.sleep(PAUSE_SECONDS)

    # Rebalance target symbols
    for _, row in target.iterrows():
        symbol = row["symbol"]
        weight = float(row["weight"])
        price = float(row["close"])
        if price <= 0:
            continue

        target_value = equity * weight
        target_qty = math.floor(target_value / price)
        current_qty = int(current_positions.get(symbol, 0))
        diff = target_qty - current_qty

        if diff > 0:
            submit_market_order(client, symbol, diff, OrderSide.BUY)
            time.sleep(PAUSE_SECONDS)
        elif diff < 0:
            submit_market_order(client, symbol, abs(diff), OrderSide.SELL)
            time.sleep(PAUSE_SECONDS)
        else:
            print(f"No trade needed: {symbol}")

    print("Paper rebalance finished.")


if __name__ == "__main__":
    main()
