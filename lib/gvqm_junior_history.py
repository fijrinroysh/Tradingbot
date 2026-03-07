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
    # --- 1. GRAB THE FIGHTERS & CONCATENATE ---
    winner = analysis.get('ticker', ticker)
    loser = analysis.get('defeated_ticker', 'UNKNOWN')
    matchup_display = f"{winner} - {loser}" if loser != 'UNKNOWN' else winner

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
                    matchup_display,        # 🎯 Replaced 'ticker' with 'NOW - XYZ'
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
                    matchup_display,        # 🎯 Replaced 'ticker' with 'NOW - XYZ'
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
                print(f"   ✅ [HISTORY] Logged Matchup {matchup_display} (2 Rows).")
                return

            # --- STANDARD HANDLING (Fallback for old prompt) ---
            else:
                exec_plan = analysis.get('execution', {})
                row = [
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    matchup_display,        # 🎯 Replaced 'ticker' with 'NOW - XYZ'
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
                print(f"   ✅ [HISTORY] Logged Standard Matchup {matchup_display}.")
                return
            
        except Exception as e:
            print(f"⚠️ History Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)

def filter_candidates(distressed_tickers, limit=20):
    """
    Acts as a Priority Queue. 
    Reads the 'Last_Match' date directly from the Minor League Elo Scoreboard
    so BOTH winners and losers get their staleness accurately tracked.
    """
    # Import locally to avoid circular import issues
    import lib.gvqm_minor_league as minor_league 
    
    try:
        # 1. Fetch the entire Minor League leaderboard
        leaderboard = minor_league.fetch_leaderboard("Junior_Elo")
        
        # 2. Build the "Last Played" map: {'AAPL': '2023-10-25', 'TSLA': '2023-10-20'}
        last_played_map = {}
        if leaderboard:
            for t, stats in leaderboard.items():
                date_str = stats.get('Last_Match', '')
                if date_str:
                    last_played_map[t] = date_str
                    
    except Exception as e:
        print(f"   ⚠️ [JUNIOR HISTORY] Could not read Elo staleness. Defaulting to raw list. Error: {e}")
        return distressed_tickers[:limit]

    # 3. Sort the Distressed Tickers into the Priority Queue
    prioritized_list = []
    
    for t in distressed_tickers:
        if t not in last_played_map:
            # PRIORITY 1: ROOKIE (Never played a match in the Minor League)
            # Give it an artificial date of year 1900 so it goes to the absolute front of the line
            prioritized_list.append({'ticker': t, 'last_played': '1900-01-01'})
        else:
            # PRIORITY 2/3: VETERAN (Has an Elo rating and a Last_Match date)
            prioritized_list.append({'ticker': t, 'last_played': last_played_map[t]})
            
    # 4. Sort the list by 'last_played' ASCENDING (Oldest dates first)
    prioritized_list.sort(key=lambda x: x['last_played'])
    
    # 5. Slice the top 'limit' (e.g., top 20 stalest/newest stocks)
    drafted_tickers = [item['ticker'] for item in prioritized_list[:limit]]
    
    return drafted_tickers

#==========================================
# 📥 READING (JUNIOR REPORTS)
# ==========================================

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
            raw_t = str(row.get('Ticker', '')).strip().upper()
            if not raw_t: continue
            
            # --- 🛡️ SAFETY NET: Extract just the Winner ---
            # If the sheet says "NOW - XYZ", we only want "NOW" for the internal systems
            t = raw_t.split('-')[0].strip()
            
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