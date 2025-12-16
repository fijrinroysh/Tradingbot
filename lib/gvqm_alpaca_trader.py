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
#  🎨 THE 3-COLUMN EXECUTION MATRIX (NUMERIC VERIFICATION)
# ==========================================================
def log_execution_matrix(ticker, command, initial_state, request_data, final_state, exec_result):
	   
																
																	 
	   
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    
    # --- HELPER: VALIDATION ICON ---
    def get_status_icon(target, actual):
        if target <= 0: return "" # Target wasn't set, no check needed
        if actual is None: return "❌" # Target set but missing in broker
        if abs(target - actual) < 0.02: return "✅" # Match (1 cent tolerance)
        return "⚠️" # Mismatch (Broker has different number)

    # --- 1. COLUMN: CURRENT STATE (Before) ---
    cur_lines = []
    if initial_state['shares'] > 0: cur_lines.append(f"Held:   {initial_state['shares']} sh")
    else: cur_lines.append("Held:   0 sh")
        
    if initial_state['pending_buy']: cur_lines.append(f"BuyLmt: ${initial_state['pending_buy']:.2f}")
    else: cur_lines.append("BuyLmt: None")
    
    if initial_state['tp'] > 0: cur_lines.append(f"Act TP: ${initial_state['tp']:.2f}")
    else: cur_lines.append("Act TP: None")
		
 
															  
							
										 
									  
																		  
        
    if initial_state['sl'] > 0: cur_lines.append(f"Act SL: ${initial_state['sl']:.2f}")
    else: cur_lines.append("Act SL: None")

    # --- 2. COLUMN: REQUEST (Senior Mgr) ---
    req_lines = []
    if "amt" in request_data: req_lines.append(f"Invest: ${request_data['amt']}")
    if request_data.get('limit', 0) > 0: req_lines.append(f"Set Buy: ${request_data['limit']:.2f}")
    else: req_lines.append("Set Buy: (Hold/Mkt)")
    
    req_lines.append(f"Set TP:  ${request_data['tp']:.2f}")
    req_lines.append(f"Set SL:  ${request_data['sl']:.2f}")

    # --- 3. COLUMN: UPDATED STATE (Broker) ---
    res_lines = []
    evt = exec_result[0].get("event", "UNKNOWN") if exec_result else "UNKNOWN"
    
    if evt in ["ERROR", "HOLD"]:
        res_lines.append(f"Status: {evt}")
        res_lines.append(f"Info:   {exec_result[0].get('info', '')[:15]}...")
    else:
        # Calculate Icons
        tp_icon = get_status_icon(request_data['tp'], final_state['tp'])
        sl_icon = get_status_icon(request_data['sl'], final_state['sl'])
        buy_icon = ""
        if request_data.get('limit', 0) > 0:
             buy_icon = get_status_icon(request_data['limit'], final_state['pending_buy'])

        # Print THE NUMBERS (With Icons)
        if final_state['shares'] > 0: res_lines.append(f"Held:   {final_state['shares']} sh")
        else: res_lines.append("Held:   0 sh")
        
        if final_state['pending_buy']: res_lines.append(f"BuyLmt: ${final_state['pending_buy']:.2f} {buy_icon}")
        else: res_lines.append("BuyLmt: None")
	 
																					

        if final_state['tp'] > 0: res_lines.append(f"Act TP: ${final_state['tp']:.2f} {tp_icon}")
        else: res_lines.append("Act TP: None")
        
        if final_state['sl'] > 0: res_lines.append(f"Act SL: ${final_state['sl']:.2f} {sl_icon}")
        else: res_lines.append("Act SL: None")
    
    # --- PRINT TABLE ---
    col_width = 32
    print(f"\n[{timestamp}] [EXECUTION] ║ {ticker:<6} | {command}")
    print("=" * 105)
    print(f"{'CURRENT STATE (Broker)':<{col_width}} | {'REQUEST (Senior Mgr)':<{col_width}} | {'UPDATED STATE (Broker)':<{col_width}}")
    print("-" * 105)
    
							 
    max_rows = max(len(cur_lines), len(req_lines), len(res_lines))
    for i in range(max_rows):
        c1 = cur_lines[i] if i < len(cur_lines) else ""
        c2 = req_lines[i] if i < len(req_lines) else ""
        c3 = res_lines[i] if i < len(res_lines) else ""
        print(f"{c1:<{col_width}} | {c2:<{col_width}} | {c3:<{col_width}}")
    print("-" * 105)
    print("\n")

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
def _fetch_snapshot(ticker):
    state = {"shares": 0.0, "pending_buy": None, "tp": 0.0, "sl": 0.0, "manual": False}
	  
	  
	
 
									 
			   
							
								   
						   
						   
							 
								
	 
	
    try:
   
        state["shares"] = get_position(ticker)

   
   
        req = GetOrdersRequest(status=QueryOrderStatus.ALL, symbols=[ticker], limit=500)
        all_orders = trading_client.get_orders(filter=req)
		
  
        live_statuses = ['new', 'partially_filled', 'accepted', 'pending_new', 'pending_replace', 'held']
        orders = [o for o in all_orders if (o.status.value if hasattr(o.status, 'value') else str(o.status)) in live_statuses]

																					 
	  
	 
        if any(o.side == OrderSide.BUY and o.type == OrderType.MARKET for o in orders):
  
   
            state["manual"] = True
																 
            return state

   
  
        buy = next((o for o in orders if o.side == OrderSide.BUY), None)
        if buy: state["pending_buy"] = float(buy.limit_price)

   
        tp = next((o for o in orders if o.side == OrderSide.SELL and o.type == OrderType.LIMIT), None)
        if tp: state["tp"] = float(tp.limit_price)

   
        sl = next((o for o in orders if o.side == OrderSide.SELL and o.type in [OrderType.STOP, OrderType.STOP_LIMIT]), None)
        if sl: state["sl"] = float(sl.stop_price) if sl.stop_price else float(sl.limit_price)
        
        return state
    except:
        return state

def get_position_details(ticker):
    ticker = normalize_ticker(ticker)
    snap = _fetch_snapshot(ticker)
    details = {
        "shares_held": snap["shares"], "pending_buy_limit": snap["pending_buy"],
        "active_tp": snap["tp"] if snap["tp"] > 0 else None,
        "active_sl": snap["sl"] if snap["sl"] > 0 else None,
        "status_msg": "NONE", "manual_override": snap["manual"]
    }
    
    if snap["manual"]: details["status_msg"] = "USER MANAGED (MARKET ORDER)"
    elif snap["shares"] > 0:
        details["status_msg"] = f"ACTIVE (TP: {snap['tp']} | SL: {snap['sl']})"
				 
															 
    elif snap["pending_buy"]:
        details["status_msg"] = f"PENDING BUY @ {snap['pending_buy']}"
        
					  
						   
															  
    return details

# ==========================================================
#  MAIN ENTRY POINTS (Verified & Validated)
# ==========================================================

def execute_update(ticker, take_profit, stop_loss, buy_limit=0):
    ticker = normalize_ticker(ticker)
			   
    req_data = {"limit": buy_limit, "tp": take_profit, "sl": stop_loss}
    
    # 1. SNAPSHOT BEFORE
    initial_state = _fetch_snapshot(ticker)
    if initial_state["manual"]:
        res = _enforce_contract({"event": "HOLD", "info": "User Manual Override"})
        log_execution_matrix(ticker, "UPDATE", initial_state, req_data, initial_state, res)
        return res

    # 2. EXECUTE
    try:
   
        req_filter = GetOrdersRequest(status=QueryOrderStatus.ALL, symbols=[ticker], limit=500)
        all_orders = trading_client.get_orders(filter=req_filter)
        live_statuses = ['new', 'partially_filled', 'accepted', 'pending_new', 'pending_replace', 'held']
        orders = [o for o in all_orders if (o.status.value if hasattr(o.status, 'value') else str(o.status)) in live_statuses]

														   
	  
																					   
	   
																					  
																 
					  
		
        buy = next((o for o in orders if o.side == OrderSide.BUY), None)
		
  
        if buy:
	   
            res = pending_mgr.manage_pending_order(trading_client, ticker, buy, buy_limit, take_profit, stop_loss, orders)
        else:
            if initial_state["shares"] > 0:
									  
					   
                res = filled_mgr.manage_active_position(trading_client, ticker, initial_state["shares"], take_profit, stop_loss, orders)
            else:
		
                res = [{"event": "HOLD", "info": "Nothing to update"}]
        
        final_res = _enforce_contract(res)
																   
						

    except Exception as e:
	 
        final_res = _enforce_contract({"event": "ERROR", "info": str(e)})

    # 3. VERIFY
    if final_res[0].get("event") not in ["ERROR", "HOLD"]:
        time.sleep(2) 
    
    final_state = _fetch_snapshot(ticker)
    
    # 4. LOG
    log_execution_matrix(ticker, "UPDATE", initial_state, req_data, final_state, final_res)
    return final_res

def execute_entry(ticker, investment_amount, buy_limit, take_profit, stop_loss):
 
	 
  
 
    ticker = normalize_ticker(ticker)
    req_data = {"limit": buy_limit, "tp": take_profit, "sl": stop_loss, "amt": investment_amount}
    
    # 1. SNAPSHOT
    initial_state = _fetch_snapshot(ticker)
    if initial_state["shares"] > 0 or initial_state["pending_buy"] or initial_state["manual"]:
        info = "Already Owned" if initial_state["shares"] > 0 else "Pending Exists"
        res = _enforce_contract({"event": "HOLD", "info": info})
        log_execution_matrix(ticker, "ENTRY", initial_state, req_data, initial_state, res)
        return res

    # 2. CALC & SUBMIT
		
   
																			  
															   
		
	  
																								
	   
    if buy_limit <= 0: return _enforce_contract({"event": "ERROR", "info": "Invalid Price"})
    qty = int(investment_amount / buy_limit)
					  
		
 
																						 
  
					   
	   
																					  
																
					  
			
						  
	 
 
 
    if qty < 1: return _enforce_contract({"event": "ERROR", "info": "Qty < 1"})
															
				  

						   
					  
																			
															
				  
		
											
				
																	  
															
				  
	
					 
    try:
        order = LimitOrderRequest(
            symbol=ticker, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
																		  
								   
            limit_price=buy_limit, order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=take_profit),
            stop_loss=StopLossRequest(stop_price=stop_loss)
        )
        trade = trading_client.submit_order(order)
	
        final_res = _enforce_contract(trade)
															
				  
    except Exception as e:
	 
        final_res = _enforce_contract({"event": "ERROR", "info": str(e)})

    # 3. VERIFY
    if final_res[0].get("event") not in ["ERROR", "HOLD"]:
        time.sleep(2) 
        
    final_state = _fetch_snapshot(ticker)
    log_execution_matrix(ticker, "ENTRY", initial_state, req_data, final_state, final_res)
    return final_res