import config
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

print("🔍 INSPECTING RAW ORDERS FOR HON...")

try:
    client = TradingClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY, paper=True)
    
    # Get ALL open orders for HON
    req = GetOrdersRequest(
        status=QueryOrderStatus.OPEN,
        symbols=["HON"]
    )
    orders = client.get_orders(filter=req)
    
    if not orders:
        print("❌ NO OPEN ORDERS FOUND FOR HON.")
    else:
        print(f"✅ Found {len(orders)} Orders:\n")
        for i, o in enumerate(orders):
            print(f"--- ORDER {i+1} ---")
            print(f"ID: {o.id}")
            print(f"Type: {o.type}")       # e.g., limit, stop, trailing_stop
            print(f"Side: {o.side}")       # buy or sell
            print(f"Limit Price: {o.limit_price}")
            print(f"Stop Price: {o.stop_price}")
            print(f"Status: {o.status}")
            print("-" * 20)

except Exception as e:
    print(f"❌ CONNECTION ERROR: {e}")