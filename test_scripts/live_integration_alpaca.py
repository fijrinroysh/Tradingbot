import sys
import os
import time

# Ensure lib modules can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lib.gvqm_alpaca_trader as trader
from alpaca.trading.requests import LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce

def run_alpaca_live_test():
    """
    Live Integration Test for Alpaca API.
    Sends a test limit order (far out of the money to prevent actual execution),
    verifies directly on the Alpaca server that the order exists and is valid,
    and then immediately cancels it.
    """
    print("🚀 Starting Alpaca Live Integration Test...")
    
    # Check connectivity
    try:
        account = trader.get_account()
        print(f"✅ Connected to Alpaca. Account Status: {account.status}")
        print(f"💰 Buying Power: ${account.buying_power}")
    except Exception as e:
        print(f"❌ Failed to connect to Alpaca: {e}")
        return

    test_ticker = "AAPL"
    
    # 1. Fetch current price
    try:
        current_price = trader.get_current_price(test_ticker)
        print(f"✅ Fetched live price for {test_ticker}: ${current_price}")
    except Exception as e:
        print(f"❌ Failed to fetch live price: {e}")
        return
        
    # 2. Place a safely "Out of the Money" Limit Order (e.g., $10)
    # So it doesn't accidentally fill
    safe_limit_price = 10.0 
    
    print(f"📝 Submitting test limit order for 1 share of {test_ticker} at ${safe_limit_price}...")
    try:
        order_request = LimitOrderRequest(
            symbol=test_ticker,
            qty=1,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            limit_price=safe_limit_price
        )
        order = trader.trading_client.submit_order(order_request)
        print(f"✅ Order submitted successfully! Order ID: {order.id}")
    except Exception as e:
        print(f"❌ Failed to submit order: {e}")
        return
        
    # 3. Wait a moment and verify directly on Alpaca server that the order was received
    time.sleep(2)
    try:
        open_orders = trader.trading_client.get_orders(filter=GetOrdersRequest(status='open'))
        test_order_found = False
        for o in open_orders:
            if o.id == order.id:
                test_order_found = True
                print(f"✅ Verified directly from Alpaca: Order {order.id} is officially listed as '{o.status}' on the exchange.")
                break
                
        if not test_order_found:
            print("❌ Order was submitted but could not be found in the open orders list on the Alpaca server.")
    except Exception as e:
        print(f"❌ Failed to fetch open orders: {e}")
        
    # 4. Cleanup: Cancel the test order
    print(f"🗑️ Canceling test order {order.id}...")
    try:
        trader.trading_client.cancel_order_by_id(order.id)
        print("✅ Test order successfully canceled!")
    except Exception as e:
        print(f"❌ Failed to cancel order: {e}")

if __name__ == "__main__":
    run_alpaca_live_test()
