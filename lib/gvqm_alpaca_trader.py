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

# --- UTILS ---
def _enforce_contract(data, context="UNKNOWN"):
    if hasattr(data, 'id'):
        return [{"event": "NEW_ENTRY", "order_id": str(data.id), "qty": getattr(data, 'qty', 0), "info": "Recovered"}]
    if isinstance(data, list): return data if data else []
    if isinstance(data, dict): return [data]
    return [{"event": "ERROR", "info": f"Bad Data: {type(data)}"}]

def normalize_ticker(ticker):
    return ticker.replace('-', '.') if ticker else ticker

def get_position(ticker):
    ticker = normalize_ticker(ticker)
    for attempt in range(3):
        try:
            return float(trading_client.get_open_position(ticker).qty)
        except Exception as e:
            if "404" in str(e) or "position does not exist" in str(e).lower(): return 0.0
            if attempt < 2: time.sleep(1)
            else: return 0.0
    return 0.0

def get_position_details(ticker):
    ticker = normalize_ticker(ticker)
    details = {"shares_held": get_position(ticker), "pending_buy_limit": None, "active_tp": None, "active_sl": None, "status_msg": "NONE"}
    try:
        req_filter = GetOrdersRequest(status=QueryOrderStatus.ALL, symbols=[ticker], limit=50)
        orders = trading_client.get_orders(filter=req_filter)
        live_statuses = ['new', 'partially_filled', 'accepted', 'pending_new', 'pending_replace', 'held']
        active_orders = [o for o in orders if (o.status.value if hasattr(o.status, 'value') else str(o.status)) in live_statuses]

        buy = next((o for o in active_orders if o.side == OrderSide.BUY), None)
        if buy: details["pending_buy_limit"] = float(buy.limit_price) if buy.limit_price else "MKT"

        for o in active_orders:
            if o.side == OrderSide.SELL:
                if o.type == OrderType.LIMIT: details["active_tp"] = float(o.limit_price)
                elif o.type in [OrderType.STOP, OrderType.STOP_LIMIT]: 
                    details["active_sl"] = float(o.stop_price) if o.stop_price else float(o.limit_price)
        
        # Status Msg Logic
        if details["shares_held"] > 0:
            if details["active_tp"] and details["active_sl"]: details["status_msg"] = f"ACTIVE POS | TP: {details['active_tp']} | SL: {details['active_sl']}"
            elif details["active_tp"]: details["status_msg"] = f"ACTIVE POS | TP ONLY: {details['active_tp']}"
            else: details["status_msg"] = "ACTIVE POS | NO BRACKET"
        elif buy:
             details["status_msg"] = f"PENDING BUY @ {details['pending_buy_limit']}"
             
        return details
    except: return details

# ==========================================================
#  INTERNAL HELPERS (THE CLEANUP)
# ==========================================================
def _update_legs(orders, take_profit, stop_loss):
    """Shared logic to update TP and SL on existing orders."""
    logs = []
    
    tp_order = next((o for o in orders if o.side == OrderSide.SELL and o.type == OrderType.LIMIT), None)
    sl_order = next((o for o in orders if o.side == OrderSide.SELL and o.type in [OrderType.STOP, OrderType.STOP_LIMIT]), None)

    # Update TP
    if tp_order and take_profit > 0:
        current = float(tp_order.limit_price)
        if abs(current - float(take_profit)) >= 0.01:
            try:
                trading_client.replace_order_by_id(tp_order.id, ReplaceOrderRequest(limit_price=float(take_profit)))
                pct = ((float(take_profit) - current) / current) * 100
                print(f"   ✅ TP Updated: {current} -> {take_profit}")
                logs.append({"event": "UPDATE_TP", "take_profit": take_profit, "info": f"Delta: {pct:.2f}%"})
            except Exception as e: logs.append({"event": "ERROR", "info": f"TP Fail: {e}"})

    # Update SL
    if sl_order and stop_loss > 0:
        current = float(sl_order.stop_price) if sl_order.stop_price else float(sl_order.limit_price)
        if abs(current - float(stop_loss)) >= 0.01:
            try:
                trading_client.replace_order_by_id(sl_order.id, ReplaceOrderRequest(stop_price=float(stop_loss)))
                pct = ((float(stop_loss) - current) / current) * 100
                print(f"   ✅ SL Updated: {current} -> {stop_loss}")
                logs.append({"event": "UPDATE_SL", "stop_loss": stop_loss, "info": f"Delta: {pct:.2f}%"})
            except Exception as e: logs.append({"event": "ERROR", "info": f"SL Fail: {e}"})

    return logs

def _handle_pending_update(ticker, parent_buy, buy_limit, take_profit, stop_loss, orders):
    """Handles complex logic for modifying a Pending Buy (Replace vs Resubmit)."""
    logs = []
    current_limit = float(parent_buy.limit_price)
    
    # 1. Check if Buy Price Changed
    if buy_limit > 0 and abs(current_limit - float(buy_limit)) >= 0.01:
        try:
            # Attempt Polite Replace
            trading_client.replace_order_by_id(parent_buy.id, ReplaceOrderRequest(limit_price=float(buy_limit)))
            print(f"   ✅ Pending BUY Updated: {current_limit} -> {buy_limit}")
            logs.append({"event": "UPDATE_BUY", "price": buy_limit, "info": f"Old: {current_limit}"})
            
            # If successful, we still need to update legs
            logs.extend(_update_legs(orders, take_profit, stop_loss))
            
        except Exception as e:
            # Nuclear Resubmit (Catch 422 Errors)
            if "422" in str(e) or "cannot replace" in str(e).lower():
                print(f"   ⚠️ Replace Rejected. Executing Nuclear Resubmit...")
                try:
                    # Scrape Old Values if New ones missing
                    qty = float(parent_buy.qty)
                    old_tp = next((o.limit_price for o in orders if o.side == OrderSide.SELL and o.type == OrderType.LIMIT), 0)
                    old_sl = next((o.stop_price for o in orders if o.side == OrderSide.SELL and o.type in [OrderType.STOP, OrderType.STOP_LIMIT]), 0)

                    final_tp = float(take_profit) if take_profit > 0 else float(old_tp)
                    final_sl = float(stop_loss) if stop_loss > 0 else float(old_sl)
                    
                    if final_tp <= 0 or final_sl <= 0: raise ValueError("Missing TP/SL for Resubmit")
                    
                    trading_client.cancel_order_by_id(parent_buy.id)
                    time.sleep(1)
                    
                    new_order = LimitOrderRequest(
                        symbol=ticker, qty=int(qty), side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
                        limit_price=float(buy_limit), order_class=OrderClass.BRACKET,
                        take_profit=TakeProfitRequest(limit_price=final_tp),
                        stop_loss=StopLossRequest(stop_price=final_sl)
                    )
                    trade = trading_client.submit_order(new_order)
                    print(f"   ✅ Resubmit Successful. ID: {trade.id}")
                    logs.append({"event": "RESUBMIT_BUY", "price": buy_limit, "order_id": str(trade.id)})
                    # NOTE: We return here because legs are freshly created
                    return logs
                except Exception as ex:
                    logs.append({"event": "ERROR", "info": f"Resubmit Fail: {ex}"})
            else:
                logs.append({"event": "ERROR", "info": f"Buy Update Fail: {e}"})
    else:
        # Buy Limit Unchanged -> Just update legs
        print(f"   ✋ Pending Buy aligned. Checking legs...")
        logs.extend(_update_legs(orders, take_profit, stop_loss))

    return logs

def _handle_active_update(ticker, take_profit, stop_loss, orders):
    """Handles Active Positions (Rescue + Leg Updates)."""
    logs = []
    
    # Check if legs exist
    has_tp = any(o.side == OrderSide.SELL and o.type == OrderType.LIMIT for o in orders)
    has_sl = any(o.side == OrderSide.SELL and o.type in [OrderType.STOP, OrderType.STOP_LIMIT] for o in orders)
    
    # Rescue Logic (Position Exists, No Bracket)
    if not has_tp and not has_sl:
        qty = get_position(ticker)
        if qty > 0:
            print(f"   ⚠️ Active Position ({qty}) missing bracket. Rescuing...")
            if take_profit <= 0 or stop_loss <= 0: return [{"event": "ERROR", "info": "Rescue Failed: Missing TP/SL"}]
            
            if orders: trading_client.cancel_orders(symbols=[ticker])
            try:
                oco_data = LimitOrderRequest(
                    symbol=ticker, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
                    limit_price=take_profit, order_class=OrderClass.OCO,
                    take_profit=TakeProfitRequest(limit_price=take_profit),
                    stop_loss=StopLossRequest(stop_price=stop_loss)
                )
                trade = trading_client.submit_order(oco_data)
                print(f"   ✅ Rescue Successful. ID: {trade.id}")
                return [{"event": "RESCUE_OCO", "info": "Bracket Created"}]
            except Exception as e: return [{"event": "ERROR", "info": f"Rescue Error: {e}"}]

    # Standard Update
    return _update_legs(orders, take_profit, stop_loss)

# ==========================================================
#  MAIN EXECUTOR (THE CONTROLLER)
# ==========================================================
def execute_update(ticker, take_profit, stop_loss, buy_limit=0):
    ticker = normalize_ticker(ticker)
    print(f"♻️ TRADER: Executing UPDATE_EXISTING for {ticker}...")
    
    try:
        # 1. Fetch & Filter Orders
        req_filter = GetOrdersRequest(status=QueryOrderStatus.ALL, symbols=[ticker], limit=50)
        all_orders = trading_client.get_orders(filter=req_filter)
        live_statuses = ['new', 'partially_filled', 'accepted', 'pending_new', 'pending_replace', 'held']
        orders = [o for o in all_orders if (o.status.value if hasattr(o.status, 'value') else str(o.status)) in live_statuses]
        
        # 2. Identify State
        parent_buy = next((o for o in orders if o.side == OrderSide.BUY), None)
        
        # 3. Route to Handler
        if parent_buy:
            return _enforce_contract(_handle_pending_update(ticker, parent_buy, buy_limit, take_profit, stop_loss, orders))
        else:
            return _enforce_contract(_handle_active_update(ticker, take_profit, stop_loss, orders))

    except Exception as e:
        print(f"❌ Update Failed: {e}")
        return _enforce_contract({"event": "ERROR", "info": str(e)})

# ==========================================================
#  COMMAND 1: ENTRY
# ==========================================================
def execute_entry(ticker, investment_amount, buy_limit, take_profit, stop_loss):
    ticker = normalize_ticker(ticker)
    print(f"⚡ TRADER: Checking OPEN_NEW for {ticker}...")
    if get_position(ticker) > 0: return _enforce_contract({"event": "HOLD", "info": "Already Owned"})
    
    # Duplicate Check
    req_filter = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
    if any(o.side == OrderSide.BUY for o in trading_client.get_orders(filter=req_filter)):
         return _enforce_contract({"event": "HOLD", "info": "Pending Buy Exists"})

    qty = int(investment_amount / buy_limit)
    if qty < 1: return _enforce_contract({"event": "ERROR", "info": "Qty < 1"})

    try:
        order_data = LimitOrderRequest(
            symbol=ticker, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
            limit_price=buy_limit, order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=take_profit),
            stop_loss=StopLossRequest(stop_price=stop_loss)
        )
        trade = trading_client.submit_order(order_data)
        print(f"   ✅ Buy Order Placed. ID: {trade.id}")
        return _enforce_contract({"event": "NEW_ENTRY", "order_id": str(trade.id), "qty": qty})
    except Exception as e: return _enforce_contract({"event": "ERROR", "info": str(e)})