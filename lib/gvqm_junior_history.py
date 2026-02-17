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

#==========================================
# 📥 READING (JUNIOR REPORTS)
# ==========================================

# lib/gvqm_junior_history.py


def fetch_recent_reports(lookback_days=3):
    """
    Fetches Junior reports using YOUR EXACT COLUMN NAMES.
    Columns: Date, Ticker, Overall_Rec, Strategy, Action, Score, Reason, 
             Buy_Limit, Take_Profit, Stop_Loss, Detailed_Analysis
    """
    client = get_client()
    if not client: return []
    
    try:
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_records()
        
        valid_rows = []
        now = datetime.now()
        
        # 1. Date Filter
        for row in data:
            date_val = str(row.get('Date', ''))
            if not date_val: continue
            try:
                try: dt = datetime.strptime(date_val, "%Y-%m-%d %H:%M")
                except: dt = datetime.strptime(date_val, "%Y-%m-%d")
                row['_dt'] = dt 
                if (now - dt).days <= lookback_days:
                    valid_rows.append(row)
            except: continue
            
        # 2. Sort Newest First (Latest Record Logic)
        valid_rows.sort(key=lambda x: x['_dt'], reverse=True)
        
        # 3. Normalize & Merge
        merged = {}
        for row in valid_rows:
            t = row.get('Ticker', '').strip().upper()
            if not t: continue
            
            # --- 🎯 EXACT COLUMN MAPPING ---
            # We map your specific sheet columns to the internal keys
            strat = str(row.get('Strategy', '')).strip()
            score = 0.0
            try: score = float(row.get('Score', 0))
            except: pass

            # 'Detailed_Analysis' is usually the big text block (Rationale)
            # 'Action' is Buy/Sell
            # 'Overall_Rec' is the Verdict
            rationale_val = str(row.get('Detailed_Analysis', '')).strip()
            if not rationale_val: rationale_val = str(row.get('Reason', '')).strip()
            
            verdict_val = str(row.get('Overall_Rec', '')).strip()
            action_val = str(row.get('Action', '')).strip()
            
            # --- INIT MASTER OBJECT ---
            if t not in merged:
                merged[t] = {
                    'ticker': t,
                    'Date': str(row.get('Date', '')),
                    # We default price to 0 if not in sheet; Routes will fill from Alpaca
                    'Log_Price': 0.0, 
                    
                    'Position_Score': 0.0,
                    'Position_Verdict': "N/A",
                    'Position_Rationale': "",
                    'Position_Action': "WAIT",
                    
                    'Swing_Score': 0.0,
                    'Swing_Verdict': "N/A",
                    'Swing_Rationale': "",
                    'Swing_Action': "WAIT"
                }
            
            # --- FILL DATA ---
            if 'Position' in strat:
                if merged[t]['Position_Score'] == 0:
                    merged[t]['Position_Score'] = score
                    merged[t]['Position_Verdict'] = verdict_val
                    merged[t]['Position_Rationale'] = rationale_val
                    merged[t]['Position_Action'] = action_val
                    
            elif 'Swing' in strat:
                if merged[t]['Swing_Score'] == 0:
                    merged[t]['Swing_Score'] = score
                    merged[t]['Swing_Verdict'] = verdict_val
                    merged[t]['Swing_Rationale'] = rationale_val
                    merged[t]['Swing_Action'] = action_val
            
            # Fallback for rows without Strategy (Legacy)
            elif not strat:
                if merged[t]['Position_Score'] == 0:
                    merged[t]['Position_Score'] = score
                    merged[t]['Position_Rationale'] = rationale_val
                    merged[t]['Position_Action'] = action_val

        return list(merged.values())

    except Exception as e:
        print(f"⚠️ Junior Fetch Error: {e}")
        return []