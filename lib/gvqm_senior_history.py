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
    Fetches Junior reports using STRICT New Headers.
    Headers: Date, Ticker, Sector, Action, Score, Detailed_Analysis
    """
    client = get_client()
    if not client: return []
    
    try:
        # We read SHEET1 (Junior Logs)
        sheet = client.open(SHEET_NAME).sheet1
        rows = sheet.get_all_records() # Returns dicts with headers as keys
        
        if not rows: return []
        
        reports = []
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=lookback_days)
        
        for row in rows:
            try:
                # 1. Date Filter
                date_str = str(row.get('Date', ''))
                if not date_str: continue
                
                try:
                    row_date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                    if row_date < cutoff_date: continue
                except: continue

                # 2. Strict Extraction
                report = {
                    "ticker": row.get('Ticker'),
                    "date": date_str,
                    "conviction_score": row.get('Score', 0),
                    "action": row.get('Action', 'WATCH'),
                    "Detailed_Analysis": row.get('Detailed_Analysis', 'N/A')
                }
                
                # Cleanup Score
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
    """
    Fetches latest Junior Analysis for stocks we currently own.
    """
    if not portfolio_tickers: return []
    
    # We re-use the market fetch logic but filter for our specific tickers
    # This is efficient because get_all_records is one API call.
    all_reports = fetch_market_reports(lookback_days=7)
    
    # Filter for our portfolio
    relevant_reports = [r for r in all_reports if r['ticker'] in portfolio_tickers]
    
    print(f"   ✅ [HISTORY] Found {len(relevant_reports)} recent reports for active holdings.")
    return relevant_reports

# ==========================================
# 📤 WRITING (SENIOR DECISIONS)
# ==========================================

def log_detailed_decisions(decision_data, holdings_map=None):
    if holdings_map is None: holdings_map = {}
    
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return
            sh = client.open(SHEET_NAME)
            
            # --- NEW STRICT HEADERS ---
            headers = [
                "Date", "Ticker", "Conviction_Score", "Action", "Reason", 
                "Buy_Limit", "Take_Profit", "Stop_Loss", "Shares_Held", 
                "Detailed_Analysis" # Single Consolidated Column
            ]
            
            try: sheet = sh.worksheet(SENIOR_DECISIONS_TAB)
            except: 
                sheet = sh.add_worksheet(title=SENIOR_DECISIONS_TAB, rows=2000, cols=15)
                sheet.append_row(headers)
            
            if sheet.row_count < 1 or not sheet.row_values(1):
                 sheet.append_row(headers)

            orders = decision_data.get('final_execution_orders', [])
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            
            rows_to_append = []
            
            for order in orders:
                ticker = order.get('ticker')
                p = order.get('confirmed_params', {})
                
                # Flatten the Analysis List into a String for the Sheet
                breakdown = order.get('analysis_breakdown', [])
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

                row = [
                    timestamp, 
                    ticker, 
                    order.get('conviction_score', 0), 
                    order.get('action', 'HOLD'), 
                    order.get('reason', 'N/A'),
                    p.get('buy_limit', 0), 
                    p.get('take_profit', 0), 
                    p.get('stop_loss', 0),
                    holdings_map.get(ticker, 0),
                    analysis_text # <--- The Consolidated Block
                ]
                rows_to_append.append(row)
            
            if rows_to_append:
                sheet.append_rows(rows_to_append)
                
            print(f"   ✅ [SENIOR] Ledger Updated.")
            return
            
        except Exception as e:
            print(f"   ⚠️ Ledger Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)

def log_strategy(decision_payload):
    """Logs the CEO Report / Executive Summary."""
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