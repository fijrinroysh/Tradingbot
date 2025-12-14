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

# --- 2. ROBUST FETCHING (RETRY + SORT + DEDUPLICATE) ---
def fetch_junior_reports(lookback_days=10):
    """
    Fetches reports with 3 layers of robustness:
    1. RETRY: Tries 3 times if connection fails.
    2. SORT: Sorts by Date (Newest First) in memory.
    3. DEDUPLICATE: Keeps only the latest entry per ticker.
    """
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return []
            
            sheet = client.open(SHEET_NAME).sheet1
            raw_records = sheet.get_all_records()
            
            # --- HELPER: Safe Date Parsing for Sorting ---
            def get_date_object(record):
                date_str = str(record.get('Date', '')).split(' ')[0]
                try:
                    return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                except:
                    return datetime.date(1900, 1, 1) # Drop bad dates to bottom

            # --- STEP 1: SORT IN MEMORY (Newest First) ---
            print(f"   📚 [HISTORY] Sorting {len(raw_records)} records by Date (Attempt {attempt+1})...")
            sorted_records = sorted(raw_records, key=get_date_object, reverse=True)

            clean_records = []
            seen_tickers = set()
            
            today = datetime.date.today()
            limit_date = today - datetime.timedelta(days=lookback_days)

            # --- STEP 2: FILTER & DEDUPLICATE ---
            for row in sorted_records:
                ticker = row.get('Ticker', '').upper().strip()
                
                # Deduplication: If we already saw this ticker (which was newer), skip this old one.
                if ticker in seen_tickers:
                    continue

								   
                raw_score = row.get('Score', 0)
                score = clean_score(raw_score)
															  
				
											   
                date_str = str(row.get('Date', ''))
				  

                if not ticker or score == 0: continue

                try:
                    # Parse the full format directly for validation
                    if date_str:
														
                        report_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                        if report_dt.date() < limit_date: continue 
                except: continue 

                # Mark as seen so we don't add older duplicates
                seen_tickers.add(ticker)

                # Full Fidelity Data
                clean_records.append({
                    "ticker": ticker,
                    "report_date": date_str,
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
            
            print(f"   ✅ Found {len(clean_records)} unique, valid reports.")
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


# --- 6. MEMORY RECALL (ROBUST SORTING) ---
def get_last_strategy():
    """
    Fetches the most recent executive brief.
    Fix: Does NOT assume the last row is the latest.
    explicitly parses 'Date' column and sorts Descending.
    """
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return None
            
            # Open Sheet
            try:
                sheet = client.open(SHEET_NAME).worksheet("Executive_Briefs")
            except:
                return None # Worksheet doesn't exist yet
                
            records = sheet.get_all_records()
            if not records: return None

            # --- HELPER: Parse Timestamp ---
            def parse_strat_date(row):
                d_str = str(row.get('Date', ''))
                # Handle cases where Google Sheets might return different formats
                try:
                    # Format used in log_strategy: "2025-12-14 14:30"
                    return datetime.datetime.strptime(d_str, "%Y-%m-%d %H:%M")
                except:
                    try:
                        # Fallback for date only
                        return datetime.datetime.strptime(d_str, "%Y-%m-%d")
                    except:
                        # Push bad data to the bottom (year 1900)
                        return datetime.datetime(1900, 1, 1)

            # --- SORT DESCENDING (Newest First) ---
            # This ensures we get the true latest run, even if sheet rows are jumbled
            sorted_records = sorted(records, key=parse_strat_date, reverse=True)
            
            # Grab the top record
            last_run = sorted_records[0]
            
            return {
                "date": last_run.get("Date", "Unknown"),
                "top_tickers": last_run.get("Top_Tickers", "None"),
                "ceo_report": last_run.get("CEO_Report") or last_run.get("Report", "None")
            }

        except Exception as e:
            if attempt == 2: print(f"   ⚠️ Memory Recall Error: {e}")
            time.sleep(2)
            
    return None
