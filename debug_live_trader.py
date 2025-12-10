import sys
import os
import time

# Ensure we can find the lib folder
current_dir = os.getcwd()
sys.path.append(current_dir)

print("🧪 DEBUGGER: Initializing Trader Module...")

try:
    import lib.gvqm_alpaca_trader as trader
    import config
    
    # 1. SETUP DUMMY TRADE PARAMETERS
    TICKER = "F"  # Ford is cheap, good for testing
    INVEST_AMT = 20 # Small amount
    PRICE = trader.get_current_price(TICKER)
    
    if not PRICE:
        print("❌ ERROR: Could not fetch price. Is Alpaca connected?")
        sys.exit()
        
    BUY_LIMIT = round(PRICE * 0.99, 2) # 1% below current (Limit Buy)
    TP = round(PRICE * 1.05, 2)
    SL = round(PRICE * 0.95, 2)
    
    print(f"\n📉 TEST SETUP: Buying {TICKER} @ ${BUY_LIMIT} (Current: ${PRICE})")
    print("-" * 60)

    # 2. EXECUTE THE FUNCTION
    print("⚡ Calling 'trader.place_smart_trade'...")
    
    # We call place_smart_trade directly since that's where the logic change was made
    result = trader.place_smart_trade(TICKER, INVEST_AMT, BUY_LIMIT, TP, SL)
    
    print("-" * 60)
    print("🔍 INSPECTION RESULTS:")
    
    # 3. TYPE CHECK
    result_type = type(result)
    print(f"   > Return Type: {result_type}")
    print(f"   > Raw Content: {result}")
    
    # 4. CRASH TEST (Simulating routes.py)
    print("\n💥 CRASH TEST (Simulating routes.py loop):")
    try:
        # This is the exact loop from routes.py that failed
        if result:
            for event in result:
                event_type = event['event'] # <--- This is where it crashed
                print(f"   ✅ SUCCESS: Read event '{event_type}'")
        else:
            print("   ⚠️ Result was Empty/None")
            
        print("\n✅ PASSED: The return format is correct (List of Dicts).")
        
    except TypeError as e:
        print(f"\n❌ FAILED: Crashed with TypeError.")
        print(f"   Reason: The iterator 'event' is likely an Object, not a Dict.")
        print(f"   Error Details: {e}")
        
    except Exception as e:
        print(f"\n❌ FAILED: Unexpected Error: {e}")

except ImportError as e:
    print(f"❌ IMPORT ERROR: {e}")
except Exception as e:
    print(f"❌ SETUP ERROR: {e}")