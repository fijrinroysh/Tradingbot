import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json

SHEET_NAME = "TradingBot_History"
COOLDOWN_DAYS = 10 

def get_client():
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        if os.path.exists("google_credentials.json"):
            creds_json = open("google_credentials.json").read()
        else:
            return None
    
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(creds_json), scope)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"⚠️ [HISTORY] Auth Error: {e}")
        return None

# --- NEW LOGGING FUNCTION ---
def log_decision_to_sheet(ticker, analysis, trade_status, trade_details):
    """
    Logs the full analysis and execution result to Google Sheets.
    """
    client = get_client()
    if not client: return

    try:
        sheet = client.open(SHEET_NAME).sheet1
        
        # 1. Check/Create Headers if empty
        if sheet.row_count < 1 or not sheet.row_values(1):
            headers = [
                "Date", "Ticker", "Action", "Status", "Valuation", 
                "Rebound", "Confidence", "Reasoning", "Intel",
                "Buy_Limit", "Take_Profit", "Stop_Loss",
                "Execution_Status", "Shares", "Est_Cost"
            ]
            sheet.append_row(headers)

        # 2. Prepare Data Row
        exec_plan = analysis.get('execution', {})
        
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M"),  # 1. Date
            ticker,                                     # 2. Ticker
            analysis.get('action', 'N/A'),              # 3. Action
            analysis.get('status', 'N/A'),              # 4. Status
            analysis.get('valuation', 'N/A'),           # 5. Valuation
            analysis.get('rebound_potential', 'N/A'),   # 6. Rebound
            analysis.get('confidence', 'N/A'),          # 7. Confidence
            analysis.get('reasoning', 'N/A'),           # 8. Reasoning
            analysis.get('intel', 'N/A'),               # 9. Intel
            exec_plan.get('buy_limit', 0),              # 10. Buy Price
            exec_plan.get('take_profit', 0),            # 11. TP
            exec_plan.get('stop_loss', 0),              # 12. SL
            trade_status,                               # 13. Exec Status (e.g., "FILLED")
            trade_details.get('qty', 0),                # 14. Shares
            trade_details.get('cost', 0)                # 15. Cost
        ]
        
        # 3. Append
        sheet.append_row(row)
        print(f"✅ [HISTORY] Logged {ticker} decision to Google Sheet.")

    except Exception as e:
        print(f"⚠️ [HISTORY] Log Error: {e}")
# ----------------------------

def filter_candidates(candidates, daily_limit):
    client = get_client()
    if not client: return candidates[:daily_limit]

    print(f"📚 [HISTORY] Checking {len(candidates)} candidates against database...")
    try:
        sheet = client.open(SHEET_NAME).sheet1
        records = sheet.get_all_values()
        # Ticker is Col 2 (index 1), Date is Col 1 (index 0)
        # We scan the sheet to find the last time we checked this ticker
        history_map = {}
        for row in records[1:]: # Skip header
            if len(row) > 1:
                # Keep updating so we get the LATEST date
                history_map[row[1]] = row[0].split(" ")[0] 
    except:
        history_map = {}

    valid_candidates = []
    now = datetime.now()

    for ticker in candidates:
        last_date_str = history_map.get(ticker)
        if last_date_str:
            try:
                last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
                if (now - last_date).days < COOLDOWN_DAYS:
                    continue 
            except: pass
        
        valid_candidates.append(ticker)
        if len(valid_candidates) >= daily_limit: break
    
    print(f"✅ [HISTORY] Approved {len(valid_candidates)} fresh tickers.")
    return valid_candidates

def mark_as_analyzed(ticker):
    # We don't need a separate simple logger anymore since 
    # log_decision_to_sheet handles the full record.
    pass