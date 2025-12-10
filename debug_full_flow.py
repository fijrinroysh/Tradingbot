import sys
import os
import time

# 1. Setup Environment
current_dir = os.getcwd()
sys.path.append(current_dir)

print("🧪 FULL SYSTEM SIMULATION: Trader -> Route -> Sheets")
print("="*60)

try:
    # Import your actual libraries
    import lib.gvqm_alpaca_trader as trader
    import lib.gvqm_senior_history as senior_history
    import config
    
    # 2. Setup Dummy Trade (Ford - F)
    TICKER = "F"
    INVEST_AMT = 20 
    PRICE = trader.get_current_price(TICKER)
    
    if not PRICE:
        print("❌ CRITICAL: Could not fetch price from Alpaca. Check connection.")
        sys.exit()

    BUY_LIMIT = round(PRICE * 0.99, 2)
    TP = round(PRICE * 1.05, 2)
    SL = round(PRICE * 0.95, 2)
    
    print(f"📉 SCENARIO: Senior Manager orders BUY {TICKER} @ ${BUY_LIMIT}")

    # 3. EXECUTE TRADER (Step 1 of Crash)
    print("\n⚡ [STEP 1] Calling Trader Module...")
    
    # We call the exact function routes.py uses
    trade_events = trader.manage_smart_trade(TICKER, INVEST_AMT, BUY_LIMIT, TP, SL)
    
    print(f"   > Raw Return Type: {type(trade_events)}")
    print(f"   > Raw Return Content: {trade_events}")

    # 4. SIMULATE ROUTE LOGIC (Step 2 of Crash)
    print("\n🔄 [STEP 2] Simulating Routes.py Loop...")
    
    if not trade_events:
        print("   ⚠️ Trader returned Nothing.")
    else:
        # Check if it accidentally returned a single dict instead of a list
        if isinstance(trade_events, dict):
            print("   ⚠️ WARNING: Trader returned a Dict, not a List. (Routes expects List)")
            trade_events = [trade_events]

        for i, event in enumerate(trade_events):
            print(f"   --- Processing Item #{i} ---")
            print(f"   > Item Type: {type(event)}")
            print(f"   > Item Content: {event}")
            
            # THE CRASH LINE
            try:
                event_type = event['event']
                print(f"   ✅ Accessed event['event']: {event_type}")
                
                # 5. EXECUTE SHEET LOGGING (Step 3 of Crash)
                if event['event'] not in ["HOLD", "ERROR"]:
                    print(f"   📝 [STEP 3] Writing to Google Sheets (Trade_Log)...")
                    senior_history.log_trade_event(TICKER, event_type, event)
                    print("   ✅ Sheet Write Success!")
                else:
                    print(f"   ℹ️ Skipping Sheet Log (Event is {event_type})")
                    
            except TypeError as e:
                print(f"   ❌ CRASHED: TypeError - {e}")
                print("   🔍 DIAGNOSIS: The item above is NOT a dictionary. It's likely an Alpaca Object.")
                
            except Exception as e:
                print(f"   ❌ CRASHED: {e}")

    print("\n" + "="*60)
    print("🏁 SIMULATION COMPLETE")

except ImportError as e:
    print(f"❌ SETUP ERROR: Could not import libraries. {e}")
except Exception as e:
    print(f"❌ UNEXPECTED ERROR: {e}")