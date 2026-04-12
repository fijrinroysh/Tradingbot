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
# 🥊 1. LOG MATCHUPS (SENIOR DECISIONS TAB)
# ==========================================
def log_matchup(cand_a, cand_b, winner, rationale):
    """Logs the 1v1 Major League scouting rationale to Senior_Decisions."""
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return
            sh = client.open(SHEET_NAME)
            
            headers = ["Date", "Matchup", "Winner", "Rationale"]
            
            try: sheet = sh.worksheet(SENIOR_DECISIONS_TAB)
            except: 
                sheet = sh.add_worksheet(title=SENIOR_DECISIONS_TAB, rows=1000, cols=4)
                sheet.append_row(headers)
            
            if sheet.row_count < 1 or not sheet.row_values(1):
                 sheet.append_row(headers)

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            matchup_str = f"{cand_a} vs {cand_b}"
            
            sheet.append_row([timestamp, matchup_str, winner, rationale])
            print(f"   ✅ [SENIOR] Matchup Rationale Logged to {SENIOR_DECISIONS_TAB}.")
            return
            
        except Exception as e:
            print(f"   ⚠️ Matchup Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)

# ==========================================
# 📝 2. LOG EXECUTIONS (TRADE LOG TAB)
# ==========================================
def log_detailed_decisions(decision_data, holdings_map=None):
    """Logs the Senior Agent's execution paperwork to the Trade_Log."""
    if holdings_map is None: holdings_map = {}
    
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return
            sh = client.open(SHEET_NAME)
            
            # Master headers for the Front Office
            headers = [
                "Date", "Ticker", "Action", "Entry_Price", 
                "Stop_Loss", "Take_Profit", "Rationale", "Shares_Held"
            ]
            
            try: sheet = sh.worksheet(TRADE_LOG_TAB)
            except: 
                sheet = sh.add_worksheet(title=TRADE_LOG_TAB, rows=2000, cols=8)
                sheet.append_row(headers)
            
            if sheet.row_count < 1 or not sheet.row_values(1):
                 sheet.append_row(headers)

            orders = decision_data.get('final_execution_orders', [])
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            rows_to_append = []
            
            for order in orders:
                if not order: continue
                ticker = order.get('ticker', 'UNKNOWN')
                shares_held = holdings_map.get(ticker, 0)
                
                rows_to_append.append([
                    timestamp, ticker, order.get('action', 'UNKNOWN'),
                    order.get('entry_price', 0), order.get('stop_loss', 0),
                    order.get('take_profit', 0), order.get('rationale', 'N/A'),
                    shares_held
                ])

            if rows_to_append:
                sheet.append_rows(rows_to_append)
            print(f"   ✅ [FRONT OFFICE] Trade Paperwork Logged to {TRADE_LOG_TAB}.")
            return
            
        except Exception as e:
            print(f"   ⚠️ Trade Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)

def log_mechanical_trade(ticker, action, reason, price=0, shares=0):
    """Logs purely mathematical Front Office actions (like firing a loser) to Trade_Log."""
    client = get_client()
    if not client: return
    
    try:
        sheet = client.open(SHEET_NAME).worksheet(TRADE_LOG_TAB)
    except gspread.exceptions.WorksheetNotFound:
        # If it doesn't exist, log_detailed_decisions will create it with the right headers.
        return 

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # Aligning perfectly with the 8 columns of the Trade_Log headers
        sheet.append_row([timestamp, ticker, action, price, "", "", reason, shares])
        print(f"   ✅ [FRONT OFFICE] Mechanical Action Logged to {TRADE_LOG_TAB}.")
    except Exception as e:
        print(f"   ⚠️ [HISTORY] Failed to log to {TRADE_LOG_TAB}: {e}")

# ==========================================
# 📊 3. LOG STRATEGY (STRATEGY BRIEF TAB)
# ==========================================
def log_strategy(decision_payload):
    """Logs the CEO Email Report."""
    try:
        client = get_client()
        if not client: return
        sh = client.open(SHEET_NAME)
        
        try: sheet = sh.worksheet(STRATEGY_TAB_NAME)
        except: 
            sheet = sh.add_worksheet(title=STRATEGY_TAB_NAME, rows=1000, cols=2)
            sheet.append_row(["Date", "CEO_Report"])

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        report = decision_payload.get('ceo_report', 'No report.')
        
        sheet.append_row([timestamp, report])
        print("   ✅ [SENIOR] Strategy/Email Logged.")
    except Exception as e:
        print(f"   ⚠️ Strategy Log Error: {e}")