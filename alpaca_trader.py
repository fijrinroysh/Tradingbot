# alpaca_trader.py
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.common.exceptions import APIError
import config  # Import our keys

# Initialize the Alpaca client once when the file is imported
try:
    trading_client = TradingClient(
        config.ALPACA_KEY_ID, 
        config.ALPACA_SECRET_KEY, 
        paper=True  # Set to False for live trading
    )
    print("Alpaca Trader: Connected to paper trading account.")
except Exception as e:
    print(f"Alpaca Trader: Error connecting to Alpaca: {e}")
    trading_client = None

def place_buy_order(ticker, quantity):
    """
    Submits a market BUY order to Alpaca.
    """
    if not trading_client:
        print("Alpaca Trader: Cannot trade, client not connected.")
        return

    print(f"Alpaca Trader: Submitting BUY order for {quantity} of {ticker}.")
    try:
        market_order_data = MarketOrderRequest(
            symbol=ticker,
            qty=quantity,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )
        buy_order = trading_client.submit_order(order_data=market_order_data)
        print(f"Alpaca Trader: BUY order submitted. Order ID: {buy_order.id}")
    except APIError as e:
        print(f"Alpaca Trader: Error placing BUY order: {e}")
    except Exception as e:
        print(f"Alpaca Trader: An unknown error occurred during buy: {e}")

def close_existing_position(ticker):
    """
    Submits a SELL order to liquidate the entire position for a ticker.
    """
    if not trading_client:
        print("Alpaca Trader: Cannot trade, client not connected.")
        return

    print(f"Alpaca Trader: Submitting CLOSE order for all shares of {ticker}.")
    try:
        # This one command liquidates the entire position
        trading_client.close_position(ticker)
        print(f"Alpaca Trader: CLOSE position order submitted for {ticker}.")
    except APIError as e:
        # This error is expected if you have no position to sell.
        if "position not found" in str(e).lower():
            print(f"Alpaca Trader: No position to close for {ticker}.")
        else:
            print(f"Alpaca Trader: Error closing position: {e}")
    except Exception as e:
        print(f"Alpaca Trader: An unknown error occurred during close: {e}")