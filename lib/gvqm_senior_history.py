import gspread
from google.oauth2.service_account import Credentials
import config
import datetime
import json
import os
import time

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

							  
SHEET_NAME = getattr(config, 'GOOGLE_SHEET_NAME', "TradingBot_History")

STRATEGY_TAB_NAME = getattr(config, 'GOOGLE_SHEET_STRATEGY_TAB', "Strategy_Brief")
				   
SENIOR_DECISIONS_TAB = getattr(config, 'GOOGLE_SHEET_SENIOR_DECISIONS_TAB', "Senior_Decisions")
   


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


def clean_score(value):
		
    try: return int(float(str(value).replace('%', '').strip())) if value else 0
							  
								
    except: return 0

						   
def safe_read_sheet(worksheet):
	
			
				  
	
    try:
        raw_data = worksheet.get_all_values()
        if not raw_data: return []

        headers = raw_data[0]
		   
        clean_headers = []
        counts = {}
		
        for h in headers:
            h_str = str(h).strip()
			 
            if not h_str: h_str = "Unknown"
			
            if h_str in counts:
                counts[h_str] += 1
                clean_headers.append(f"{h_str}_{counts[h_str]}")
            else:
                counts[h_str] = 0
                clean_headers.append(h_str)

        records = []
        for row in raw_data[1:]:
				  
											 
            if len(row) < len(clean_headers): row += [''] * (len(clean_headers) - len(row))
	   
            records.append(dict(zip(clean_headers, row)))
			
        return records
    except Exception as e:
        print(f"⚠️ Safe Read Error: {e}")
        return []

# --- ROBUST DATE PARSER (CRITICAL FIX) ---
def robust_parse_date(date_str):
    date_str = str(date_str).strip()
    if not date_str: return datetime.datetime(1900, 1, 1)
    formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y %H:%M", "%m/%d/%Y"]
    for fmt in formats:
        try: return datetime.datetime.strptime(date_str, fmt)
        except ValueError: continue
    return datetime.datetime(1900, 1, 1)

# --- FUNCTIONS ---

def fetch_junior_reports(lookback_days=10):
	
			
			
			 
				 
	
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return []
			
            sheet = client.open(SHEET_NAME).sheet1
				 
            raw_records = safe_read_sheet(sheet)
            
            # Sort by Date Descending
										
																	
					
																				  
					   
													

				 
							 
            sorted_records = sorted(raw_records, key=lambda x: robust_parse_date(x.get('Date', '')), reverse=True)
            
            clean_records = []
            seen_tickers = set()
			
										 
            limit_date = datetime.datetime.now() - datetime.timedelta(days=lookback_days)

			  
            for row in sorted_records:
                ticker = row.get('Ticker', '').upper().strip()
	
						 
                if ticker in seen_tickers: continue
	   

  
                score = clean_score(row.get('Score', 0))
											  
 
 
  
                date_obj = robust_parse_date(row.get('Date', ''))
                

                if not ticker or score == 0 or date_obj < limit_date: continue

					
				   
								
  
																						  
																   
								 

				  
                seen_tickers.add(ticker)
                
		 
                clean_records.append({
                    "ticker": ticker,
                    "report_date": date_obj.strftime("%Y-%m-%d %H:%M"),
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

							 
def log_strategy(decision):
	
					 
	
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return
			
            sh = client.open(SHEET_NAME)
				 
            try: sheet = sh.worksheet(STRATEGY_TAB_NAME)
            except: 
			 
                sheet = sh.add_worksheet(title=STRATEGY_TAB_NAME, rows=1000, cols=10)
                sheet.append_row(["Date", "Total", "Top_Count", "Report"])
            
            trades = decision.get('final_execution_orders', [])
            trades_summary = ", ".join([f"{t.get('action')} {t.get('ticker')}" for t in trades])
   
  
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
			
	   
		
	   
		  
            sheet.append_row([timestamp, len(trades), trades_summary, decision.get('ceo_report', 'N/A')])
	
								 
            print(f"   ✅ [SENIOR] Strategy Brief Logged to '{STRATEGY_TAB_NAME}'.")
            return
        except Exception as e:
            print(f"   ⚠️ Strategy Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)

							 
def log_detailed_decisions(decision_data, holdings_map=None):
    if holdings_map is None: holdings_map = {}
	
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return
            sh = client.open(SHEET_NAME)
			
		 
					   
															  
																	   
            headers = ["Date", "Ticker", "Rank", "Action", "Reason", "Buy_Limit", "Take_Profit", "Stop_Loss", "Shares_Held", "Justification_Safe", "Justification_Bargain", "Justification_Rebound"]
			 

				   
							 

            try: sheet = sh.worksheet(SENIOR_DECISIONS_TAB)
            except: 
			
                sheet = sh.add_worksheet(title=SENIOR_DECISIONS_TAB, rows=2000, cols=15)
                sheet.append_row(headers)
            
            orders = decision_data.get('final_execution_orders', [])
   
  
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            
            for order in orders:
                ticker = order.get('ticker')
                p = order.get('confirmed_params', {})
	
			 
															 
																   
																   

                row = [
                    timestamp, ticker, order.get('rank', 0), order.get('action', 'HOLD'), order.get('reason', 'N/A'),
		 
		   
			
			  
			  
                    p.get('buy_limit', 0), p.get('take_profit', 0), p.get('stop_loss', 0),
			  
                    holdings_map.get(ticker, 0),
                    order.get('justification_safe', '-'), order.get('justification_bargain', '-'), order.get('justification_rebound', '-')
		 
		 
		
                ]
                sheet.append_row(row)
				
            print(f"   ✅ [SENIOR] Detailed Ledger Updated ({len(orders)} rows).")
            return

        except Exception as e:
            print(f"   ⚠️ Ledger Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)

						  
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
            row = [now, ticker, event_type, details.get('qty', '-'), price, details.get('stop_loss', '-'), details.get('take_profit', '-'), details.get('info', '')]
											  
												
										  
																			 
				
																	 
            sheet.append_row(row)
            print(f"   ✅ [HISTORY] Trade Event Logged: {event_type} for {ticker}")
            return
        except Exception as e:
            print(f"   ⚠️ Trade Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)


						  
def get_last_strategy():
	   
												  
													  
			   
	   
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return None
			
			   
				
            try: sheet = client.open(SHEET_NAME).worksheet(STRATEGY_TAB_NAME)
				   
            except: return None 
				
				 
            records = safe_read_sheet(sheet)
            if not records: return None

			
									  
												
					 
	 
	  
																			   
					   
	  
   
																			 
		 
	 
																

			 
					  
            sorted_records = sorted(records, key=lambda x: robust_parse_date(x.get('Date', '')), reverse=True)
			
   
            for record in sorted_records:
                report_val = record.get('Report')
                if not report_val:
                    for key, val in record.items():
                        if "ceo" in str(key).lower() or "report" in str(key).lower():
                            report_val = val
                            break
                if report_val and len(str(report_val).strip()) > 10 and "N/A" not in str(report_val):
                    print(f"   ✅ [MEMORY] Found valid strategy from {record.get('Date', 'Unknown')}")
                    return {
                        "date": record.get("Date", "Unknown"),
                        "top_tickers": record.get("Top_Count", "None"), # Mapped to schema
                        "ceo_report": report_val
                    }
            return None
        except Exception as e:
            if attempt == 2: print(f"   ⚠️ Memory Recall Error: {e}")
            time.sleep(2)
   
    return None

													
def fetch_latest_ranks():
	   
							 
						
								
														  
	   
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return {}
			

			
	
            try: sheet = client.open(SHEET_NAME).worksheet(SENIOR_DECISIONS_TAB)
	   
            except: return {} 
			
				 
            records = safe_read_sheet(sheet)
            if not records: return {}

													
										 
												
																			   
															

											   
	   
            sorted_records = sorted(records, key=lambda x: robust_parse_date(x.get('Date', '')), reverse=True)
		  
			
		  
																								 
			
			   
            rank_map = {}
			
													 
            for r in sorted_records:
                ticker = r.get('Ticker')
                rank = r.get('Rank')
				
																			 
                if ticker and ticker not in rank_map:
						
	   
                    try: rank_map[ticker] = int(float(rank)) if rank else 99
													 
                    except: pass
									   
			
            return rank_map

        except Exception as e:
            print(f"   ⚠️ Memory Fetch Error: {e}")
            time.sleep(1)
			
    return {}