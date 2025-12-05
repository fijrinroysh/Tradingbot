import config
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

# Initialize the client
trading_client = TradingClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY)

def get_buying_power():
    """Returns available cash to trade."""
    try:
        account = trading_client.get_account()
        return float(account.buying_power)
    except:
        return 0.0

def get_position(ticker):
    """
    Checks if we already own this stock.
    Returns the quantity owned (0 if none).
    """
    try:
        position = trading_client.get_open_position(ticker)
        return float(position.qty) # Use float to handle fractional shares
    except:
        return 0.0

def place_smart_trade(ticker, investment_amount, buy_limit, take_profit, stop_loss):
    """
    Places a BRACKET ORDER with a DAY entry and GTC exits.
    Includes a safety check to prevent duplicate positions.
    """
    print(f"--- TRADER: Preparing Smart Trade for {ticker} ---")
    
    # 1. SAFETY CHECK: Do we already own this?
    # This prevents buying the same stock twice.
    current_qty = get_position(ticker)
    if current_qty > 0:
        print(f"⚠️ TRADER ALERT: We already hold {current_qty} shares of {ticker}. Skipping new trade.")
        return None

    # 2. Check Funds
    cash = get_buying_power()
    if cash < investment_amount:
        print(f"TRADER ERROR: Insufficient funds (${cash:.2f}) for ${investment_amount} trade.")
        return None

    # 3. Calculate Quantity
    if buy_limit <= 0:
        print(f"TRADER ERROR: Invalid buy limit ${buy_limit}")
        return None
        
    qty = int(investment_amount / buy_limit)
    
    if qty < 1:
        print(f"TRADER ERROR: ${investment_amount} cannot buy 1 share of {ticker} at ${buy_limit}")
        return None

    print(f"   > Action: Buy {qty} shares @ ${buy_limit}")
    print(f"   > Exits:  TP ${take_profit} | SL ${stop_loss}")

    # 4. Construct the Bracket Order
    order_data = LimitOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY, # Entry expires today if not filled
        limit_price=buy_limit,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=take_profit),
        stop_loss=StopLossRequest(stop_price=stop_loss)
    )

    # 5. Submit
    try:
        trade = trading_client.submit_order(order_data)
        print(f"✅ TRADER SUCCESS: Smart Bracket Order placed. ID: {trade.id}")
        return trade
    except Exception as e:
        print(f"❌ TRADER FAILED: {e}")
        return None


def get_current_price(ticker):
    """
    Fetches the absolute latest real-time price (Ask Price) from Alpaca.
    This ensures we never trade on old data.
    """
    try:
        req = StockLatestQuoteRequest(symbol_or_symbols=ticker)
        res = data_client.get_stock_latest_quote(req)
        quote = res[ticker]
        # Use ask_price for buying (conservative), or calculate mid-point
        return float(quote.ask_price)
    except Exception as e:
        print(f"TRADER ERROR: Could not fetch price for {ticker}: {e}")
        return None


# --- Helper for Legacy Routes (Optional) ---
def place_notional_buy_order(ticker, notional_value):
    """
    Used by the SIP bot.
    """
    try:
        order_data = MarketOrderRequest(
            symbol=ticker,
            notional=notional_value,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )
        trading_client.submit_order(order_data)
        print(f"Placed Notional BUY order for ${notional_value} of {ticker}")
    except Exception as e:
        print(f"Failed to place buy order: {e}")

def close_existing_position(ticker):
    try:
        trading_client.close_position(ticker)
        print(f"Closed position for {ticker}")
    except Exception as e:
        print(f"No position to close for {ticker}: {e}")