import config
import datetime
import time
    
import pandas as pd 
  
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, TakeProfitRequest, StopLossRequest, GetOrdersRequest, MarketOrderRequest
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
        if abs(target - actual) < 0.02: return "✅" # Match (2 cent tolerance)
        return "⚠️" # Mismatch (Broker has different number)

    # --- 1. COLUMN: CURRENT STATE (Before) ---
    cur_lines = []
    if initial_state['shares'] > 0: 
        cur_lines.append(f"Held:   {initial_state['shares']} @ ${initial_state['avg_entry']:.2f}")
    else: 
        cur_lines.append("Held:   0 sh")
        
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
    elif request_data.get('action') == "CANCEL": req_lines.append("ACTION: CANCEL")
    else: req_lines.append("Set Buy: (Hold/Mkt)")
    
    req_lines.append(f"Set TP:  ${request_data['tp']:.2f}")
    req_lines.append(f"Set SL:  ${request_data['sl']:.2f}")

    # --- 3. COLUMN: UPDATED STATE (Broker) ---
    res_lines = []
    evt = exec_result[0].get("event", "UNKNOWN") if exec_result else "UNKNOWN"
    
    if evt in ["ERROR", "HOLD", "CANCEL_PENDING"]:
        res_lines.append(f"Status: {evt}")
        res_lines.append(f"Info:   {exec_result[0].get('info', '')[:25]}")
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
    if getattr(config, 'DEBUG_MODE', False):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [TRADER_MAIN] {message}")

def _enforce_contract(data):
    if hasattr(data, 'id'): return [{"event": "NEW_ENTRY", "order_id": str(data.id)}]
    if isinstance(data, list): return data if data else []
    return [{"event": "ERROR", "info": str(data)}]

   
def _inject_log_params(result_list, qty, buy, tp, sl):
    """Common helper to inject trade parameters into result objects for logging."""
    for item in result_list:
        item['qty'] = qty
        item['buy_limit'] = buy
        item['take_profit'] = tp
        item['stop_loss'] = sl

def normalize_ticker(ticker): 
    """Converts 'BF-B' to 'BF.B' for Alpaca API compatibility."""
    return ticker.replace('-', '.') if ticker else ticker
  

# ==========================================================
#  ⚡ BULK DATA FETCHER (Optimization)
# ==========================================================
def get_bulk_market_data(tickers, lookback=14):
    """
    Fetches History (for ATR) and Current Prices for ALL tickers in 2 API calls.
    """
    price_map = {}
    atr_map = {}
    
    if not tickers: return {}, {}

    ticker_map = { t.replace('-', '.'): t for t in tickers }
    alpaca_tickers = list(ticker_map.keys())

    try:
        latest_trades_req = StockLatestTradeRequest(symbol_or_symbols=alpaca_tickers)
        latest_trades = data_client.get_stock_latest_trade(latest_trades_req)
        
        for alpaca_ticker, trade in latest_trades.items():
            original_ticker = ticker_map.get(alpaca_ticker, alpaca_ticker)
            price_map[original_ticker] = round(trade.price, 2)
            
    except Exception as e:
        print(f"[TRADER] ⚠️ Bulk Price Fetch Warning: {e}")

    try:
        start_dt = datetime.datetime.now() - datetime.timedelta(days=45)
        
        bars_request = StockBarsRequest(
            symbol_or_symbols=alpaca_tickers,
            timeframe=TimeFrame.Day,
            start=start_dt,
            limit=None
        )
        bars_df = data_client.get_stock_bars(bars_request).df

        if not bars_df.empty:
            if 'symbol' in bars_df.index.names:
                for alpaca_ticker, group in bars_df.groupby(level='symbol'):
                    original_ticker = ticker_map.get(alpaca_ticker, alpaca_ticker)
                    
                    try:
                        if len(group) < lookback:
                            atr_map[original_ticker] = 0.0
                            continue

                        df = group.copy()
                        df = df.sort_index()
                        
                        df['h-l'] = df['high'] - df['low']
                        df['h-pc'] = (df['high'] - df['close'].shift(1)).abs()
                        df['l-pc'] = (df['low'] - df['close'].shift(1)).abs()
                        df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
                        
                        atr = df['tr'].rolling(window=lookback).mean().iloc[-1]
                        
                        if pd.isna(atr):
                            atr_map[original_ticker] = 0.0
                        else:
                            atr_map[original_ticker] = round(float(atr), 2)

                    except Exception as calc_err:
                        print(f"[TRADER] ⚠️ ATR Calc Failed for {original_ticker}: {calc_err}")
                        atr_map[original_ticker] = 0.0
                        
    except Exception as e:
        print(f"[TRADER] ⚠️ Bulk History/ATR Fetch Warning: {e}")

    return price_map, atr_map

# ==========================================================
#  INDIVIDUAL HELPERS
# ==========================================================

def get_current_price(ticker):
    ticker = normalize_ticker(ticker)
    try:
        req = StockLatestTradeRequest(symbol_or_symbols=ticker)
        return float(data_client.get_stock_latest_trade(req)[ticker].price)
    except: return None

def get_position_details(ticker):
    snap = _fetch_snapshot(ticker)
    details = {
        "shares_held": snap["shares"], 
        "avg_entry_price": snap["avg_entry"], 
        "pending_buy_limit": snap["pending_buy"],
        "active_tp": snap["tp"] if snap["tp"] > 0 else None,
        "active_sl": snap["sl"] if snap["sl"] > 0 else None,
        "status_msg": "NONE", "manual_override": snap["manual"]
    }
    return details

def _fetch_snapshot(ticker):
    alpaca_ticker = normalize_ticker(ticker)
    state = {"shares": 0.0, "avg_entry": 0.0, "pending_buy": None, "tp": 0.0, "sl": 0.0, "manual": False}
    try:
        try:
            pos = trading_client.get_open_position(alpaca_ticker)
            state["shares"] = float(pos.qty)
            state["avg_entry"] = float(pos.avg_entry_price)
        except: pass

        req = GetOrdersRequest(status=QueryOrderStatus.ALL, symbols=[alpaca_ticker], limit=500)
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
    except: return state

# ==========================================================
#  MAIN ENTRY POINTS
# ==========================================================

def execute_update(ticker, take_profit, stop_loss, buy_limit=0):
    """
    Main Logic for updating stops with Anti-Spam Firewall.
    """
    alpaca_ticker = normalize_ticker(ticker)
    req_data = {"limit": buy_limit, "tp": take_profit, "sl": stop_loss}
    
    initial_state = _fetch_snapshot(ticker)
    if initial_state["manual"]:
        res = _enforce_contract({"event": "HOLD", "info": "User Manual Override"})
        log_execution_matrix(ticker, "UPDATE", initial_state, req_data, initial_state, res)
        return res

    # --- 🛡️ ANTI-SPAM TOLERANCE CHECK ---
    curr_tp = initial_state['tp'] or 0.0
    curr_sl = initial_state['sl'] or 0.0
    curr_buy = initial_state['pending_buy'] or 0.0
    
    # Check if the change is less than $2.00 (to avoid micro-adjustments that could trigger broker rejections or fees)
    tp_diff = abs(curr_tp - take_profit)
    sl_diff = abs(curr_sl - stop_loss)
    buy_diff = abs(curr_buy - buy_limit)

    if tp_diff < 2.00 and sl_diff < 2.00 and buy_diff < 2.00:
        res = _enforce_contract({"event": "HOLD", "info": "STOPS UNCHANGED (Tolerance)"})
        log_execution_matrix(ticker, "UPDATE", initial_state, req_data, initial_state, res)
        return res

    try:
        req_filter = GetOrdersRequest(status=QueryOrderStatus.ALL, symbols=[alpaca_ticker], limit=500)
        all_orders = trading_client.get_orders(filter=req_filter)
        live_statuses = ['new', 'partially_filled', 'accepted', 'pending_new', 'pending_replace', 'held']
        orders = [o for o in all_orders if (o.status.value if hasattr(o.status, 'value') else str(o.status)) in live_statuses]

        buy = next((o for o in orders if o.side == OrderSide.BUY), None)
        if buy:
            res = pending_mgr.manage_pending_order(trading_client, alpaca_ticker, buy, buy_limit, take_profit, stop_loss, orders)
        else:
            if initial_state["shares"] > 0:
                res = filled_mgr.manage_active_position(trading_client, alpaca_ticker, initial_state["shares"], take_profit, stop_loss, orders)
            else:
                res = [{"event": "HOLD", "info": "Nothing to update"}]
        
        final_res = _enforce_contract(res)
        log_qty = initial_state['shares']
        if log_qty == 0 and buy and hasattr(buy, 'qty'):
            log_qty = float(buy.qty)
            
        _inject_log_params(final_res, log_qty, buy_limit, take_profit, stop_loss)

        for item in final_res:
            if item.get('event') not in ['ERROR', 'HOLD']:
                deltas = []
                if initial_state['tp'] > 0 and abs(initial_state['tp'] - take_profit) > 0.01:
                    deltas.append(f"TP: {initial_state['tp']}->{take_profit}")
                if initial_state['sl'] > 0 and abs(initial_state['sl'] - stop_loss) > 0.01:
                    deltas.append(f"SL: {initial_state['sl']}->{stop_loss}")
                if deltas:
                    item['info'] = f"{item.get('info','')} | {', '.join(deltas)}"

    except Exception as e:
        final_res = _enforce_contract({"event": "ERROR", "info": str(e)})

    if final_res[0].get("event") not in ["ERROR", "HOLD"]:
        time.sleep(2) 
    
    final_state = _fetch_snapshot(ticker)
    log_execution_matrix(ticker, "UPDATE", initial_state, req_data, final_state, final_res)
    return final_res

def execute_entry(ticker, investment_amount, buy_limit, take_profit, stop_loss):
    alpaca_ticker = normalize_ticker(ticker)
    req_data = {"limit": buy_limit, "tp": take_profit, "sl": stop_loss, "amt": investment_amount}
    initial_state = _fetch_snapshot(ticker)
    
    if initial_state["shares"] > 0 or initial_state["pending_buy"]:
        res = _enforce_contract({"event": "HOLD", "info": "Already Owned/Pending"})
        log_execution_matrix(ticker, "ENTRY", initial_state, req_data, initial_state, res)
        return res

    if buy_limit <= 0: return _enforce_contract({"event": "ERROR", "info": "Invalid Price"})
    qty = int(investment_amount / buy_limit)
    if qty < 1: return _enforce_contract({"event": "ERROR", "info": "Qty < 1"})
      
    try:
        order = LimitOrderRequest(
            symbol=alpaca_ticker, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
            limit_price=buy_limit, order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=take_profit),
            stop_loss=StopLossRequest(stop_price=stop_loss)
        )
        trade = trading_client.submit_order(order)
        final_res = _enforce_contract(trade)
        _inject_log_params(final_res, qty, buy_limit, take_profit, stop_loss)
        for item in final_res: item['info'] = f"New Entry | Limit: {buy_limit}"
    except Exception as e:
        final_res = _enforce_contract({"event": "ERROR", "info": str(e)})

    time.sleep(2) 
    final_state = _fetch_snapshot(ticker)
    log_execution_matrix(ticker, "ENTRY", initial_state, req_data, final_state, final_res)
    return final_res

def is_market_open():
    try:
        clock = trading_client.get_clock()
        return clock.is_open
    except: return False
    
def close_full_position(ticker):
    try:
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
        open_orders = trading_client.get_orders(filter=req)
        for order in open_orders: client.cancel_order_by_id(order.id)
        
        pos = trading_client.get_open_position(ticker)
        qty = float(pos.qty)
        market_order = MarketOrderRequest(
            symbol=ticker, qty=abs(qty), side=OrderSide.SELL, time_in_force=TimeInForce.DAY
        )
        trading_client.submit_order(market_order)
    except: pass

# --- ACCOUNT UTILS ---
def get_account():
    try: return trading_client.get_account()
    except: return None

def get_portfolio():
    try: return trading_client.get_all_positions()
    except: return []