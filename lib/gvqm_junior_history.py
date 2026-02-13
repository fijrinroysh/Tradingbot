import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json
import config
import time

SHEET_NAME = getattr(config, 'GOOGLE_SHEET_NAME', "TradingBot_History")

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def get_client():
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
						
        if os.path.exists("google_credentials.json"):
            try:
                creds_json = open("google_credentials.json").read()
            except: return None
   
        else: return None
            
    try:
        creds_dict = json.loads(creds_json)
		  
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"⚠️ [JUNIOR HISTORY] Auth Error: {e}")
        return None



def log_report(ticker, analysis):
    # --- RETRY LOOP ---
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return

            sh = client.open(SHEET_NAME)
            sheet = sh.sheet1
            
            # --- CLEANER HEADERS (Removed deleted fields) ---
            if sheet.row_count < 1 or not sheet.row_values(1):
                 headers = [
                     "Date", "Ticker", "Sector", "Action", "Score", 
                     "Detailed_Analysis", # <--- The Main Justification Column
                     "Buy_Limit", "Take_Profit", "Stop_Loss"
                 ]
                 sheet.append_row(headers)

            exec_plan = analysis.get('execution', {})
            
            # --- FORMAT BREAKDOWN ---
            breakdown = analysis.get('analysis_breakdown', [])
            analysis_text = ""
            if isinstance(breakdown, list):
                lines = []
                for item in breakdown:
                    lbl = item.get('label', 'Unknown')
                    det = item.get('details', 'N/A')
                    lines.append(f"🔹 [{lbl}]: {det}")
                analysis_text = "\n".join(lines)
            else:
                analysis_text = str(breakdown)

            # --- BUILD ROW ---
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                ticker, 
                analysis.get('sector'), 
                analysis.get('action'), 
                analysis.get('conviction_score'),
                analysis_text, # <--- Consolidated Analysis
                exec_plan.get('buy_limit', 0), 
                exec_plan.get('take_profit', 0), 
                exec_plan.get('stop_loss', 0)
            ]
            
            sheet.append_row(row)
            print(f"✅ [JUNIOR] Lean Report filed for {ticker}.")
            return 

        except Exception as e:
            print(f"⚠️ Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(5)
            
    print(f"❌ [JUNIOR] Failed to log {ticker} after 3 attempts.")

def filter_candidates(candidates, limit=20):
    """
    Prioritizes stocks that have NEVER been analyzed, followed by those analyzed longest ago.
    Removes strict cooldown to allow re-analysis if the list is short.
    """
    # 1. Fetch History
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return candidates[:limit]

            sheet = client.open(SHEET_NAME).sheet1
            records = sheet.get_all_values()
            
																
            history_map = {}
            for r in records[1:]:
                if len(r) > 1:
                    # Map Ticker -> Date String
                    history_map[r[1]] = r[0]
            break
        except Exception as e:
            print(f"⚠️ History Read Error (Attempt {attempt+1}/3): {e}")
            time.sleep(5)
            if attempt == 2: return candidates[:limit]

    # 2. Score Candidates by "Staleness"
    scored_candidates = []
    now = datetime.now()
    
    for t in candidates:
        days_since = 9999 # Default: High priority for "Never Analyzed"
        
        if t in history_map:
            try:
                # Parse YYYY-MM-DD HH:MM
                last_seen = datetime.strptime(history_map[t], "%Y-%m-%d %H:%M")
                days_since = (now - last_seen).days
							
            except: 
                pass # Keep as 9999 if parse fails

        # We do NOT filter by cooldown anymore. 
        # We just add everything and let the sort handle the priority.
        scored_candidates.append((t, days_since))

    # 3. The Sort (Highest Days -> Lowest Days)
    # This puts 9999 (New) at the top, followed by 365 (Old), with 0 (Yesterday) at the bottom.
    scored_candidates.sort(key=lambda x: x[1], reverse=True)

    # 4. Extract Top N
    # If limit is 20, we take the 20 "stalest" stocks. 
    # Recently analyzed stocks naturally fall off the list unless we run out of candidates.
    valid = [x[0] for x in scored_candidates[:limit]]
        
    print(f"✅ [HISTORY] Prioritized {len(valid)} stalest candidates (Limit: {limit}).")
    return valid
