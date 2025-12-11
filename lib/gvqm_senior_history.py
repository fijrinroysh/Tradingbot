import gspread
from google.oauth2.service_account import Credentials
import config
import datetime
import json
import os
import time

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# 1. PARAMETERIZED SHEET NAME
SHEET_NAME = getattr(config, 'GOOGLE_SHEET_NAME', "TradingBot_History")

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


def clean_score(value):
    try:
        if isinstance(value, str): value = value.replace('%', '').strip()
        if not value: return 0
        return int(float(value))
    except: return 0

# --- 2. ROBUST FETCHING (NO SPLITTING) ---
def fetch_junior_reports(lookback_days=10):
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return []
            
            sheet = client.open(SHEET_NAME).sheet1
            raw_records = sheet.get_all_records()
            
            clean_records = []
            today = datetime.date.today()
            limit_date = today - datetime.timedelta(days=lookback_days)

            print(f"   📚 [HISTORY] Scanning {len(raw_records)} rows from Sheets...")

            for row in raw_records:
                raw_score = row.get('Score', 0)
                score = clean_score(raw_score)
                ticker = row.get('Ticker', '').upper().strip()
                
                # --- DATE HANDLING (AS IS) ---
                date_str = str(row.get('Date', '')) # e.g. "2025-12-09 21:47"
																	 

                if not ticker or score == 0: continue

                try:
                    if date_str:
                        # Parse the full format directly
                        report_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                        if report_dt.date() < limit_date: continue 
                except: continue 

                # Full Fidelity Data
                clean_records.append({
                    "ticker": ticker,
                    "report_date": date_str, # Keep original format
                    "conviction_score": score,
                    "sector": row.get('Sector', ''),
                    "recommended_action": row.get('Action', ''),
                    "status": row.get('Status', ''),
                    "status_reason": row.get('Status_Reason', ''),
                    "valuation": row.get('Valuation', ''),
                    "valuation_reason": row.get('Valuation_Reason', ''),
                    "rebound_potential": row.get('Rebound', ''),
                    "rebound_reason": row.get('Rebound_Reason', ''),
                    "catalyst": row.get('Catalyst', ''),
                    "intel": row.get('Intel', ''),
                    "junior_targets": {
                        "buy_limit": row.get('Buy_Limit', 0),
                        "take_profit": row.get('Take_Profit', 0),
                        "stop_loss": row.get('Stop_Loss', 0)
                    }
                })
            print(f"   ✅ Found {len(clean_records)} valid reports.")
            return clean_records

        except Exception as e:
            print(f"   ⚠️ Fetch Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)
            
    return []

# --- 3. STRATEGY LOGGING (YYYY-MM-DD HH:MM) ---
def log_strategy(decision):
												  
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return
            
            sh = client.open(SHEET_NAME)
            try: sheet = sh.worksheet("Executive_Briefs")
            except: 
                sheet = sh.add_worksheet(title="Executive_Briefs", rows=1000, cols=10)
                sheet.append_row(["Date", "Total", "Top_Count", "Top_Tickers", "CEO_Report"])
                
            trades = decision.get('final_execution_orders', [])
            trades_summary = ", ".join([f"{t.get('action')} {t.get('ticker')}" for t in trades])
            
            # --- STANDARDIZED TIMESTAMP ---
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            
            row = [
                timestamp,
                len(trades),
                trades_summary,
                decision.get('ceo_report', 'N/A')
            ]
            sheet.append_row(row)
            print("   ✅ [SENIOR] Strategy Brief Logged.")
            return
        except Exception as e:
            print(f"   ⚠️ Strategy Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)

# --- 4. DETAILED LOGGING (YYYY-MM-DD HH:MM) ---
def log_detailed_decisions(decision_data, holdings_map=None):
    if holdings_map is None: holdings_map = {}
    
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return
            sh = client.open(SHEET_NAME)
            
            try: sheet = sh.worksheet("Senior_Decisions")
            except: 
                sheet = sh.add_worksheet(title="Senior_Decisions", rows=2000, cols=10)
                sheet.append_row(["Date", "Ticker", "Rank", "Action", "Reason", "Buy_Limit", "Take_Profit", "Stop_Loss", "Shares_Held"])
            
            orders = decision_data.get('final_execution_orders', [])
            
            # --- STANDARDIZED TIMESTAMP ---
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            
            for order in orders:
                ticker = order.get('ticker')
                params = order.get('confirmed_params', {})
                
                row = [
                    timestamp,
                    ticker,
                    order.get('rank', 0),
                    order.get('action', 'HOLD'),
                    order.get('reason', 'N/A'),
                    params.get('buy_limit', 0),
                    params.get('take_profit', 0),
                    params.get('stop_loss', 0),
                    holdings_map.get(ticker, 0)
                ]
                sheet.append_row(row)
                
            print(f"   ✅ [SENIOR] Detailed Ledger Updated ({len(orders)} rows).")
            return

        except Exception as e:
            print(f"   ⚠️ Ledger Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)

# --- 5. TRADE LOGGING (YYYY-MM-DD HH:MM) ---
def log_trade_event(ticker, event_type, details):
    for attempt in range(3):
							 
							 
        try:
            client = get_client()
            if not client: return
																										  
																													 
		
																   
																									 
									 
										  
											
									  
																		 
            
            sh = client.open(SHEET_NAME)
            try: sheet = sh.worksheet("Trade_Log")
            except:
                sheet = sh.add_worksheet(title="Trade_Log", rows=1000, cols=10)
                sheet.append_row(["Timestamp", "Ticker", "Event", "Qty", "Price", "Stop_Loss", "Take_Profit", "Details"])
            
            # --- STANDARDIZED TIMESTAMP ---
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            
            price = details.get('price') or details.get('buy_limit') or details.get('limit_price') or '-'
            qty = details.get('qty', '-')
            sl = details.get('stop_loss', '-')
            tp = details.get('take_profit', '-')
            info = details.get('info', '')
            if 'order_id' in details: info += f" | ID: {details['order_id']}"
                
            row = [now, ticker, event_type, qty, price, sl, tp, info]
            sheet.append_row(row)
            print(f"   ✅ [HISTORY] Trade Event Logged: {event_type} for {ticker}")
            return
        except Exception as e:
            print(f"   ⚠️ Trade Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)

# --- 6. MEMORY RECALL ---
def get_last_strategy():
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return None
            
            sheet = client.open(SHEET_NAME).worksheet("Executive_Briefs")
            records = sheet.get_all_records()
            
            if records:
                last_row = records[-1]
                return {
                    "date": last_row.get("Date", "Unknown"),
                    "top_tickers": last_row.get("Top_Tickers", "None"),
                    "ceo_report": last_row.get("CEO_Report") or last_row.get("Report", "None")
                }
            return None
        except Exception as e:
            if attempt == 2: print(f"   ⚠️ Memory Recall Error: {e}")
            time.sleep(2)
            
    return None
