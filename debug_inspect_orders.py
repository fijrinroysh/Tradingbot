import sys
import os
import json
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

# Setup
sys.path.append(os.getcwd())

print("🔍 INSPECTING RAW ORDERS FOR CRM")
print("="*60)

try:
    import config
    
    # 1. Connect
    client = TradingClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY, paper=True)
    
    # 2. Fetch ALL Open Orders for CRM (No other filters)
    # We use the raw request to ensure we get everything
    req = GetOrdersRequest(
        status=QueryOrderStatus.OPEN,
        symbols=["CRM"]
    )
    
    print("📡 Fetching orders from Alpaca...")
    orders = client.get_orders(filter=req)
    
    print(f"📊 Total Orders Found: {len(orders)}")
    
    if len(orders) == 0:
        print("❌ CRITICAL: Alpaca says you have ZERO open orders for CRM.")
        print("   This explains why the bot does nothing.")
        print("   -> Do you actually see open orders in your Alpaca Dashboard?")
    
    for i, o in enumerate(orders):
        print(f"\n--- ORDER #{i+1} ---")
        print(f"ID:     {o.id}")
        print(f"Type:   {o.type}")   # <--- Critical Check
        print(f"Side:   {o.side}")   # <--- Critical Check
        print(f"Limit:  {o.limit_price}")
        print(f"Stop:   {o.stop_price}")
        print(f"Class:  {o.order_class}")
        print(f"Legs:   {o.legs}")   # Check if this is a parent order with legs
        
        # Check if our logic would catch it
        is_limit_sell = (o.type == 'limit' and o.side == 'sell')
        is_stop_sell  = (o.type == 'stop' and o.side == 'sell')
        
        print(f"   -> Would match 'TP Logic'? {is_limit_sell}")
        print(f"   -> Would match 'SL Logic'? {is_stop_sell}")

except ImportError as e:
    print(f"❌ Import Error: {e}")
except Exception as e:
    print(f"❌ General Error: {e}")