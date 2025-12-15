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
    # 1. AUDIT
    tp_order = next((o for o in orders if o.side == OrderSide.SELL and o.type == OrderType.LIMIT), None)
    sl_order = next((o for o in orders if o.side == OrderSide.SELL and o.type in [OrderType.STOP, OrderType.STOP_LIMIT]), None)

    curr_tp = float(tp_order.limit_price) if tp_order else 0.0
    curr_sl = float(sl_order.stop_price) if sl_order and sl_order.stop_price else (float(sl_order.limit_price) if sl_order else 0.0)

    log(f"🔍 AUDIT {ticker}: Current(TP={curr_tp}, SL={curr_sl}) ➡️ Target(TP={take_profit}, SL={stop_loss})")

    # 2. MISSING LEGS CHECK
    if not tp_order and not sl_order:
        log(f"⚠️ No active brackets found for {ticker}. Generating protection...")
        return _nuclear_regenerate(client, ticker, qty, take_profit, stop_loss)

    # 3. PLAN A: POLITE UPDATE
    tp_ok = _try_update(client, tp_order, take_profit, "TP") if take_profit > 0 else True
    sl_ok = _try_update(client, sl_order, stop_loss, "SL") if stop_loss > 0 else True

    # 4. PLAN B: NUCLEAR FALLBACK
    if not tp_ok or not sl_ok:
        log("⚠️ Polite update failed (or stuck). Switching to Nuclear Regeneration.")
        return _nuclear_regenerate(client, ticker, qty, take_profit, stop_loss)
        
    return [{"event": "UPDATE_LEGS", "info": "Polite Update Success"}]

def _try_update(client, order, new_price, label):
    if not order: return False
    current = float(order.stop_price) if order.stop_price else float(order.limit_price)
    
    if abs(current - float(new_price)) < 0.01: return True 
    
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
    STRICT SEQUENTIAL LOGIC: Cancel -> Verify Gone -> Verify Unlocked -> Resubmit.
    """
    log(f"☢️ NUCLEAR REGENERATE: Resetting TP/SL for {ticker}...")
    
    # --- PHASE 1: AGGRESSIVE CANCELLATION ---
    # We loop to ensure we send the signal, but we don't assume success yet.
    for attempt in range(3):
        try:
            req_filter = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
            orders_to_cancel = client.get_orders(filter=req_filter)
            
            if not orders_to_cancel:
                break # Nothing to cancel, proceed to verification
            
            log(f"   🗑️ Cancel Attempt {attempt+1}: Targeting {len(orders_to_cancel)} orders...")
            for o in orders_to_cancel:
                try:
                    client.cancel_order_by_id(o.id)
                except Exception as c_err:
                    # Ignore "Pending" errors, it just means it's already dying
                    pass 
            time.sleep(1)
        except Exception as e:
            log(f"   ⚠️ Cancel Loop Error: {e}")

    # --- PHASE 2: STRICT DEATH VERIFICATION ---
    # We DO NOT proceed until get_orders returns empty.
    verified_gone = False
    for i in range(10): # Wait up to 10s
        open_orders = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker]))
        if not open_orders:
            verified_gone = True
            break
        log(f"   ⏳ Waiting for orders to disappear (Attempt {i+1}/10)...")
        time.sleep(1)

    if not verified_gone:
        log("❌ ABORT: Orders refused to die. Cannot resubmit safely.")
        return [{"event": "ERROR", "info": "Stuck Orders"}]

    # --- PHASE 3: STRICT WALLET VERIFICATION ---
    # We DO NOT proceed until qty_available matches our holding.
    verified_unlocked = False
    for i in range(5):
        try:
            pos = client.get_open_position(ticker)
            available = float(pos.qty_available) if hasattr(pos, 'qty_available') else float(pos.qty)
            # If available is close to qty (floating point safety), we are good
            if abs(available - qty) < 0.01:
                verified_unlocked = True
                break
            log(f"   ⏳ Waiting for shares to unlock: {available}/{qty} (Attempt {i+1}/5)...")
            time.sleep(1)
        except:
            time.sleep(1)

    # Note: If verify_unlocked is False, we might still try if Phase 2 passed, 
    # but it's risky. Let's block it to be safe.
    if not verified_unlocked:
        log("❌ ABORT: Shares still showing as locked in wallet.")
        return [{"event": "ERROR", "info": "Wallet Locked"}]

    # --- PHASE 4: RESUBMIT ---
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