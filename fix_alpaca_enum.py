import os
import sys

print("🔧 APPLYING FINAL ALPACA ENUM FIX...")

# THE CORRECT CODE (Imports QueryOrderStatus)
CORRECT_CODE = r'''print("--- TRADER LOADED: VERSION 10.0 (QUERY_STATUS FIX) ---")
import config
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    LimitOrderRequest, 
    TakeProfitRequest, 
    StopLossRequest, 
    ReplaceOrderRequest,
    GetOrdersRequest
)
# CRITICAL FIX: Import QueryOrderStatus for filtering
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus
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

def place_smart_trade(ticker, investment_amount, buy_limit, take_profit, stop_loss):
    ticker = normalize_ticker(ticker)
    print(f"--- TRADER: Placing NEW Order for {ticker} ---")
    
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
        time_in_force=TimeInForce.DAY,
        limit_price=buy_limit,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=take_profit),
        stop_loss=StopLossRequest(stop_price=stop_loss)
    )

    try:
        trade = trading_client.submit_order(order_data)
        print(f"   ✅ Order Placed. ID: {trade.id}")
        return _enforce_contract(trade, context=f"place_smart_trade({ticker})")
    except Exception as e:
        print(f"   ❌ Order Failed: {e}")
        return _enforce_contract({"event": "ERROR", "info": str(e)})

def manage_smart_trade(ticker, invest_amt, buy_limit, take_profit, stop_loss):
    ticker = normalize_ticker(ticker)
    actions_log = []
    
    qty = get_position(ticker)
    
    if qty == 0:
        return place_smart_trade(ticker, invest_amt, buy_limit, take_profit, stop_loss)
    
    else:
        print(f"--- TRADER: Managing Position for {ticker} ---")
        try:
            # --- CRITICAL FIX: Use QueryOrderStatus.OPEN ---
            req_filter = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,  # <--- CHANGED THIS
                symbols=[ticker]
            )
            orders = trading_client.get_orders(filter=req_filter)
            
            tp_order = next((o for o in orders if o.type == 'limit' and o.side == 'sell'), None)
            sl_order = next((o for o in orders if o.type == 'stop' and o.side == 'sell'), None)
            
            # Update TP
            if tp_order:
                current_limit = float(tp_order.limit_price)
                new_limit = float(take_profit)
                if abs(current_limit - new_limit) > (new_limit * 0.01):
                    try:
                        req = ReplaceOrderRequest(limit_price=new_limit)
                        trading_client.replace_order(tp_order.id, req)
                        print(f"   ♻️ TP Updated: ${new_limit}")
                        actions_log.append({"event": "UPDATE_TP", "info": f"Old: {current_limit}"})
                    except Exception as e:
                        actions_log.append({"event": "ERROR", "info": f"TP Fail: {e}"})

            # Update SL
            if sl_order:
                current_stop = float(sl_order.stop_price)
                new_stop = float(stop_loss)
                if abs(current_stop - new_stop) > (new_stop * 0.01):
                    try:
                        req = ReplaceOrderRequest(stop_price=new_stop)
                        trading_client.replace_order(sl_order.id, req)
                        print(f"   ♻️ SL Updated: ${new_stop}")
                        actions_log.append({"event": "UPDATE_SL", "info": f"Old: {current_stop}"})
                    except Exception as e:
                        actions_log.append({"event": "ERROR", "info": f"SL Fail: {e}"})
                
            if not actions_log:
                print("   > Orders aligned. No changes.")
                return _enforce_contract({"event": "HOLD", "info": "Orders Aligned"})
                
            return _enforce_contract(actions_log)

        except Exception as e:
            print(f"❌ TRADER ERROR updating {ticker}: {e}")
            return _enforce_contract({"event": "ERROR", "info": str(e)})
'''

# Overwrite the file
try:
    with open(os.path.join("lib", "gvqm_alpaca_trader.py"), "w") as f:
        f.write(CORRECT_CODE)
    print("✅ Trader File Repaired (Version 10.0).")
    print("👉 Please RESTART 'routes.py' now.")
except Exception as e:
    print(f"❌ Error: {e}")