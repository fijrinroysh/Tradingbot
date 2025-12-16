import config
import datetime
import time
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, TakeProfitRequest, StopLossRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus, OrderType
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# --- IMPORTS ---
import lib.gvqm_pending_orders_manager as pending_mgr
import lib.gvqm_alpaca_filled_orders_manager as filled_mgr

# Initialize Clients
trading_client = TradingClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY)

# ==========================================================
#  🎨 THE EXECUTION MATRIX LOGGER
# ==========================================================
def log_execution_matrix(ticker, command, request_data, result_data):
    """
    Prints a beautiful side-by-side Matrix comparing 'Request' vs 'Reality'.
    """
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    
    # Format Request Column (What Senior Mgr Wanted)
    req_str = f"{command}"
    if "limit" in request_data: req_str += f" | Lmt: {request_data['limit']}"
    if "tp" in request_data:    req_str += f" | TP: {request_data['tp']}"
    if "sl" in request_data:    req_str += f" | SL: {request_data['sl']}"
    
    # Format Result Column (What Actually Happened)
    res_str = "UNKNOWN"
    status_icon = "❓"
    
    if isinstance(result_data, list) and len(result_data) > 0:
        res = result_data[0]
        evt = res.get("event", "UNKNOWN")
        info = res.get("info", "")
        oid = res.get("order_id", "")[-4:] if "order_id" in res else ""
        
        if evt == "ERROR": 
            status_icon = "❌"
            res_str = f"FAILED: {info}"
        elif evt == "HOLD":
            status_icon = "🛑"
            res_str = f"BLOCKED: {info}"
        elif "NEW_ENTRY" in evt:
            status_icon = "✅"
            res_str = f"FILLED: ID..{oid}"
        elif "UPDATE" in evt:
            status_icon = "🔄"
            res_str = f"UPDATED: {info}"
        elif "REGENERATE" in evt or "RESUBMIT" in evt:
            status_icon = "☢️"
            res_str = f"NUCLEAR REBUILD: {info}"
        else:
            status_icon = "Hz"
            res_str = f"{evt}: {info}"
            
    print(f"[{timestamp}] [EXECUTION] ║ {ticker:<6} ║ {req_str:<45} ║ {status_icon} {res_str}")

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
#  👀 THE CONTEXT FETCHER
# ==========================================================
def get_position_details(ticker):
	   
															
																		
																
	   
    ticker = normalize_ticker(ticker)
    details = {
        "shares_held": 0.0, 
        "pending_buy_limit": None, 
        "active_tp": None, 
        "active_sl": None, 
        "status_msg": "NONE",
        "manual_override": False
    }
    
    try:
						   
        details["shares_held"] = get_position(ticker)

												
						
        req = GetOrdersRequest(status=QueryOrderStatus.ALL, symbols=[ticker], limit=500)
        all_orders = trading_client.get_orders(filter=req)
        
		
        live_statuses = ['new', 'partially_filled', 'accepted', 'pending_new', 'pending_replace', 'held']
        orders = [o for o in all_orders if (o.status.value if hasattr(o.status, 'value') else str(o.status)) in live_statuses]

															
																  
																	   
        if any(o.side == OrderSide.BUY and o.type == OrderType.MARKET for o in orders):
		
						
            details["manual_override"] = True
            details["status_msg"] = "USER MANAGED (MARKET ORDER)"
            return details 

							  
		
        buy = next((o for o in orders if o.side == OrderSide.BUY), None)
        if buy: details["pending_buy_limit"] = float(buy.limit_price)

			
        tp = next((o for o in orders if o.side == OrderSide.SELL and o.type == OrderType.LIMIT), None)
        if tp: details["active_tp"] = float(tp.limit_price)

		 
        sl = next((o for o in orders if o.side == OrderSide.SELL and o.type in [OrderType.STOP, OrderType.STOP_LIMIT]), None)
        if sl: 
	   
            details["active_sl"] = float(sl.stop_price) if sl.stop_price else float(sl.limit_price)

												
        if details["shares_held"] > 0:
            if details["active_tp"] and details["active_sl"]:
                details["status_msg"] = f"ACTIVE (TP: {details['active_tp']} | SL: {details['active_sl']})"
            elif details["active_tp"]:
                 details["status_msg"] = f"ACTIVE (TP: {details['active_tp']} | NO SL)"
            elif details["active_sl"]:
                 details["status_msg"] = f"ACTIVE (SL: {details['active_sl']} | NO TP)"
            else:
                details["status_msg"] = "ACTIVE (NO BRACKET)"
        elif details["pending_buy_limit"]:
            details["status_msg"] = f"PENDING BUY @ {details['pending_buy_limit']}"

        return details
    except Exception as e: 
        log_trader(f"⚠️ Detail Fetch Error {ticker}: {e}")
        return details

# ==========================================================
#  MAIN ENTRY POINTS (Updated with Matrix Logging)
# ==========================================================

def execute_update(ticker, take_profit, stop_loss, buy_limit=0):
    ticker = normalize_ticker(ticker)
    # Log Matrix happens at the END, but we prepare data now
    req_data = {"limit": buy_limit, "tp": take_profit, "sl": stop_loss}
    
    try:
							  
        req_filter = GetOrdersRequest(status=QueryOrderStatus.ALL, symbols=[ticker], limit=500)
        all_orders = trading_client.get_orders(filter=req_filter)
        live_statuses = ['new', 'partially_filled', 'accepted', 'pending_new', 'pending_replace', 'held']
        orders = [o for o in all_orders if (o.status.value if hasattr(o.status, 'value') else str(o.status)) in live_statuses]
        
																	
																	 
        if any(o.side == OrderSide.BUY and o.type == OrderType.MARKET for o in orders):
																				  
            res = _enforce_contract({"event": "HOLD", "info": "User Manual Override"})
            log_execution_matrix(ticker, "UPDATE", req_data, res)
            return res
        
        parent_buy = next((o for o in orders if o.side == OrderSide.BUY), None)
        
								
        if parent_buy:
																   
            res = pending_mgr.manage_pending_order(trading_client, ticker, parent_buy, buy_limit, take_profit, stop_loss, orders)
        else:
																  
            qty = get_position(ticker)
            if qty > 0:
                res = filled_mgr.manage_active_position(trading_client, ticker, qty, take_profit, stop_loss, orders)
            else:
																						 
                res = [{"event": "HOLD", "info": "Nothing to update"}]

        final_res = _enforce_contract(res)
        log_execution_matrix(ticker, "UPDATE", req_data, final_res)
        return final_res

    except Exception as e:
											
        err_res = _enforce_contract({"event": "ERROR", "info": str(e)})
        log_execution_matrix(ticker, "UPDATE", req_data, err_res)
        return err_res

def execute_entry(ticker, investment_amount, buy_limit, take_profit, stop_loss):
	   
																			 
  
	   
    ticker = normalize_ticker(ticker)
    req_data = {"limit": buy_limit, "tp": take_profit, "sl": stop_loss, "amt": investment_amount}
    
    # 1. CHECK ACTIVE POSITION
    qty_held = get_position(ticker)
    if qty_held > 0: 
																				
        res = _enforce_contract({"event": "HOLD", "info": "Already Owned"})
        log_execution_matrix(ticker, "ENTRY", req_data, res)
        return res

    # 2. CHECK PENDING ORDERS
    try:
   
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
        existing_orders = trading_client.get_orders(filter=req)
        
													  
        if any(o.side == OrderSide.BUY and o.type == OrderType.MARKET for o in existing_orders):
																							  
            res = _enforce_contract({"event": "HOLD", "info": "User Manual Override"})
            log_execution_matrix(ticker, "ENTRY", req_data, res)
            return res
        
	
        pending_buy = next((o for o in existing_orders if o.side == OrderSide.BUY), None)
  
        if pending_buy:
																								 
            res = _enforce_contract({"event": "HOLD", "info": "Pending Order Exists"})
            log_execution_matrix(ticker, "ENTRY", req_data, res)
            return res
            
    except Exception as e:
														   
 
 
        res = _enforce_contract({"event": "ERROR", "info": "Duplicate Check Failed"})
        log_execution_matrix(ticker, "ENTRY", req_data, res)
        return res

    # 3. CALCULATE QUANTITY
    if buy_limit <= 0:
        res = _enforce_contract({"event": "ERROR", "info": "Invalid Price"})
        log_execution_matrix(ticker, "ENTRY", req_data, res)
        return res
        
    qty = int(investment_amount / buy_limit)
    if qty < 1: 
        res = _enforce_contract({"event": "ERROR", "info": "Qty < 1"})
        log_execution_matrix(ticker, "ENTRY", req_data, res)
        return res
    
    # 4. SUBMIT ORDER
    try:
        order = LimitOrderRequest(
            symbol=ticker, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
            limit_price=buy_limit, order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=take_profit),
            stop_loss=StopLossRequest(stop_price=stop_loss)
        )
        trade = trading_client.submit_order(order)
																
        res = _enforce_contract(trade)
        log_execution_matrix(ticker, "ENTRY", req_data, res)
        return res
    except Exception as e:
											   
        res = _enforce_contract({"event": "ERROR", "info": str(e)})
        log_execution_matrix(ticker, "ENTRY", req_data, res)
        return res