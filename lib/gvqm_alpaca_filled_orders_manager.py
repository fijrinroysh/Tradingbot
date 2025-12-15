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
    Tries Polite Update -> Falls back to Nuclear Regeneration.
    """
    tp_order = next((o for o in orders if o.side == OrderSide.SELL and o.type == OrderType.LIMIT), None)
    sl_order = next((o for o in orders if o.side == OrderSide.SELL and o.type in [OrderType.STOP, OrderType.STOP_LIMIT]), None)

    # 0. If brackets are missing entirely, regenerate immediately
    if not tp_order and not sl_order:
        log(f"⚠️ No active brackets found for {ticker}. Generating protection...")
        return _nuclear_regenerate(client, ticker, qty, take_profit, stop_loss)

    # 1. PLAN A: POLITE UPDATE
    tp_ok = _try_update(client, tp_order, take_profit, "TP") if take_profit > 0 else True
    sl_ok = _try_update(client, sl_order, stop_loss, "SL") if stop_loss > 0 else True

    # 2. PLAN B: NUCLEAR FALLBACK
    if not tp_ok or not sl_ok:
        log("⚠️ Polite update failed (or stuck). Switching to Nuclear Regeneration.")
        return _nuclear_regenerate(client, ticker, qty, take_profit, stop_loss)
        
    return [{"event": "UPDATE_LEGS", "info": "Polite Update Success"}]

def _try_update(client, order, new_price, label):
    """Helper to attempt a polite replace."""
    if not order: return False
    current = float(order.stop_price) if order.stop_price else float(order.limit_price)
    
    if abs(current - float(new_price)) < 0.01: return True # Already matches
    
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
    FIX: Manually fetches and cancels specific orders instead of using unsupported 'symbols' arg.
    """
    log(f"☢️ NUCLEAR REGENERATE: Resetting TP/SL for {ticker}...")
    try:
        # --- FIX START: Correct Cancellation Logic ---
        # 1. Fetch only open orders for this specific ticker
        req_filter = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
        orders_to_cancel = client.get_orders(filter=req_filter)
        
        if not orders_to_cancel:
            log(f"   ℹ️ No open orders found to cancel for {ticker}.")
        else:
            log(f"   🗑️ Cancelling {len(orders_to_cancel)} open orders for {ticker}...")
            for o in orders_to_cancel:
                try:
                    client.cancel_order_by_id(o.id)
                except Exception as c_err:
                    log(f"      ⚠️ Failed to cancel order {o.id}: {c_err}")
            
            time.sleep(2) # Wait for cancellation to settle
        # --- FIX END ---
        
        if take_profit <= 0 or stop_loss <= 0:
            log("❌ Cannot regenerate: Missing TP or SL params.")
            return [{"event": "ERROR", "info": "Missing Params"}]

        # 2. Submit New OCO Bracket
        oco_data = LimitOrderRequest(
            symbol=ticker, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
            limit_price=take_profit, order_class=OrderClass.OCO,
            take_profit=TakeProfitRequest(limit_price=take_profit),
            stop_loss=StopLossRequest(stop_price=stop_loss)
        )
        trade = client.submit_order(oco_data)
        log(f"✅ Regenerated OCO Bracket. ID: {trade.id}")
        return [{"event": "REGENERATE_LEGS", "info": "Success"}]

    except Exception as e:
        log(f"❌ Regeneration Failed: {e}")
        return [{"event": "ERROR", "info": str(e)}]