import time
import datetime
from alpaca.trading.requests import (
    LimitOrderRequest, 
    TakeProfitRequest, 
    StopLossRequest, 
    ReplaceOrderRequest,
    GetOrdersRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, OrderType, QueryOrderStatus

def log(message):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [FILLED_MGR] {message}")

def manage_active_position(client, ticker, qty, take_profit, stop_loss, orders):
    """
    Main Entry Point for Filled Orders (Active Positions).
    """
    # 1. EXTRACT CURRENT VALUES (For Logging)
    tp_order = next((o for o in orders if o.side == OrderSide.SELL and o.type == OrderType.LIMIT), None)
    sl_order = next((o for o in orders if o.side == OrderSide.SELL and o.type in [OrderType.STOP, OrderType.STOP_LIMIT]), None)

    curr_tp = float(tp_order.limit_price) if tp_order else 0.0
    curr_sl = float(sl_order.stop_price) if sl_order and sl_order.stop_price else (float(sl_order.limit_price) if sl_order else 0.0)

    # 2. LOG THE AUDIT COMPARISON (The Visibility You Requested)
    log(f"🔍 AUDIT {ticker}: Current(TP={curr_tp}, SL={curr_sl}) ➡️ Target(TP={take_profit}, SL={stop_loss})")

    # 3. DECISION LOGIC
    # If brackets are missing entirely, regenerate immediately
    if not tp_order and not sl_order:
        log(f"⚠️ No active brackets found for {ticker}. Generating protection...")
        return _nuclear_regenerate(client, ticker, qty, take_profit, stop_loss)

    # PLAN A: POLITE UPDATE
    # The helper _try_update will log the specific "Value A -> Value B" change
    tp_ok = _try_update(client, tp_order, take_profit, "TP") if take_profit > 0 else True
    sl_ok = _try_update(client, sl_order, stop_loss, "SL") if stop_loss > 0 else True

    # PLAN B: NUCLEAR FALLBACK
    if not tp_ok or not sl_ok:
        log("⚠️ Polite update failed (or stuck). Switching to Nuclear Regeneration.")
        return _nuclear_regenerate(client, ticker, qty, take_profit, stop_loss)
        
    return [{"event": "UPDATE_LEGS", "info": "Polite Update Success"}]

def _try_update(client, order, new_price, label):
    """Helper to attempt a polite replace."""
    if not order: return False
    current = float(order.stop_price) if order.stop_price else float(order.limit_price)
    
    # Check if update is actually needed (Ignore tiny floating point diffs)
    if abs(current - float(new_price)) < 0.01: 
        return True 
    
    try:
        log(f"👉 Updating {label}: {current} -> {new_price}")
        if label == "TP": req = ReplaceOrderRequest(limit_price=float(new_price))
        else: req = ReplaceOrderRequest(stop_price=float(new_price))
        
        client.replace_order_by_id(order.id, req)
        return True
    except Exception as e:
        log(f"❌ {label} Update Failed ({e}).")
        return False

def _nuclear_regenerate(client, ticker, qty, take_profit, stop_loss):
    """
    Cancels existing exit orders and submits a fresh OCO bracket.
    Includes Race Condition Fixes (Retry Cancel + Wait for Unlock).
    """
    log(f"☢️ NUCLEAR REGENERATE: Resetting TP/SL for {ticker}...")
    
    # --- PHASE 1: ROBUST CANCELLATION ---
    max_cancel_retries = 3
    orders_cleared = False
    
    for attempt in range(max_cancel_retries):
        try:
            req_filter = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
            orders_to_cancel = client.get_orders(filter=req_filter)
            
            if not orders_to_cancel:
                orders_cleared = True
                break
            
            log(f"   🗑️ Attempt {attempt+1}/{max_cancel_retries}: Cancelling {len(orders_to_cancel)} orders...")
            
            for o in orders_to_cancel:
                try:
                    client.cancel_order_by_id(o.id)
                except Exception as c_err:
                    err_str = str(c_err).lower()
                    if "pending" in err_str or "42210000" in err_str:
                        log(f"      ⏳ Order {o.id} is locked in Pending state. Waiting...")
                    else:
                        log(f"      ⚠️ Cancel warning: {c_err}")
            
            time.sleep(2) 
            
        except Exception as e:
            log(f"   ❌ Critical Cancel Error: {e}")
            time.sleep(1)

    # --- PHASE 2: WAIT FOR UNLOCK ---
    if orders_cleared:
        unlocked = False
        for i in range(5): 
            try:
                open_orders = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker]))
                if not open_orders:
                    unlocked = True
                    break
                log(f"      ⏳ Waiting for orders to clear (Attempt {i+1}/5)...")
                time.sleep(2)
            except Exception as e:
                log(f"      ⚠️ Unlock check failed: {e}")
                time.sleep(1)
                
        if not unlocked:
            log("❌ Regeneration Aborted: Orders stuck in clearing state.")
            return [{"event": "ERROR", "info": "Shares Locked (Race Condition)"}]

    # --- PHASE 3: RESUBMIT ---
    if take_profit <= 0 or stop_loss <= 0:
        return [{"event": "ERROR", "info": "Missing TP/SL Params"}]

    try:
        oco_data = LimitOrderRequest(
            symbol=ticker, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
            limit_price=take_profit, order_class=OrderClass.OCO,
            take_profit=TakeProfitRequest(limit_price=take_profit),
            stop_loss=StopLossRequest(stop_price=stop_loss)
        )
        trade = client.submit_order(oco_data)
        log(f"✅ Regenerated OCO Bracket: TP {take_profit} | SL {stop_loss}")
        return [{"event": "REGENERATE_LEGS", "info": "Success"}]
    except Exception as e:
        log(f"❌ Resubmit Failed: {e}")
        return [{"event": "ERROR", "info": str(e)}]