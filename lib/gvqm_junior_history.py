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
            
            # --- DEBUG: PRINT URL ---
            # This tells us EXACTLY where the data is going
            if attempt == 0:
                print(f"   📝 Writing to Sheet: {sh.title} (ID: {sh.id})")
                print(f"   🔗 URL: https://docs.google.com/spreadsheets/d/{sh.id}")

            # --- CLEAN HEADERS (16 Columns) ---
            if sheet.row_count < 1 or not sheet.row_values(1):
                 headers = [
                     "Date", "Ticker", "Sector", "Action", "Score", 
                     "Status", "Status_Reason", 
                     "Valuation", "Valuation_Reason", 
                     "Rebound", "Rebound_Reason", 
                     "Catalyst", 
                     "Buy_Limit", "Take_Profit", "Stop_Loss",
                     "Intel"
                 ]
                 sheet.append_row(headers)

            exec_plan = analysis.get('execution', {})
            
													   
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                ticker, 
                analysis.get('sector'), 
                analysis.get('action'), 
                analysis.get('conviction_score'),
                analysis.get('status'), 
                analysis.get('status_rationale'),
                analysis.get('valuation'), 
                analysis.get('valuation_rationale'),
                analysis.get('rebound_potential'), 
                analysis.get('rebound_rationale'),
                analysis.get('catalyst'),
	
			 
                exec_plan.get('buy_limit', 0), 
                exec_plan.get('take_profit', 0), 
                exec_plan.get('stop_loss', 0),
	
                analysis.get('intel')
            ]
            sheet.append_row(row)
            print(f"✅ [JUNIOR] Report filed for {ticker}.")
            return # Success

        except Exception as e:
            print(f"⚠️ Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(5)
            
    print(f"❌ [JUNIOR] Failed to log {ticker} after 3 attempts.")

def filter_candidates(candidates, limit=20):
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return candidates[:limit]

            sheet = client.open(SHEET_NAME).sheet1
            records = sheet.get_all_values()
            
            # No splitting needed anymore, using standard format
            history_map = {}
            for r in records[1:]:
                if len(r) > 1:
													   
                    history_map[r[1]] = r[0]
            break
        except Exception as e:
            print(f"⚠️ History Read Error (Attempt {attempt+1}/3): {e}")
            time.sleep(5)
            if attempt == 2: return candidates[:limit]

    valid = []
    now = datetime.now()
    
    for t in candidates:
        if t in history_map:
            try:
                # Parse YYYY-MM-DD HH:MM
                last_seen = datetime.strptime(history_map[t], "%Y-%m-%d %H:%M")
                if (now - last_seen).days < config.COOLDOWN_DAYS: 
                    continue
            except: pass
        valid.append(t)
        if len(valid) >= limit: break
        
    print(f"✅ [HISTORY] Approved {len(valid)} fresh tickers for today.")
    return valid
