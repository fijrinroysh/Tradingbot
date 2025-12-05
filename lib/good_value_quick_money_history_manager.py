# lib/good_value_quick_money_history_manager.py
import json
import os
from datetime import datetime

# Use a specific history file for this strategy
HISTORY_FILE = "good_value_quick_money_history.json"
COOLDOWN_DAYS = 7 

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)

def filter_candidates(candidates, daily_limit):
    """
    Returns tickers that haven't been analyzed recently, up to the limit.
    """
    history = load_history()
    valid_candidates = []
    now = datetime.now()
    
    print(f"History Manager: Filtering {len(candidates)} candidates against history...")
    
    for ticker in candidates:
        last_scan_str = history.get(ticker)
        
        if last_scan_str:
            try:
                last_scan_date = datetime.strptime(last_scan_str, "%Y-%m-%d")
                if (now - last_scan_date).days < COOLDOWN_DAYS:
                    continue
            except ValueError:
                pass
        
        valid_candidates.append(ticker)
        
        if len(valid_candidates) >= daily_limit:
            break
            
    print(f"History Manager: Selected {len(valid_candidates)} fresh tickers for analysis.")
    return valid_candidates

def mark_as_analyzed(ticker):
    history = load_history()
    history[ticker] = datetime.now().strftime("%Y-%m-%d")
    save_history(history)