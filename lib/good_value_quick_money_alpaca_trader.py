import config
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data.historical import StockHistoricalDataClient
# --- THIS IS THE FIX (Import Trade Request) ---
from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest
# ----------------------------------------------

# Initialize Clients
# Use paper=True for testing
trading_client = TradingClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY)


# --- NEW FUNCTION: Market Status Check ---
def is_market_open():
    """
    Checks if the US Stock Market is currently open (Regular Trading Hours).
    Returns: True (Open) or False (Closed).
    """
    try:
        clock = trading_client.get_clock()
        if clock.is_open:
            print(f"✅ [TRADER] Market is OPEN. (Next close: {clock.next_close})")
            return True
        else:
            print(f"🛑 [TRADER] Market is CLOSED. (Next open: {clock.next_open})")
            return False
    except Exception as e:
        print(f"⚠️ [TRADER] Error checking market clock: {e}")
        # Fail-safe: If we can't check, assume CLOSED to prevent errors.
        return False
# -----------------------------------------
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
        return float(position.qty)
    except:
        return 0.0

# --- UPDATED FUNCTION ---
def get_current_price(ticker):
    """
    Fetches the Last Traded Price from Alpaca.
    This is much more stable than the 'Ask' price for daily analysis.
    """
    try:
        # Use StockLatestTradeRequest instead of Quote
        req = StockLatestTradeRequest(symbol_or_symbols=ticker)
        res = data_client.get_stock_latest_trade(req)
        trade = res[ticker]
        
        # Return the actual price it last traded at
        return float(trade.price)
    except Exception as e:
        print(f"TRADER ERROR: Could not fetch price for {ticker}: {e}")
        return None
# ------------------------

def place_smart_trade(ticker, investment_amount, buy_limit, take_profit, stop_loss):
    """
    Places a BRACKET ORDER with a DAY entry and GTC exits.
    """
    print(f"--- TRADER: Preparing Smart Trade for {ticker} ---")
    
    # 1. Check Position
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
        time_in_force=TimeInForce.DAY, # Entry expires today
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