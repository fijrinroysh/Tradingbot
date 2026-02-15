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
				
            try: creds_json = open("google_credentials.json").read()
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
    """
    Logs the Junior Analyst report. 
    Handles both OLD formats (single object) and NEW DUAL formats (Position + Swing).
    """
    # --- RETRY LOOP ---
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return

            sh = client.open(SHEET_NAME)
												 
            try: sheet = sh.sheet1
								 
            except: sheet = sh.add_worksheet(title="Junior_Analyst_Log", rows=1000, cols=12)

            # --- HEADER CHECK (Auto-Add Columns if New Sheet) ---
            if sheet.row_count < 1 or not sheet.row_values(1):
                 headers = [
                     "Date", "Ticker", "Strategy", "Action", "Score", "Price",
                     "Detailed_Analysis", "Buy_Limit", "Take_Profit", "Stop_Loss", "Sector"
                 ]
                 sheet.append_row(headers)

            # --- DUAL STRATEGY HANDLING (New Prompt) ---
            if "position_trade_analysis" in analysis and "swing_trade_analysis" in analysis:
                current_price = analysis.get('current_price', 0)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
				
                rows_to_add = []
                
                # 1. Position Strategy Row
                pos = analysis["position_trade_analysis"]
                p_exec = pos.get('execution_plan', {})
                
                # Format Breakdown
                p_breakdown = pos.get('analysis_breakdown', [])
                p_text = "\n".join([f"🔹 [{i.get('label')}]: {i.get('details')}" for i in p_breakdown]) if isinstance(p_breakdown, list) else str(p_breakdown)

                rows_to_add.append([
                    timestamp,
                    ticker,
                    "Position Trading",     # Strategy
                    pos.get("verdict", "N/A"),
                    pos.get("score", 0),
                    current_price,          # Price
                    p_text,                 # Detailed Analysis
                    p_exec.get("entry_price", 0),
                    p_exec.get("take_profit", 0),
                    p_exec.get("stop_loss", 0),
                    "N/A"                   # Sector (Not in new prompt, can be ignored)
                ])
                
                # 2. Swing Strategy Row
                swing = analysis["swing_trade_analysis"]
                s_exec = swing.get('execution_plan', {})
                
                # Format Breakdown
                s_breakdown = swing.get('analysis_breakdown', [])
                s_text = "\n".join([f"🔹 [{i.get('label')}]: {i.get('details')}" for i in s_breakdown]) if isinstance(s_breakdown, list) else str(s_breakdown)

                rows_to_add.append([
                    timestamp,
                    ticker,
                    "Swing Trading",        # Strategy
                    swing.get("verdict", "N/A"),
                    swing.get("score", 0),
                    current_price,          # Price
                    s_text,                 # Detailed Analysis
                    s_exec.get("entry_price", 0),
                    s_exec.get("take_profit", 0),
                    s_exec.get("stop_loss", 0),
                    "N/A"
                ])
                
                sheet.append_rows(rows_to_add)
                print(f"   ✅ [HISTORY] Logged Dual Strategy for {ticker} (2 Rows).")
                return

            # --- STANDARD HANDLING (Fallback for old prompt) ---
            else:
														   
                exec_plan = analysis.get('execution', {})
													  
				
														  
									  
													
															   
													  
														 
																	  

                row = [
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    ticker,
                    "Standard", # Strategy
                    analysis.get('action'),
                    analysis.get('conviction_score'),
                    "N/A",      # Price (Old prompt didn't return it)
                    str(analysis.get('analysis_breakdown', '')),
                    exec_plan.get('buy_limit', 0),
                    exec_plan.get('take_profit', 0),
                    exec_plan.get('stop_loss', 0),
                    analysis.get('sector')
                ]
				
                sheet.append_row(row)
                print(f"   ✅ [HISTORY] Logged Standard Report for {ticker}.")
                return
            
        except Exception as e:
            print(f"⚠️ History Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)

def filter_candidates(candidates, limit=20):
    """
    Prioritizes stocks that have NEVER been analyzed, followed by those analyzed longest ago.
																	  
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
											   
                    history_map[r[1]] = r[0] # Ticker -> Date
            break
        except Exception as e:
            print(f"⚠️ History Read Error (Attempt {attempt+1}/3): {e}")
            time.sleep(5)
            if attempt == 2: return candidates[:limit]

    # 2. Score Candidates
    scored_candidates = []
    now = datetime.now()
    
    for t in candidates:
        days_since = 9999 
		
        if t in history_map:
            try:
										
                last_seen = datetime.strptime(history_map[t], "%Y-%m-%d %H:%M")
                days_since = (now - last_seen).days
	   
            except: pass
												  

												
																	  
        scored_candidates.append((t, days_since))

    # 3. Sort & Extract
																							   
    scored_candidates.sort(key=lambda x: x[1], reverse=True)

					  
													   
																						   
    valid = [x[0] for x in scored_candidates[:limit]]
        
    print(f"✅ [HISTORY] Prioritized {len(valid)} stalest candidates (Limit: {limit}).")
    return valid
