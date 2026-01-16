import time
import datetime
from alpaca.trading.requests import LimitOrderRequest, TakeProfitRequest, StopLossRequest, ReplaceOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, OrderType, QueryOrderStatus

def log(message):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [PENDING_MGR] {message}")

# --- NEW: EXPLICIT KILL SWITCH ---
def kill_order(client, ticker):
    """
    Explicitly finds and cancels any open orders for this ticker.
    Used when action is 'CANCEL_PENDING'.
    """
    log(f"💀 KILL COMMAND received for {ticker}.")
    try:
        # 1. Find the orders
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
        orders = client.get_orders(filter=req)
        
        if not orders:
            return [{"event": "HOLD", "info": "No Orders to Cancel"}]

        # 2. Cancel them
        cancel_ids = []
        for o in orders:
            client.cancel_order_by_id(o.id)
            cancel_ids.append(str(o.id))
        
        time.sleep(2) # Wait for Alpaca to process
        return [{"event": "CANCEL_PENDING", "info": f"Killed {len(cancel_ids)} orders"}]

    except Exception as e:
        log(f"❌ Kill Failed: {e}")
        return [{"event": "ERROR", "info": str(e)}]

def manage_pending_order(client, ticker, parent_buy, buy_limit, take_profit, stop_loss, orders):
    """
    Main Entry Point for Pending Orders.
    Logic: If ANY parameter (Limit, TP, SL) changes, we must RESUBMIT the whole bracket
    to keep the prices aligned. Polite updates are too risky for brackets.
    """
    current_limit = float(parent_buy.limit_price)
    
    # 1. Check if Buy Limit Changed
    limit_changed = buy_limit > 0 and abs(current_limit - float(buy_limit)) >= 0.01

    # 2. Check if Legs Changed (Need to scrape old leg prices first)
    # Note: 'orders' contains 'held' legs if we passed status='all' to get_orders
    old_tp_order = next((o for o in orders if o.side == OrderSide.SELL and o.type == OrderType.LIMIT), None)
    old_sl_order = next((o for o in orders if o.side == OrderSide.SELL and o.type in [OrderType.STOP, OrderType.STOP_LIMIT]), None)

    old_tp = float(old_tp_order.limit_price) if old_tp_order else 0.0
    old_sl = float(old_sl_order.stop_price) if old_sl_order and old_sl_order.stop_price else (float(old_sl_order.limit_price) if old_sl_order else 0.0)

    tp_changed = take_profit > 0 and abs(old_tp - float(take_profit)) >= 0.01
    sl_changed = stop_loss > 0 and abs(old_sl - float(stop_loss)) >= 0.01

    # 3. Decision Logic
    if limit_changed or tp_changed or sl_changed:
        log(f"⚠️ Bracket Mismatch Detected (Limit: {limit_changed}, TP: {tp_changed}, SL: {sl_changed}). Executing NUCLEAR RESUBMIT.")
        # We skip 'Polite Update' entirely because syncing 3 separate orders is brittle.
        # Nuke it and build a fresh, perfect bracket.
        return _nuclear_resubmit(client, ticker, parent_buy, buy_limit, take_profit, stop_loss, orders)

    return [{"event": "HOLD_PENDING", "info": "Bracket is aligned"}]
	   

														   

def _nuclear_resubmit(client, ticker, parent_buy, buy_limit, take_profit, stop_loss, orders):
    """
    PLAN B: Cancel Old -> Submit New Bracket.
    """
    try:
        # 1. Scrape Old Values
        qty = float(parent_buy.qty)
        current_limit = float(parent_buy.limit_price)
        
        old_tp = next((o.limit_price for o in orders if o.side == OrderSide.SELL and o.type == OrderType.LIMIT), None)
        old_sl = next((o.stop_price for o in orders if o.side == OrderSide.SELL and o.type in [OrderType.STOP, OrderType.STOP_LIMIT]), None)
        
        # 2. Determine Final Values
        final_limit = buy_limit if buy_limit > 0 else current_limit
        final_tp = take_profit if take_profit > 0 else (float(old_tp) if old_tp else 0)
        final_sl = stop_loss if stop_loss > 0 else (float(old_sl) if old_sl else 0)

        # 3. Kill the Old Order
        log(f"☢️ Canceling pending order for {ticker}...")
        client.cancel_order_by_id(parent_buy.id)
        time.sleep(2) 

        # 4. Validate Safety
        if final_tp <= 0 or final_sl <= 0:
            return [{"event": "ERROR", "info": "Resubmit Failed: Missing TP/SL"}]
        
        # 5. Submit New Bracket
        log(f"🔨 Resubmitting Bracket: Buy {final_limit} | TP {final_tp} | SL {final_sl}")
        new_order = LimitOrderRequest(
            symbol=ticker, qty=int(qty), side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
            limit_price=float(final_limit), order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=final_tp),
            stop_loss=StopLossRequest(stop_price=final_sl)
        )
        trade = client.submit_order(new_order)
        return [{"event": "RESUBMIT_PENDING", "order_id": str(trade.id)}]

    except Exception as ex:
        log(f"❌ Nuclear Resubmit Failed: {ex}")
        return [{"event": "ERROR", "info": f"Resubmit Fail: {ex}"}]