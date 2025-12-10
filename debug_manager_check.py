import sys
import os
import inspect

# Ensure we can find the lib folder
sys.path.append(os.getcwd())

try:
    import lib.gvqm_alpaca_trader as trader
    
    print(f"📂 FILE: {trader.__file__}")
    print("🔍 INSPECTING manage_smart_trade source code...")
    source = inspect.getsource(trader.manage_smart_trade)
    
    print("-" * 40)
    # Print the specific part we care about
    for line in source.split('\n'):
        if "replace_order" in line:
            print(f"Line found: {line.strip()}")
    print("-" * 40)

    if "ReplaceOrderRequest(" in source:
        print("✅ GOOD: The code is using the Object.")
    else:
        print("❌ BAD: The code is using a Dictionary (or raw params). This causes the crash.")

except Exception as e:
    print(f"❌ Error: {e}")