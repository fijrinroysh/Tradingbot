import sys
import os
import time

# Setup environment
sys.path.append(os.getcwd())

print("🧪 DEBUG: Testing 'Update Existing' Logic (Live)")
print("="*60)

try:
    import lib.gvqm_alpaca_trader as trader
    from alpaca.trading.client import TradingClient
    import config

    # 1. FIND A REAL POSITION
    print("... Connecting to Alpaca to find active positions ...")
    client = TradingClient(config.ALPACA_KEY_ID, config.ALPACA_SECRET_KEY, paper=True)
    positions = client.get_all_positions()

    target_ticker = 'CRM'
    
    if not positions:
        print("⚠️ No positions found. Placing a dummy trade for 'F' (Ford) to create one...")
        # Create a position so we can update it
        trader.place_smart_trade("F", 20, 10.0, 11.0, 9.0)
        time.sleep(5) # Wait for Alpaca to process
        target_ticker = "F"
    else:
        # Pick the first one we find
        target_ticker = positions[0].symbol
        print(f"✅ Found active position: {target_ticker} ({positions[0].qty} shares)")

    # 2. CALCULATE NEW TARGETS (To Trigger Update)
    # We get the current price and move the goalposts
    price = trader.get_current_price(target_ticker)
    if not price:
        print("❌ Error: Could not fetch price. Aborting.")
        sys.exit()

    # Move TP/SL by 5% from current price to ensure they are "different" enough
    new_tp = round(price * 1.05, 2)
    new_sl = round(price * 0.95, 2)
    
    print(f"📉 {target_ticker} Price: ${price}")
    print(f"🎯 Attempting UPDATE -> TP: ${new_tp} | SL: ${new_sl}")

    # 3. EXECUTE THE UPDATE
    print("\n⚡ Calling manage_smart_trade...")
    
    # This simulates exactly what the Senior Manager does
    result = trader.manage_smart_trade(
        target_ticker, 
        config.INVEST_PER_TRADE, 
        price,   # Buy limit (ignored for updates)
        new_tp,  # NEW Take Profit
        new_sl   # NEW Stop Loss
    )

    # 4. INSPECT THE RESULT
    print("-" * 60)
    print(f"🔍 RAW RESULT TYPE: {type(result)}")
    print(f"🔍 RAW CONTENT: {result}")
    print("-" * 60)

    # 5. PASS/FAIL CHECK
    if isinstance(result, list):
        print("✅ TEST PASSED: Returned a List.")
        
        if not result:
             print("ℹ️ List is empty (means orders were already aligned or failed silently).")
        else:
             first_item = result[0]
             if isinstance(first_item, dict):
                 print("✅ TEST PASSED: List contains Dictionaries.")
                 print(f"   Event: {first_item.get('event')}")
                 if first_item.get('event') == "ERROR":
                     print("⚠️ WARNING: The logic worked, but Alpaca rejected the update (see info above).")
             else:
                 print(f"❌ FAIL: List contains {type(first_item)} (Expected Dict).")
    else:
        print(f"❌ FAIL: Returned {type(result)} (Expected List).")

except ImportError as e:
    print(f"❌ SETUP ERROR: {e}")
except Exception as e:
    print(f"❌ RUNTIME ERROR: {e}")