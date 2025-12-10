import sys
import os
import time

# Ensure we can find the lib folder
sys.path.append(os.getcwd())

print("🔍 DEBUG: CRM Update Diagnosis")
print("="*60)

try:
    import config
    import lib.gvqm_alpaca_trader as trader
    
    TICKER = "CRM"
    
    # 1. Get Current Price
    print(f"📡 Fetching live price for {TICKER}...")
    price = trader.get_current_price(TICKER)
    if not price:
        print("❌ Could not fetch price. Is Alpaca connected?")
        sys.exit()
        
    print(f"   Current Price: ${price}")

    # 2. Define NEW Targets (Force Update)
    # We move them 5% away to guarantee they are different from whatever you have now
    new_tp = round(price * 5, 2)
    new_sl = round(price * .25, 2)
    
    print(f"\n🎯 Attempting Update for {TICKER}:")
    print(f"   New TP: ${new_tp}")
    print(f"   New SL: ${new_sl}")

    # 3. Call the Trader Module
    print("\n⚡ EXECUTION START (Watch for [DEBUG] logs)...")
    result = trader.manage_smart_trade(TICKER, 50, price, new_tp, new_sl)
    
    print("-" * 60)
    print(f"🏁 RESULT: {result}")

except ImportError as e:
    print(f"❌ Import Error: {e}")
except Exception as e:
    print(f"❌ General Error: {e}")