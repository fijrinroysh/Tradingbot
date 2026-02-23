import gspread
from google.oauth2.service_account import Credentials
import config
import datetime
import json
import os
import time

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = getattr(config, 'GOOGLE_SHEET_NAME', "TradingBot_History")
SENIOR_DECISIONS_TAB = getattr(config, 'GOOGLE_SHEET_SENIOR_DECISIONS_TAB', "Senior_Decisions")
STRATEGY_TAB_NAME = getattr(config, 'GOOGLE_SHEET_STRATEGY_TAB', "Strategy_Brief")
TRADE_LOG_TAB = getattr(config, 'GOOGLE_SHEET_TRADE_LOG_TAB', "Trade_Log")

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
        print(f"⚠️ [SENIOR HISTORY] Auth Error: {e}")
        return None

# ==========================================
# 📥 READING (JUNIOR REPORTS)
# ==========================================

def fetch_market_reports(lookback_days=3):
    """
    Fetches Junior reports including the 'Strategy' column.
    """
    client = get_client()
    if not client: return []
    
    try:
        sheet = client.open(SHEET_NAME).sheet1
        rows = sheet.get_all_records()
        
        if not rows: return []
        
        reports = []
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=lookback_days)
        
        for row in rows:
            try:
                date_str = str(row.get('Date', ''))
                if not date_str: continue
                
                try:
                    row_date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                    if row_date < cutoff_date: continue
                except: continue

                report = {
                    "ticker": row.get('Ticker'),
                    "date": date_str,
                    # ✅ NEW: Fetch Strategy Column
                    "strategy": row.get('Strategy', 'Standard'), 
                    "conviction_score": row.get('Score', 0),
                    "action": row.get('Action', 'WATCH'),
                    "Detailed_Analysis": row.get('Detailed_Analysis', 'N/A')
                }
                
                try: report['conviction_score'] = int(report['conviction_score'])
                except: report['conviction_score'] = 0
                
                if report['ticker']:
                    reports.append(report)
                    
            except Exception: continue

        print(f"   ✅ [HISTORY] Fetched {len(reports)} valid market reports.")
        return reports

    except Exception as e:
        print(f"   ⚠️ Market Fetch Error: {e}")
        return []

def fetch_portfolio_reports(portfolio_tickers):
    if not portfolio_tickers: return []
    all_reports = fetch_market_reports(lookback_days=7)
    relevant_reports = [r for r in all_reports if r['ticker'] in portfolio_tickers]
    print(f"   ✅ [HISTORY] Found {len(relevant_reports)} recent reports for active holdings.")
    return relevant_reports

# ==========================================
# 📤 WRITING (SENIOR DECISIONS)
# ==========================================

def log_detailed_decisions(decision_data, holdings_map=None):
    """
    Logs the Senior Manager's Dual Analysis (Position + Swing) to Google Sheets.
    Writes 2 rows per ticker.
    """
    if holdings_map is None: holdings_map = {}
    
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return
            sh = client.open(SHEET_NAME)
            
            # --- UPDATED HEADERS (Added Overall_Rec) ---
            headers = [
                "Date", "Ticker", "Overall_Rec", "Strategy", "Action", "Score", 
                "Reason", "Buy_Limit", "Take_Profit", "Stop_Loss", 
                "Shares_Held", "Detailed_Analysis"
            ]
            
            try: sheet = sh.worksheet(SENIOR_DECISIONS_TAB)
            except: 
                sheet = sh.add_worksheet(title=SENIOR_DECISIONS_TAB, rows=2000, cols=15)
                sheet.append_row(headers)
            
            # Check if headers exist, if not add them
            if sheet.row_count < 1 or not sheet.row_values(1):
                 sheet.append_row(headers)

            # Orders are now complex Dual Objects
            orders = decision_data.get('final_execution_orders', [])
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            
            rows_to_append = []
            
            for order in orders:
                ticker = order.get('ticker')
                shares_held = holdings_map.get(ticker, 0)
                
                # ✅ NEW: Extract Overall Recommendation (High Level Decision)
                overall_rec = order.get('final_recommendation', 'N/A')
                
                # --- 1. LOG POSITION STRATEGY ---
                if 'position_trade_analysis' in order:
                    pos = order['position_trade_analysis']
                    p_exec = pos.get('execution_plan', {})
                    
                    # Format Breakdown
                    breakdown = pos.get('analysis_breakdown', [])
                    p_text = "\n".join([f"🔹 [{i.get('label')}]: {i.get('details')}" for i in breakdown]) if isinstance(breakdown, list) else str(breakdown)

                    rows_to_append.append([
                        timestamp,
                        ticker,
                        overall_rec,            # <--- ADDED HERE
                        "Position Trading",     # Strategy Column
                        pos.get('verdict', 'N/A'),
                        pos.get('score', 0),
                        pos.get('rationale', 'N/A'),
                        p_exec.get('entry_price', 0),
                        p_exec.get('take_profit', 0),
                        p_exec.get('stop_loss', 0),
                        shares_held,
                        p_text
                    ])

                # --- 2. LOG SWING STRATEGY ---
                if 'swing_trade_analysis' in order:
                    swing = order['swing_trade_analysis']
                    s_exec = swing.get('execution_plan', {})
                    
                    # Format Breakdown
                    breakdown = swing.get('analysis_breakdown', [])
                    s_text = "\n".join([f"🔹 [{i.get('label')}]: {i.get('details')}" for i in breakdown]) if isinstance(breakdown, list) else str(breakdown)

                    rows_to_append.append([
                        timestamp,
                        ticker,
                        overall_rec,            # <--- ADDED HERE
                        "Swing Trading",        # Strategy Column
                        swing.get('verdict', 'N/A'),
                        swing.get('score', 0),
                        swing.get('rationale', 'N/A'),
                        s_exec.get('entry_price', 0),
                        s_exec.get('take_profit', 0),
                        s_exec.get('stop_loss', 0),
                        shares_held,
                        s_text
                    ])

            if rows_to_append:
                sheet.append_rows(rows_to_append)
                
            print(f"   ✅ [SENIOR] Ledger Updated ({len(rows_to_append)} rows).")
            return
            
        except Exception as e:
            print(f"   ⚠️ Ledger Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)

def log_strategy(decision_payload):
    """Logs the CEO Report."""
    try:
        client = get_client()
        if not client: return
        sh = client.open(SHEET_NAME)
        
        try: sheet = sh.worksheet(STRATEGY_TAB_NAME)
        except: 
            sheet = sh.add_worksheet(title=STRATEGY_TAB_NAME, rows=1000, cols=5)
            sheet.append_row(["Date", "CEO_Report"])

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        report = decision_payload.get('ceo_report', 'No report.')
        
        sheet.append_row([timestamp, report])
        print("   ✅ [SENIOR] CEO Strategy Logged.")
    except Exception as e:
        print(f"   ⚠️ Strategy Log Error: {e}")


def fetch_active_strategies(active_tickers):
    """
    Scans the 'Senior_Decisions' ledger to find the LAST Overall Recommendation.
    Returns a map like: {'AAPL': 'HYBRID', 'TSLA': 'SWING_ONLY'}
    """
    if not active_tickers: return {}
    
    client = get_client()
    if not client: return {}

    try:
        sheet = client.open(SHEET_NAME).worksheet(SENIOR_DECISIONS_TAB)
        data = sheet.get_all_records()
        
        strategy_map = {}
        
        # Iterate through history (Oldest to Newest)
        # We want the LAST entry for each ticker
        for row in data:
            t = row.get('Ticker')
            # Look for our new specific column
            rec = row.get('Overall_Rec') 
            
            if t in active_tickers and rec:
                strategy_map[t] = rec
                
        print(f"   🧠 [MEMORY] Retrieved strategies for {len(strategy_map)} active holdings.")
        return strategy_map
        
    except Exception as e:
        print(f"   ⚠️ Memory Read Error: {e}")
        return {}
    


def log_mechanical_trade(ticker, action, reason, price=0, shares=0):
    """
    Logs Python-based mechanical decisions (like Relegation) to a separate Trade_Log sheet.
    """
    client = get_client()
    if not client: return
    
    try:
        sheet = client.open(SHEET_NAME).worksheet(TRADE_LOG_TAB)
    except gspread.exceptions.WorksheetNotFound:
        # Create it if it doesn't exist
        sheet = client.open(SHEET_NAME).add_worksheet(title=TRADE_LOG_TAB, rows=1000, cols=6)
        sheet.append_row(["Date", "Ticker", "Action", "Reason", "Current_Price", "Shares_Held"])

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        sheet.append_row([timestamp, ticker, action, reason, price, shares])
        print(f"   ✅ [HISTORY] Logged Mechanical Action to Trade_Log: {ticker} -> {action}")
    except Exception as e:
        print(f"   ⚠️ [HISTORY] Failed to log to Trade_Log: {e}")