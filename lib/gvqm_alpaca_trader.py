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
import time

# Initialize Clients
trading_client = TradingClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY)

# --- SAFETY LAYER ---
def _enforce_contract(data, context="UNKNOWN"):
														 
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

# --- ROBUST POSITION CHECK ---
def get_position(ticker):
    ticker = normalize_ticker(ticker)
    for attempt in range(3):
        try:
            return float(trading_client.get_open_position(ticker).qty)
        except Exception as e:
            err_str = str(e).lower()
            if "position does not exist" in err_str or "404" in err_str:
                return 0.0
            if attempt < 2:
                print(f"   ⚠️ Position Check Flake ({ticker}): {e}. Retrying ({attempt+1}/3)...")
                time.sleep(1)
            else:
                print(f"   ❌ Position Check Failed: {e}")
                return 0.0
    return 0.0

		   
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
        # 1. Fetch ALL orders (Open + Closed + Held)
        # We need 'ALL' because 'held' orders are not considered 'OPEN' by the API filter
        req_filter = GetOrdersRequest(
            status=QueryOrderStatus.ALL, 
            symbols=[ticker],
            limit=50  # Fetch recent history to find the active bracket
        )
        orders = trading_client.get_orders(filter=req_filter)
        
        # 2. DEFINE LIVE STATUSES (The "Active" List)
        # We manually filter for anything that represents a live, working order
        live_status_strings = [
            'new', 'partially_filled', 'accepted', 'pending_new', 
            'pending_replace', 'held', 'calculated', 'suspended'
        ]
        
        active_orders = []
        for o in orders:
            # FIX: Extract the raw string value from the Enum
            # If o.status is OrderStatus.HELD, .value gives "held"
            current_status = o.status.value if hasattr(o.status, 'value') else str(o.status)
            
            if current_status in live_status_strings:
                active_orders.append(o)

        # 3. PARSE ACTIVE ORDERS
        buy_order = next((o for o in active_orders if o.side == OrderSide.BUY), None)
        if buy_order:
									   
            price = buy_order.limit_price if buy_order.limit_price else "MKT"
            details["pending_buy_limit"] = float(price) if price != "MKT" else "MKT"
            details["status_msg"] = f"PENDING BUY @ ${details['pending_buy_limit']}"
        
	
	 
        for o in active_orders:
            if o.side == OrderSide.SELL:
		
   
                if o.type == OrderType.LIMIT: 
                    details["active_tp"] = float(o.limit_price)
                
                # Check for STOP and STOP_LIMIT
                elif o.type in [OrderType.STOP, OrderType.STOP_LIMIT]: 
                    price = o.stop_price if o.stop_price else o.limit_price
                    details["active_sl"] = float(price)
        
        # 4. CONSTRUCT STATUS MESSAGE
        if details["shares_held"] > 0:
            if details["active_tp"] and details["active_sl"]:
                details["status_msg"] = f"ACTIVE POS ({details['shares_held']}) | TP: ${details['active_tp']} | SL: ${details['active_sl']}"
            elif details["active_tp"]:
                details["status_msg"] = f"ACTIVE POS ({details['shares_held']}) | TP ONLY: ${details['active_tp']}"
            elif details["active_sl"]:
                details["status_msg"] = f"ACTIVE POS ({details['shares_held']}) | SL ONLY: ${details['active_sl']}"
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
#  COMMAND 1: EXECUTE ENTRY (WITH SAFETY BRAKE)
# ==========================================================
def execute_entry(ticker, investment_amount, buy_limit, take_profit, stop_loss):
    ticker = normalize_ticker(ticker)
    print(f"⚡ TRADER: Checking OPEN_NEW for {ticker}...")

    # 1. SAFETY BRAKE: Do we already own this?
    # This catches cases where Senior Manager received bad data (0 shares)
    existing_shares = get_position(ticker)
    if existing_shares > 0:
        msg = f"Safety Brake: We already own {existing_shares} shares of {ticker}. Aborting BUY."
        print(f"   🛑 {msg}")
        return _enforce_contract({"event": "HOLD", "info": msg})

    # 2. DUPLICATE CHECK: Is there a pending order?
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
        
				
        return _enforce_contract({
            "event": "NEW_ENTRY",
            "order_id": str(trade.id),
            "qty": qty,
            "price": buy_limit,       
            "take_profit": take_profit,
            "stop_loss": stop_loss,     
            "info": "Order Placed"
        })
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
        # Fetch ALL orders to ensure we see 'held' legs
        req_filter = GetOrdersRequest(status=QueryOrderStatus.ALL, symbols=[ticker])
        all_orders = trading_client.get_orders(filter=req_filter)
        
        # Filter for LIVE orders (Same logic as get_position_details)
        live_status_strings = ['new', 'partially_filled', 'accepted', 'pending_new', 'pending_replace', 'held']
        orders = [o for o in all_orders if (o.status.value if hasattr(o.status, 'value') else str(o.status)) in live_status_strings]
        
        # --- 1. CHECK FOR PENDING PARENT BUY (Pre-Market/Bracket Scenario) ---
        parent_buy = next((o for o in orders if o.side == OrderSide.BUY), None)
        
        if parent_buy and buy_limit > 0:
            current_limit = float(parent_buy.limit_price)
            
            # CHECK: Only update if diff >= 1 cent
            if abs(current_limit - float(buy_limit)) >= 0.01:
                try:
                    # ATTEMPT 1: The Polite Way (Replace)
                    trading_client.replace_order_by_id(parent_buy.id, ReplaceOrderRequest(limit_price=float(buy_limit)))
                    
									 
                    pct_change = ((float(buy_limit) - current_limit) / current_limit) * 100
                    delta_msg = f"{'⬆️' if pct_change > 0 else '⬇️'} {pct_change:.2f}%"
																
					
                    print(f"   ✅ Pending BUY Updated: {current_limit} -> {buy_limit} ({delta_msg})")
										
											   
											
                    actions_log.append({"event": "UPDATE_BUY", "price": buy_limit, "info": f"Old: {current_limit} | Delta: {delta_msg}"})
                
                except Exception as e:
                    # ATTEMPT 2: The Nuclear Way (Cancel & Resubmit)
                    # Catches "422 cannot replace order in accepted status"
                    if "422" in str(e) or "cannot replace" in str(e).lower():
                        print(f"   ⚠️ Replace Rejected ({e}). Switching to Cancel & Resubmit...")
                        
                        try:
                            # A. Scrape Existing Data to Preserve Strategy
                            qty = float(parent_buy.qty)
                            
                            # Find existing TP/SL if the Senior Manager passed 0 (No Change)
                            # We look at the 'held' child legs
                            existing_tp = next((o.limit_price for o in orders if o.side == OrderSide.SELL and o.type == OrderType.LIMIT), 0)
                            existing_sl = next((o.stop_price for o in orders if o.side == OrderSide.SELL and o.type in [OrderType.STOP, OrderType.STOP_LIMIT]), 0)
                            
                            # Use New Values if provided, else Fallback to Existing
                            final_tp = float(take_profit) if take_profit > 0 else float(existing_tp)
                            final_sl = float(stop_loss) if stop_loss > 0 else float(existing_sl)
                            
                            if final_tp <= 0 or final_sl <= 0:
                                raise ValueError(f"Cannot Resubmit. Missing Legs (TP:{final_tp}, SL:{final_sl})")

                            # B. Cancel Old Chain
                            trading_client.cancel_order_by_id(parent_buy.id)
                            time.sleep(1) # Safety pause for backend

                            # C. Resubmit New Bracket
                            new_order = LimitOrderRequest(
                                symbol=ticker,
                                qty=int(qty),
                                side=OrderSide.BUY,
                                time_in_force=TimeInForce.GTC,
                                limit_price=float(buy_limit),
                                order_class=OrderClass.BRACKET,
                                take_profit=TakeProfitRequest(limit_price=final_tp),
                                stop_loss=StopLossRequest(stop_price=final_sl)
                            )
                            trade = trading_client.submit_order(new_order)
                            
                            print(f"   ✅ Resubmit Successful. New ID: {trade.id}")
                            actions_log.append({
                                "event": "RESUBMIT_BUY", 
                                "price": buy_limit, 
                                "info": "Replaced via Resubmit (422 Fix)",
                                "order_id": str(trade.id)
                            })
                            
                        except Exception as resubmit_err:
                             print(f"   ❌ Resubmit Failed: {resubmit_err}")
                             actions_log.append({"event": "ERROR", "info": f"Resubmit Fail: {resubmit_err}"})
                    else:
                        print(f"   ❌ Failed to update Pending Buy: {e}")
                        actions_log.append({"event": "ERROR", "info": f"Buy Update Fail: {e}"})
            else:
                print(f"   ✋ Pending Buy aligned ({current_limit}). No change.")
                return _enforce_contract({"event": "HOLD", "info": "Pending Buy Aligned"})

        # --- 2. EXISTING POSITIONS (Standard Update) ---
	 
        tp_order = None
        sl_order = None
        
        for o in orders:
            if o.side == OrderSide.SELL:
                if o.type == OrderType.LIMIT: tp_order = o
                elif o.type in [OrderType.STOP, OrderType.STOP_LIMIT]: sl_order = o
        
        # RESCUE MODE (No Bracket Found)
        if not tp_order and not sl_order and not parent_buy:
             qty = get_position(ticker)
             if qty > 0:
                 print(f"   ⚠️ Shares found ({qty}) but NO valid TP/SL. Rescuing...")
				 
	  
                 if take_profit <= 0 or stop_loss <= 0:
																							
										   
                     return _enforce_contract({"event": "ERROR", "info": "Rescue Failed: Missing TP/SL"})
                 
                 if orders: trading_client.cancel_orders(symbols=[ticker])
                 
  
                 oco_data = LimitOrderRequest(
								   
							 
										 
                    symbol=ticker, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
											
                    limit_price=take_profit, order_class=OrderClass.OCO,
                    take_profit=TakeProfitRequest(limit_price=take_profit),
                    stop_loss=StopLossRequest(stop_price=stop_loss)
                 )
                 try:
                     trade = trading_client.submit_order(oco_data)
                     print(f"   ✅ Rescue Successful. ID: {trade.id}")
                     return _enforce_contract({"event": "RESCUE_OCO", "info": "Reset TP/SL", "order_id": str(trade.id)})
												
													
												
														   
												  
					   
                 except Exception as ex:
                     return _enforce_contract({"event": "ERROR", "info": str(ex)})
             else:
                 if not parent_buy: # Only error if we didn't just handle a parent buy
                    print("   ❌ No position/orders. Nothing to update.")
                    return _enforce_contract({"event": "ERROR", "info": "No Position/Orders"})

        # STANDARD TP/SL UPDATE (No changes needed here, existing logic works for Child Legs)
        if tp_order:
            current_limit = float(tp_order.limit_price)
													
            if take_profit > 0 and abs(current_limit - float(take_profit)) >= 0.01:
                try:
 
                    trading_client.replace_order_by_id(tp_order.id, ReplaceOrderRequest(limit_price=float(take_profit)))
                    
									 
                    pct_change = ((float(take_profit) - current_limit) / current_limit) * 100
                    delta_msg = f"{'⬆️' if pct_change > 0 else '⬇️'} {pct_change:.2f}%"
																
					
                    print(f"   ✅ TP Updated: {current_limit} -> {take_profit} ({delta_msg})")
										
											  
													
                    actions_log.append({"event": "UPDATE_TP", "take_profit": take_profit, "info": f"Old: {current_limit} | Delta: {delta_msg}"})
					  
                except Exception as e:
                    actions_log.append({"event": "ERROR", "info": f"TP Fail: {e}"})

        if sl_order:
            current_stop = float(sl_order.stop_price) if sl_order.stop_price else float(sl_order.limit_price)
													
            if stop_loss > 0 and abs(current_stop - float(stop_loss)) >= 0.01:
                try:
 
                    trading_client.replace_order_by_id(sl_order.id, ReplaceOrderRequest(stop_price=float(stop_loss)))
                    
									 
                    pct_change = ((float(stop_loss) - current_stop) / current_stop) * 100
                    delta_msg = f"{'⬆️' if pct_change > 0 else '⬇️'} {pct_change:.2f}%"
																
					
                    print(f"   ✅ SL Updated: {current_stop} -> {stop_loss} ({delta_msg})")
										
											  
												
                    actions_log.append({"event": "UPDATE_SL", "stop_loss": stop_loss, "info": f"Old: {current_stop} | Delta: {delta_msg}"})
					  
                except Exception as e:
                    actions_log.append({"event": "ERROR", "info": f"SL Fail: {e}"})

        if not actions_log:
            print("   > Orders aligned. No changes.")
            return _enforce_contract({"event": "HOLD", "info": "Orders Aligned"})

        return _enforce_contract(actions_log)

    except Exception as e:
        print(f"❌ Update Failed: {e}")
        return _enforce_contract({"event": "ERROR", "info": str(e)})