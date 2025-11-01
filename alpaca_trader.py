# alpaca_trader.py
from alpaca.trading.client import TradingClient

from alpaca.trading.requests import MarketOrderRequest 
from alpaca.trading.enums import OrderSide, TimeInForce
# ---
from alpaca.common.exceptions import APIError
import config

# (Connection code is unchanged)
try:
    trading_client = TradingClient(
        config.ALPACA_KEY_ID, 
        config.ALPACA_SECRET_KEY, 
        paper=True
    )
    print("Alpaca Trader: Connected to paper trading account.")
except Exception as e:
    print(f"Alpaca Trader: Error connecting to Alpaca: {e}")
    trading_client = None


def place_buy_order(ticker, quantity):
    """
    (Webhook Function)
    Submits a market BUY order for a specific quantity.
    """
    if not trading_client:
        print("Alpaca Trader: Cannot trade, client not connected.")
        return

    print(f"Alpaca Trader (Qty): Submitting BUY order for {quantity} of {ticker}.")
    try:
        market_order_data = MarketOrderRequest(
            symbol=ticker,
            qty=quantity,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )
        buy_order = trading_client.submit_order(order_data=market_order_data)
        print(f"Alpaca Trader (Qty): BUY order submitted. Order ID: {buy_order.id}")
    except APIError as e:
        print(f"Alpaca Trader (Qty): Error placing BUY order: {e}")

# --- UPDATED FUNCTION ---
def place_notional_buy_order(ticker, trade_value):
    """
    (Sentiment Function)
    Submits a 'notional' (dollar amount) market BUY order.
    """
    if not trading_client:
        print("Alpaca Trader: Cannot trade, client not connected.")
        return

    print(f"Alpaca Trader (Notional): Submitting BUY order for ${trade_value} of {ticker}.")
    try:
        # --- THIS IS THE FIX ---
        # We use MarketOrderRequest and pass the 'notional' parameter.
        notional_order_data = MarketOrderRequest(
            symbol=ticker,
            notional=trade_value, # The dollar amount you want to buy
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )
        # --- END OF FIX ---
        
        buy_order = trading_client.submit_order(order_data=notional_order_data)
        print(f"Alpaca Trader (Notional): BUY order submitted. Order ID: {buy_order.id}")
    except APIError as e:
        print(f"Alpaca Trader (Notional): Error placing BUY order: {e}")
# --- END UPDATED FUNCTION ---


def place_sell_order(ticker, quantity):
    """
    (Webhook Function)
    Submits a market SELL order for a specific quantity.
    """
    if not trading_client:
        print("Alpaca Trader: Cannot trade, client not connected.")
        return

    print(f"Alpaca Trader (Qty): Submitting SELL order for {quantity} of {ticker}.")
    try:
        market_order_data = MarketOrderRequest(
            symbol=ticker,
            qty=quantity,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY
        )
        sell_order = trading_client.submit_order(order_data=market_order_data)
        print(f"Alpaca Trader (Qty): SELL order submitted. Order ID: {sell_order.id}")
    except APIError as e:
        print(f"Alpaca Trader (Qty): Error placing SELL order: {e}")

# (close_existing_position function is unchanged)
def close_existing_position(ticker):
    """
    (Shared Function)
    Submits a SELL order to liquidate the entire position for a ticker.
    """
    if not trading_client:
        print("Alpaca Trader: Cannot trade, client not connected.")
        return

    print(f"Alpaca Trader (Close): Submitting CLOSE order for all shares of {ticker}.")
    try:
        trading_client.close_position(ticker)
        print(f"Alpaca Trader (Close): CLOSE position order submitted for {ticker}.")
    except APIError as e:
        if "position not found" in str(e).lower():
            print(f"Alpaca Trader (Close): No position to close for {ticker}.")
        else:
            print(f"Alpaca Trader (Close): Error closing position: {e}")