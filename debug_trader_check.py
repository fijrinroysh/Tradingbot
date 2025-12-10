import sys
import os
import inspect
import textwrap

# Ensure we can find the lib folder
current_dir = os.getcwd()
sys.path.append(current_dir)

print("🔍 DEBUG: Inspecting 'lib.gvqm_alpaca_trader'...")

try:
    import lib.gvqm_alpaca_trader as trader
    
    # 1. Check File Location
    print(f"📂 FILE PATH: {trader.__file__}")
    
    # 2. Inspect 'place_smart_trade' Source Code
    source = inspect.getsource(trader.place_smart_trade)
    
    print("\n📜 ACTUAL SOURCE CODE ON DISK (place_smart_trade):")
    print("="*60)
    print(source)
    print("="*60)
    
    # 3. Validation Logic
    if 'return [{' in source and '"event": "NEW_ENTRY"' in source:
        print("\n✅ CODE LOOKS CORRECT. The function returns a List of Dicts.")
        print("   If you still get errors, try deleting the __pycache__ folder inside /lib/.")
    else:
        print("\n❌ CODE IS OUTDATED! The function is missing the list return format.")
        print("   It is likely returning the raw 'trade' object.")
        print("   -> ACTION: Overwrite lib/gvqm_alpaca_trader.py again.")

except ImportError:
    print("❌ ERROR: Could not import 'lib.gvqm_alpaca_trader'. Check your file naming.")
except Exception as e:
    print(f"❌ ERROR: {e}")