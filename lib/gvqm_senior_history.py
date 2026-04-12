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
# 📤 WRITING (SENIOR DECISIONS)
# ==========================================

def log_detailed_decisions(decision_data, holdings_map=None):
    """
    Logs the Senior Agent's execution paperwork to Google Sheets.
    """
    if holdings_map is None: holdings_map = {}
    
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return
            sh = client.open(SHEET_NAME)
            
            # The new, simplified headers matching our "Einstein" JSON prompt
            headers = [
                "Date", "Ticker", "Action", "Entry_Price", 
                "Stop_Loss", "Take_Profit", "Risk_Rationale", "Shares_Held"
            ]
            
            try: sheet = sh.worksheet(SENIOR_DECISIONS_TAB)
            except: 
                sheet = sh.add_worksheet(title=SENIOR_DECISIONS_TAB, rows=2000, cols=10)
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
                    timestamp,
                    ticker,
                    order.get('action', 'UNKNOWN'),
                    order.get('entry_price', 0),
                    order.get('stop_loss', 0),
                    order.get('take_profit', 0),
                    order.get('risk_rationale', 'N/A'),
                    shares_held
                ])

            if rows_to_append:
                sheet.append_rows(rows_to_append)
                
            print(f"   ✅ [SENIOR] Ledger Updated ({len(rows_to_append)} rows).")
            return
            
        except Exception as e:
            print(f"   ⚠️ Ledger Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)

def log_strategy(decision_payload):
    """Logs the CEO Report / Execution summaries."""
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
        print("   ✅ [SENIOR] Strategy/Execution Logged.")
    except Exception as e:
        print(f"   ⚠️ Strategy Log Error: {e}")

def log_mechanical_trade(ticker, action, reason, price=0, shares=0):
    """
    Logs Python-based pure-math decisions (like Swaps/Sells) to a separate Trade_Log sheet.
    """
    client = get_client()
    if not client: return
    
    try:
        sheet = client.open(SHEET_NAME).worksheet(TRADE_LOG_TAB)
    except gspread.exceptions.WorksheetNotFound:
        sheet = client.open(SHEET_NAME).add_worksheet(title=TRADE_LOG_TAB, rows=1000, cols=6)
        sheet.append_row(["Date", "Ticker", "Action", "Reason", "Current_Price", "Shares_Held"])

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        sheet.append_row([timestamp, ticker, action, reason, price, shares])
        print(f"   ✅ [HISTORY] Logged Mechanical Action to Trade_Log: {ticker} -> {action}")
    except Exception as e:
        print(f"   ⚠️ [HISTORY] Failed to log to Trade_Log: {e}")