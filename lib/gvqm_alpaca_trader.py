import config
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    LimitOrderRequest, 
    TakeProfitRequest, 
    StopLossRequest, 
    ReplaceOrderRequest,
    GetOrdersRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus, OrderType
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest

# Initialize Clients
trading_client = TradingClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY)

# --- SAFETY LAYER ---
def _enforce_contract(data, context="UNKNOWN"):
    """Forces return data into a List of Dictionaries."""
    if hasattr(data, 'id'):
        return [{
            "event": "NEW_ENTRY",
            "order_id": str(data.id),
            "qty": getattr(data, 'qty', 0),
            "info": "Recovered from Raw Object"
        }]
    if isinstance(data, list):
        if not data: return data
        if hasattr(data[0], 'id'):
            return [_enforce_contract(item, context)[0] for item in data]
        return data
    if isinstance(data, dict):
        return [data]
    return [{"event": "ERROR", "info": f"Bad Data Type: {type(data)}"}]

def normalize_ticker(ticker):
    if not ticker: return ticker
    return ticker.replace('-', '.')

def is_market_open():
    try:
        return trading_client.get_clock().is_open
    except: return False

def get_current_price(ticker):
    ticker = normalize_ticker(ticker)
    try:
        req = StockLatestTradeRequest(symbol_or_symbols=ticker)
        res = data_client.get_stock_latest_trade(req)
        return float(res[ticker].price)
    except Exception as e:
        print(f"⚠️ [TRADER] Price Error {ticker}: {e}")
        return None

def get_position(ticker):
    ticker = normalize_ticker(ticker)
    try:
        return float(trading_client.get_open_position(ticker).qty)
    except:
        return 0.0

# --- DEEP DATA FETCH ---
def get_position_details(ticker):
																				 
    ticker = normalize_ticker(ticker)
    details = {
        "shares_held": get_position(ticker),
        "pending_buy_limit": None,
        "active_tp": None,
        "active_sl": None,
        "status_msg": "NONE"
    }
    
    try:
        req_filter = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
        orders = trading_client.get_orders(filter=req_filter)
        
        # 1. Check for Pending BUY
        buy_order = next((o for o in orders if o.side == OrderSide.BUY), None)
        if buy_order:
            details["pending_buy_limit"] = float(buy_order.limit_price) if buy_order.limit_price else "MKT"
            details["status_msg"] = f"PENDING BUY @ ${details['pending_buy_limit']}"
            
        # 2. Check for Active TP/SL (Sell Orders)
        tp_order = next((o for o in orders if o.side == OrderSide.SELL and o.type == OrderType.LIMIT), None)
        sl_order = next((o for o in orders if o.side == OrderSide.SELL and o.type == OrderType.STOP), None)
        
        if tp_order: details["active_tp"] = float(tp_order.limit_price)
        if sl_order: details["active_sl"] = float(sl_order.stop_price)
        
        if details["shares_held"] > 0:
            if tp_order and sl_order:
                details["status_msg"] = f"ACTIVE POS ({details['shares_held']}) | TP: ${details['active_tp']} | SL: ${details['active_sl']}"
            else:
                details["status_msg"] = f"ACTIVE POS ({details['shares_held']}) | NO BRACKET"
                
        return details
  
    except Exception as e:
        print(f"⚠️ [TRADER] Error getting details for {ticker}: {e}")
        return details

def get_pending_order_status(ticker):
    d = get_position_details(ticker)
    return d['status_msg'] if d['status_msg'] != "NONE" else None

# ==========================================================
#  COMMAND 1: EXECUTE ENTRY
# ==========================================================
def execute_entry(ticker, investment_amount, buy_limit, take_profit, stop_loss):
    ticker = normalize_ticker(ticker)
    print(f"⚡ TRADER: Checking OPEN_NEW for {ticker}...")

    # 1. DUPLICATE CHECK
    try:
        req_filter = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
        existing_orders = trading_client.get_orders(filter=req_filter)
        pending_buy = next((o for o in existing_orders if o.side == OrderSide.BUY), None)
        
        if pending_buy:
            print(f"   ✋ Pending BUY order found (ID: {pending_buy.id}). Skipping duplicate.")
            return _enforce_contract({"event": "HOLD", "info": "Pending Buy Exists", "order_id": str(pending_buy.id)})
            
    except Exception as e:
        print(f"   ⚠️ Could not check pending orders: {e}")

    if buy_limit <= 0:
        return _enforce_contract({"event": "ERROR", "info": "Senior Manager sent Buy_Limit=0 for a NEW entry."})

    try:
        cash = float(trading_client.get_account().buying_power)
    except: cash = 0.0
        
    if cash < investment_amount:
        print(f"   ❌ Insufficient Buying Power (${cash}).")
        return _enforce_contract({"event": "ERROR", "info": f"Insufficient Funds: ${cash}"})

    qty = int(investment_amount / buy_limit)
    if qty < 1: 
        return _enforce_contract({"event": "ERROR", "info": "Qty < 1"})

    # --- GTC (Good Till Canceled) ---
    order_data = LimitOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.GTC,
        limit_price=buy_limit,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=take_profit),
        stop_loss=StopLossRequest(stop_price=stop_loss)
    )

    try:
        trade = trading_client.submit_order(order_data)
        print(f"   ✅ Buy Order Placed. ID: {trade.id}")
        return _enforce_contract(trade, context=f"execute_entry({ticker})")
    except Exception as e:
        print(f"   ❌ Order Failed: {e}")
        return _enforce_contract({"event": "ERROR", "info": str(e)})

# ==========================================================
#  COMMAND 2: EXECUTE UPDATE
# ==========================================================
def execute_update(ticker, take_profit, stop_loss, buy_limit=0):
    ticker = normalize_ticker(ticker)
    print(f"♻️ TRADER: Executing UPDATE_EXISTING for {ticker}...")
    actions_log = []
    
    try:
        req_filter = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
        orders = trading_client.get_orders(filter=req_filter)
        
        # --- 1. CHECK FOR PENDING PARENT BUY (Pre-Market Scenario) ---
        parent_buy = next((o for o in orders if o.side == OrderSide.BUY), None)
        
        if parent_buy and buy_limit > 0:
            current_limit = float(parent_buy.limit_price)
            if abs(current_limit - float(buy_limit)) > (float(buy_limit) * 0.005):
                try:
                    # FIX: Use 'replace_order_by_id' instead of 'replace_order'
                    trading_client.replace_order_by_id(parent_buy.id, ReplaceOrderRequest(limit_price=float(buy_limit)))
                    print(f"   ✅ Pending BUY Updated: {current_limit} -> {buy_limit}")
                    actions_log.append({"event": "UPDATE_BUY", "info": f"New Entry: {buy_limit}"})
                    return _enforce_contract(actions_log)
                except Exception as e:
                    print(f"   ❌ Failed to update Pending Buy: {e}")
                    return _enforce_contract({"event": "ERROR", "info": f"Buy Update Fail: {e}"})
            else:
                print(f"   ✋ Pending Buy aligned ({current_limit}). No change.")
                return _enforce_contract({"event": "HOLD", "info": "Pending Buy Aligned"})

        # --- 2. EXISTING POSITIONS (Standard Update) ---
        tp_order = next((o for o in orders if o.type == OrderType.LIMIT and o.side == OrderSide.SELL), None)
        sl_order = next((o for o in orders if o.type == OrderType.STOP and o.side == OrderSide.SELL), None)
        
        # RESCUE MODE
        if not tp_order and not sl_order and not parent_buy:
             qty = get_position(ticker)
             if qty > 0:
                 print(f"   ⚠️ Shares found ({qty}) but NO valid TP/SL. Rescuing...")
                 
                 # --- STRICT MODE: NO AUTO-CALCULATION ---
                 if take_profit <= 0 or stop_loss <= 0:
                     err = f"Missing targets for rescue (TP={take_profit}, SL={stop_loss})."
                     print(f"   ❌ {err}")
                     return _enforce_contract({"event": "ERROR", "info": err})

                 if orders: trading_client.cancel_orders(symbols=[ticker])
                 
                 # --- GTC RESCUE ---
                 oco_data = LimitOrderRequest(
                    symbol=ticker, 
                    qty=qty, 
                    side=OrderSide.SELL, 
                    time_in_force=TimeInForce.GTC,
                    limit_price=take_profit, # Main Order Limit (TP)
                    order_class=OrderClass.OCO,
                    take_profit=TakeProfitRequest(limit_price=take_profit), # REQUIRED for OCO
                    stop_loss=StopLossRequest(stop_price=stop_loss)
                 )
                 try:
                     trade = trading_client.submit_order(oco_data)
                     print(f"   ✅ Rescue Successful. ID: {trade.id}")
                     return _enforce_contract({"event": "RESCUE_OCO", "info": "Reset TP/SL", "order_id": str(trade.id)})
                 except Exception as ex:
                     return _enforce_contract({"event": "ERROR", "info": str(ex)})
             else:
                 print("   ❌ No position and no orders. Nothing to update.")
                 return _enforce_contract({"event": "ERROR", "info": "No Position/Orders"})

        # STANDARD TP/SL UPDATE
        if tp_order:
            current_limit = float(tp_order.limit_price)
            if take_profit > 0 and abs(current_limit - float(take_profit)) > (float(take_profit) * 0.005):
                try:
                    # FIX: Use 'replace_order_by_id'
                    trading_client.replace_order_by_id(tp_order.id, ReplaceOrderRequest(limit_price=float(take_profit)))
                    print(f"   ✅ TP Updated: {current_limit} -> {take_profit}")
                    actions_log.append({"event": "UPDATE_TP", "info": f"Old: {current_limit}"})
                except Exception as e:
                    actions_log.append({"event": "ERROR", "info": f"TP Fail: {e}"})

        if sl_order:
            current_stop = float(sl_order.stop_price)
            if stop_loss > 0 and abs(current_stop - float(stop_loss)) > (float(stop_loss) * 0.005):
                try:
                    # FIX: Use 'replace_order_by_id'
                    trading_client.replace_order_by_id(sl_order.id, ReplaceOrderRequest(stop_price=float(stop_loss)))
                    print(f"   ✅ SL Updated: {current_stop} -> {stop_loss}")
                    actions_log.append({"event": "UPDATE_SL", "info": f"Old: {current_stop}"})
                except Exception as e:
                    actions_log.append({"event": "ERROR", "info": f"SL Fail: {e}"})

        if not actions_log:
            print("   > Orders aligned. No changes.")
            return _enforce_contract({"event": "HOLD", "info": "Orders Aligned"})

        return _enforce_contract(actions_log)

    except Exception as e:
        print(f"❌ Update Failed: {e}")
        return _enforce_contract({"event": "ERROR", "info": str(e)})
