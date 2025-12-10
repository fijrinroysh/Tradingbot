import sys
import os
import time
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import ReplaceOrderRequest, LimitOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest

# Force current directory to path
sys.path.append(os.getcwd())

print("🔍 DEBUG: CRM Update (Inline Logic Test)")
print("="*60)

try:
    # 1. Load Config
    import config
    
    # 2. Connect to Alpaca
    print("📡 Connecting to Alpaca...")
    client = TradingClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY, paper=True)
    data_client = StockHistoricalDataClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY)
    
    TICKER = "CRM"
    
    # 3. Get Current Price
    print(f"💲 Fetching price for {TICKER}...")
    req = StockLatestTradeRequest(symbol_or_symbols=TICKER)
    res = data_client.get_stock_latest_trade(req)
    price = float(res[TICKER].price)
    print(f"   Current Price: ${price}")

    # 4. Find or Create Open Order
    print(f"🔎 Checking for open orders...")
    orders = client.get_orders(filter={"status": "open", "symbols": [TICKER]})
    
    tp_order = next((o for o in orders if o.type == 'limit' and o.side == 'sell'), None)
    
    if not tp_order:
        print("   ❌ No Open TP Order found.")
        print("   🛠️ Placing a NEW Dummy Trade to test updates...")
        
        # Create a fresh Bracket Order
        limit_price = round(price * 0.98, 2)
        tp_price = round(price * 1.05, 2)
        sl_price = round(price * 0.95, 2)
        
        order_data = LimitOrderRequest(
            symbol=TICKER,
            qty=10,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=tp_price),
            stop_loss=StopLossRequest(stop_price=sl_price)
        )
        trade = client.submit_order(order_data)
        print(f"   ✅ Placed Dummy Order: {trade.id}")
        print("   ⏳ Waiting 5s for Alpaca to process...")
        time.sleep(5)
        
        # Fetch it again
        orders = client.get_orders(filter={"status": "open", "symbols": [TICKER]})
        tp_order = next((o for o in orders if o.type == 'limit' and o.side == 'sell'), None)
        
    if not tp_order:
        print("❌ CRITICAL: Could not find/create a TP order. Aborting.")
        sys.exit()
        
    print(f"   ✅ Found TP Order: {tp_order.id} (Price: {tp_order.limit_price})")

    # 5. ATTEMPT UPDATE (The Critical Test)
    # This uses the CORRECT 'ReplaceOrderRequest' Object syntax
    
    new_tp = round(float(tp_order.limit_price) * 1.02, 2) # Shift by 2%
    print(f"\n⚡ Attempting UPDATE to ${new_tp}...")
    
    try:
        # --- CORRECT SYNTAX ---
        req_object = ReplaceOrderRequest(limit_price=new_tp)
        print(f"   [DEBUG] Sending Object: {req_object}")
        
        client.replace_order(tp_order.id, req_object)
        print(f"   ✅ SUCCESS! Order updated to ${new_tp}")
        print("   🎉 CONCLUSION: The logic here works. Your 'lib' file is definitely outdated/broken.")
        
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        print("   🔍 CONCLUSION: Alpaca rejected the valid request. Check your account settings.")

except ImportError as e:
    print(f"❌ Setup Error: {e}")
except Exception as e:
    print(f"❌ Runtime Error: {e}")