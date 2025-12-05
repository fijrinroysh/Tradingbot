import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json

# Define the scope
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']

# Load credentials securely (from env or file)
# For Render, you will paste the content of google_credentials.json into an Environment Variable
def get_client():
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    
    if creds_json:
        # Load from Render Environment Variable
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        # Load from local file (for testing)
        if os.path.exists("google_credentials.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("google_credentials.json", scope)
        else:
            print("History Manager Warning: No Google Sheets credentials found. History will be lost.")
            return None
            
    return gspread.authorize(creds)

SHEET_NAME = "TradingBot_History"
COOLDOWN_DAYS = 7 

def load_history():
    """Reads the history from Google Sheets."""
    client = get_client()
    if not client: return {}
    
    try:
        sheet = client.open(SHEET_NAME).sheet1
        records = sheet.get_all_records() # Returns list of dicts: [{'Ticker': 'AAPL', 'Date_Analyzed': '2023-10-20'}, ...]
        
        # Convert to dictionary format: {'AAPL': '2023-10-20'}
        history = {}
        for row in records:
            history[row['Ticker']] = row['Date_Analyzed']
        return history
    except Exception as e:
        print(f"History Manager Error: {e}")
        return {}

def mark_as_analyzed(ticker):
    """Adds or updates a ticker in Google Sheets."""
    client = get_client()
    if not client: return
    
    try:
        sheet = client.open(SHEET_NAME).sheet1
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Check if ticker exists to update it, or append new row
        # (For simplicity, we'll just append. You can clean up the sheet manually occasionally)
        row = [ticker, today]
        sheet.append_row(row)
        print(f"History Manager: Marked {ticker} as analyzed in Google Sheets.")
    except Exception as e:
        print(f"History Manager Error saving {ticker}: {e}")

def filter_candidates(candidates, daily_limit):
    """
    Returns tickers that haven't been analyzed recently, up to the limit.
    """
    history = load_history()
    valid_candidates = []
    now = datetime.now()
    
    print(f"History Manager: Checking {len(candidates)} candidates against Google Sheets history...")
    
    for ticker in candidates:
        last_scan_str = history.get(ticker)
        
        if last_scan_str:
            try:
                last_scan_date = datetime.strptime(last_scan_str, "%Y-%m-%d")
                if (now - last_scan_date).days < COOLDOWN_DAYS:
                    continue # Skip
            except ValueError:
                pass
        
        valid_candidates.append(ticker)
        if len(valid_candidates) >= daily_limit:
            break
            
    print(f"History Manager: Selected {len(valid_candidates)} fresh tickers for analysis.")
    return valid_candidates