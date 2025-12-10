import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import os
import json
import time

SHEET_NAME = "TradingBot_History"

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def get_client():
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        if os.path.exists("google_credentials.json"):
            creds_json = open("google_credentials.json").read()
        else: return None
    
    try:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"⚠️ [SENIOR HISTORY] Auth Error: {e}")
        return None

def fetch_junior_reports(lookback_days):
    # (Same as before - keeping existing logic)
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return []
            
            sheet = client.open(SHEET_NAME).sheet1
            records = sheet.get_all_values()
            candidates = []
            cutoff = datetime.now() - timedelta(days=lookback_days)
            
            for row in records[1:]:
                if len(row) < 16: continue
                try:
                    try:
                        row_date = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
                    except:
                        row_date = datetime.strptime(row[0].split(" ")[0], "%Y-%m-%d")
                        
                    if row_date < cutoff: continue
                    
                    candidates.append({
                        "analysis_date": row[0],
                        "ticker": row[1],
                        "sector": row[2],
                        "conviction_score": row[4],
                        "status": row[5],
                        "status_rationale": row[6],
                        "valuation": row[7],
                        "valuation_rationale": row[8],
                        "rebound": row[9],
                        "rebound_rationale": row[10],
                        "catalyst": row[11],
                        "proposed_execution": {
                            "buy_limit": row[12],
                            "take_profit": row[13],
                            "stop_loss": row[14]
                        },
                        "intel": row[15]
                    })
                except: continue
            return candidates
            
        except Exception as e:
            print(f"⚠️ Senior Fetch Error (Attempt {attempt+1}): {e}")
            time.sleep(5)
            
    return []

def get_last_strategy():
    # (Same as before)
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return None
            sheet = client.open(SHEET_NAME).worksheet("Executive_Briefs")
            last_row = sheet.get_all_values()[-1]
            return {"date": last_row[0], "top_tickers": last_row[3]}
        except: 
            time.sleep(2)
    return None

def log_strategy(report):
    # (Logs the markdown summary - Same as before)
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return
            sh = client.open(SHEET_NAME)
            try: sheet = sh.worksheet("Executive_Briefs")
            except: sheet = sh.add_worksheet(title="Executive_Briefs", rows="1000", cols="5"); sheet.append_row(["Date", "Total", "Top_Count", "Top_Tickers", "Report"])
            
            top_picks = report.get('final_execution_orders', [])
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                len(top_picks),
                ", ".join([p['ticker'] for p in top_picks]),
                report.get('ceo_report', 'N/A')
            ]
            sheet.append_row(row)
            print("✅ [SENIOR] Strategy Brief Logged.")
            return
        except Exception as e:
            print(f"⚠️ Senior Log Error: {e}")
            time.sleep(5)

def log_detailed_decisions(decision_data, holdings_map=None):
    """
    NEW: Logs every individual trade recommendation to a structured 'Senior_Decisions' tab.
    Acts as a database for performance tracking.
    """
    if holdings_map is None: holdings_map = {}
    
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return
            sh = client.open(SHEET_NAME)
            
            # 1. Get/Create Tab
            try: 
                sheet = sh.worksheet("Senior_Decisions")
            except: 
                sheet = sh.add_worksheet(title="Senior_Decisions", rows="2000", cols="9")
                sheet.append_row([
                    "Date", "Ticker", "Rank", "Action", "Reasoning", 
                    "Buy_Limit", "Take_Profit", "Stop_Loss", "Shares_Held"
                ])
            
            # 2. Parse & Append Rows
            orders = decision_data.get('final_execution_orders', [])
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            for order in orders:
                ticker = order.get('ticker')
                params = order.get('confirmed_params', {})
                
                row = [
                    timestamp,
                    ticker,
                    order.get('rank'),
                    order.get('action'),
                    order.get('reason'),
                    params.get('buy_limit', 0),
                    params.get('take_profit', 0),
                    params.get('stop_loss', 0),
                    holdings_map.get(ticker, 0) # Log how many we held at this moment
                ]
                sheet.append_row(row)
                
            print(f"✅ [SENIOR] Detailed Ledger Updated ({len(orders)} rows).")
            return

        except Exception as e:
            print(f"⚠️ Ledger Log Error (Attempt {attempt+1}): {e}")
            time.sleep(5)



def log_trade_event(ticker, event_type, details):
    """
    Logs concrete broker actions (Orders Placed, Updated, Rejected).
    Tab: 'Trade_Log'
    """
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return
            sh = client.open(SHEET_NAME)
            
            # 1. Get/Create Tab
            try: 
                sheet = sh.worksheet("Trade_Log")
            except: 
                sheet = sh.add_worksheet(title="Trade_Log", rows="5000", cols="8")
                sheet.append_row([
                    "Timestamp", "Ticker", "Event", "Qty", "Price/Limit", 
                    "Stop_Loss", "Take_Profit", "Order_ID / Details"
                ])
            
            # 2. Format Data
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ticker,
                event_type,              # e.g., "NEW_ENTRY", "UPDATE_SL"
                details.get('qty', '-'),
                details.get('price', '-'),
                details.get('stop_loss', '-'),
                details.get('take_profit', '-'),
                str(details.get('order_id', details.get('info', '')))
            ]
            
            sheet.append_row(row)
            print(f"✅ [HISTORY] Trade Event Logged: {event_type} for {ticker}")
            return

        except Exception as e:
            print(f"⚠️ Trade Log Error (Attempt {attempt+1}): {e}")
            time.sleep(2)