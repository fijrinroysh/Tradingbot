import config
import datetime
import time
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, TakeProfitRequest, StopLossRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus, OrderType
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# --- NEW IMPORTS (RENAMED) ---
import lib.gvqm_pending_orders_manager as pending_mgr
import lib.gvqm_alpaca_filled_orders_manager as filled_mgr

# Initialize Clients
trading_client = TradingClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY)

# --- SHARED UTILS ---
def log_trader(message):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [TRADER_MAIN] {message}")

def _enforce_contract(data):
    if hasattr(data, 'id'): return [{"event": "NEW_ENTRY", "order_id": str(data.id)}]
    if isinstance(data, list): return data if data else []
    return [{"event": "ERROR", "info": str(data)}]

def normalize_ticker(ticker): return ticker.replace('-', '.') if ticker else ticker

def get_current_price(ticker):
    ticker = normalize_ticker(ticker)
    try:
        req = StockLatestTradeRequest(symbol_or_symbols=ticker)
        return float(data_client.get_stock_latest_trade(req)[ticker].price)
    except: return None

def get_simple_moving_average(ticker, window=250):
    try:
        start_dt = datetime.datetime.now() - datetime.timedelta(days=window * 2) 
        req = StockBarsRequest(symbol_or_symbols=[normalize_ticker(ticker)], timeframe=TimeFrame.Day, start=start_dt, limit=window+10)
        closes = [b.close for b in data_client.get_stock_bars(req)[normalize_ticker(ticker)]]
        return float(sum(closes[-window:]) / window) if len(closes) >= window else None
    except: return None

def get_position(ticker):
    for _ in range(3):
        try: return float(trading_client.get_open_position(normalize_ticker(ticker)).qty)
        except: time.sleep(1)
    return 0.0

# ==========================================================
#  👀 THE CONTEXT FETCHER (UPDATED)
# ==========================================================
def get_position_details(ticker):
    """
    Returns the 'Reality' of a stock for the Senior Manager.
    UPDATED: Returns 'manual_override=True' if a Market Order is found.
    """
    ticker = normalize_ticker(ticker)
    details = {
        "shares_held": 0.0, 
        "pending_buy_limit": None, 
        "active_tp": None, 
        "active_sl": None, 
        "status_msg": "NONE",
        "manual_override": False  # <--- NEW FLAG
    }
    
    try:
        # 1. Check Holdings
        details["shares_held"] = get_position(ticker)

        # 2. Check Active Orders
        req = GetOrdersRequest(status=QueryOrderStatus.ALL, symbols=[ticker], limit=20)
        orders = [o for o in trading_client.get_orders(filter=req) if o.status in ['new', 'partially_filled', 'accepted', 'pending_new']]
        
        # --- DETECT MANUAL MARKET ORDERS ---
        # If we see a Market Order, we flag this stock as "User Managed"
        market_orders = [o for o in orders if o.type == OrderType.MARKET or o.limit_price is None]
        if market_orders:
            details["manual_override"] = True
            details["status_msg"] = "USER MANAGED (MARKET ORDER)"
            return details # Return immediately so Bot ignores details

        # Standard Logic
        buy = next((o for o in orders if o.side == OrderSide.BUY), None)
        if buy: details["pending_buy_limit"] = float(buy.limit_price)
        
        return details
    except Exception as e: 
        log_trader(f"⚠️ Detail Fetch Error {ticker}: {e}")
        return details

# ==========================================================
#  MAIN ENTRY POINTS (The Router)
# ==========================================================

def execute_update(ticker, take_profit, stop_loss, buy_limit=0):
    ticker = normalize_ticker(ticker)
    log_trader(f"🔄 EXECUTE_UPDATE {ticker} | Limit: {buy_limit} | TP: {take_profit} | SL: {stop_loss}")
    
    try:
        # 1. Fetch World State
        req_filter = GetOrdersRequest(status=QueryOrderStatus.ALL, symbols=[ticker], limit=50)
        all_orders = trading_client.get_orders(filter=req_filter)
        live_statuses = ['new', 'partially_filled', 'accepted', 'pending_new', 'pending_replace', 'held']
        orders = [o for o in all_orders if (o.status.value if hasattr(o.status, 'value') else str(o.status)) in live_statuses]
        
        # 2. Safety Check: Ignore User Market Orders
        if any(o.type == OrderType.MARKET for o in orders):
            log_trader(f"   🛑 SKIP: Found User Market Order. Ignoring update.")
            return _enforce_contract({"event": "HOLD", "info": "User Manual Override"})
        
        parent_buy = next((o for o in orders if o.side == OrderSide.BUY), None)
        
        # 3. Route to Specialist
        if parent_buy:
            log_trader("   👉 Routing to PENDING Orders Manager")
            res = pending_mgr.manage_pending_order(trading_client, ticker, parent_buy, buy_limit, take_profit, stop_loss, orders)
        else:
            log_trader("   👉 Routing to FILLED Orders Manager")
            qty = get_position(ticker)
            if qty > 0:
                res = filled_mgr.manage_active_position(trading_client, ticker, qty, take_profit, stop_loss, orders)
            else:
                log_trader("   ❌ No Position and No Pending Order. Nothing to update.")
                res = [{"event": "HOLD", "info": "Nothing to update"}]

        return _enforce_contract(res)

    except Exception as e:
        log_trader(f"❌ Router Error: {e}")
        return _enforce_contract({"event": "ERROR", "info": str(e)})

def execute_entry(ticker, investment_amount, buy_limit, take_profit, stop_loss):
    """
    Standard Entry Logic with DUPLICATE PROTECTION & MANUAL ORDER PROTECTION.
    Prevents opening new positions if we already own shares OR have a pending buy/market order.
    """
    ticker = normalize_ticker(ticker)
    log_trader(f"⚡ EXECUTE_ENTRY {ticker}")
    
    # 1. CHECK ACTIVE POSITION (Do we own shares?)
    qty_held = get_position(ticker)
    if qty_held > 0: 
        log_trader(f"   🛑 Aborting OPEN_NEW: Already own {qty_held} shares.")
        return _enforce_contract({"event": "HOLD", "info": "Already Owned"})

    # 2. CHECK PENDING ORDERS (Are we already waiting to buy?)
    try:
        # Get all open orders (New, Accepted, Pending)
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
        existing_orders = trading_client.get_orders(filter=req)
        
        # CRITICAL: If we see a Market Order here, ABORT.
        if any(o.type == OrderType.MARKET for o in existing_orders):
            log_trader(f"   🛑 ABORT: User Market Order detected. Bot will not touch this.")
            return _enforce_contract({"event": "HOLD", "info": "User Manual Override"})
        
        # Filter strictly for BUY orders (in case we have a stray sell order without position)
        pending_buy = next((o for o in existing_orders if o.side == OrderSide.BUY), None)
        
        if pending_buy:
            log_trader(f"   🛑 Aborting OPEN_NEW: Found Pending Buy Order ({pending_buy.id}).")
            return _enforce_contract({"event": "HOLD", "info": "Pending Order Exists"})
            
    except Exception as e:
        log_trader(f"   ⚠️ Duplicate Check Error: {e}")
																						
							   
        return _enforce_contract({"event": "ERROR", "info": "Duplicate Check Failed"})

    # 3. CALCULATE QUANTITY
    if buy_limit <= 0:
        return _enforce_contract({"event": "ERROR", "info": "Invalid Price"})
        
    qty = int(investment_amount / buy_limit)
    if qty < 1: 
        return _enforce_contract({"event": "ERROR", "info": "Qty < 1"})
    
    # 4. SUBMIT ORDER
    try:
        order = LimitOrderRequest(
            symbol=ticker, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
            limit_price=buy_limit, order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=take_profit),
            stop_loss=StopLossRequest(stop_price=stop_loss)
        )
        trade = trading_client.submit_order(order)
        log_trader(f"   ✅ Entry Order Placed. ID: {trade.id}")
        return _enforce_contract(trade)
    except Exception as e:
        log_trader(f"   ❌ Entry Failed: {e}")
        return _enforce_contract({"event": "ERROR", "info": str(e)})