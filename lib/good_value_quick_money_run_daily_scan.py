# good_value_quick_money_run_daily_scan.py
import sys, os
import time
import config

# Add root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- UPDATED IMPORTS ---
from lib.good_value_quick_money_market_scanner import find_distressed_stocks
from lib.good_value_quick_money_history_manager import filter_candidates, mark_as_analyzed
from lib.good_value_quick_money_gemini_agent import analyze_stock
import alpaca_trader 

def job():
    print("--- STARTING DAILY 'GOOD VALUE QUICK MONEY' SCAN ---")
    
    # 1. Find candidates
    candidates = find_distressed_stocks()
    
    if not candidates:
        print("No distressed stocks found.")
        return

    # 2. Filter using History
    to_analyze = filter_candidates(candidates, config.DAILY_SCAN_LIMIT)
    
    if not to_analyze:
        print("No fresh candidates to analyze today.")
        return

    print(f"--- Selected {len(to_analyze)} tickers for Deep Analysis ---")
    
    # 3. Analyze & Trade
    for ticker in to_analyze:
        
        result = analyze_stock(ticker)
        mark_as_analyzed(ticker)
        
        if result:
            action = result.get('action')
            status = result.get('status')
            conf = result.get('confidence')
            
            print(f"   > {ticker}: {action} | {status} | Confidence: {conf}")
            
            if action == "BUY" and status == "SAFE" and conf == "HIGH":
                print(f"*** HIGH CONVICTION BUY FOUND: {ticker} ***")
                print(f"    Reason: {result.get('reasoning')}")
                
                exec_plan = result.get('execution', {})
                
                alpaca_trader.place_smart_trade(
                    ticker, 
                    config.INVEST_PER_TRADE,
                    exec_plan.get('buy_limit'),
                    exec_plan.get('take_profit'),
                    exec_plan.get('stop_loss')
                )

        # Sleep to respect Gemini API rate limits
        time.sleep(30) 
        
    print("--- SCAN COMPLETE ---")

if __name__ == "__main__":
    job()