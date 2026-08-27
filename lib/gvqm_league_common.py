import gspread
from google.oauth2.service_account import Credentials
import os
import json
import config

# --- SETUP ---
SHEET_NAME = getattr(config, 'GOOGLE_SHEET_NAME', "TradingBot_History")
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def get_client():
    """Authenticates and connects to Google Sheets."""
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        if os.path.exists("google_credentials.json"):
            try: 
                creds_json = open("google_credentials.json").read()
            except: 
                return None
        else: 
            return None
            
    try:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"⚠️ [COMMON] Auth Error: {e}")
        return None


def update_active_contenders_flag(tab_name, todays_active_tickers, wipe_inactive_elo=False):
    """
    The Smart Bouncer: Updates the 'Active_Contenders' flag incrementally.
    If wipe_inactive_elo is True (Major League), it also resets demoted stocks to 1500.
    If False (Minor League), it preserves historical Elo scores for inactive stocks.
    """
    print(f"📋 Checking active contenders on the {tab_name} tab...")
    client = get_client()
    if not client: return
    
    sheet = client.open(SHEET_NAME)
    worksheet = sheet.worksheet(tab_name)
    
    headers = worksheet.row_values(1)
    
    # 1. Setup the VIP Badge Column (Active_Contenders)
    status_col_name = "Active_Contenders"
    if status_col_name not in headers:
        headers.append(status_col_name)
        worksheet.update('1:1', [headers]) 
        status_col_index = len(headers) 
    else:
        status_col_index = headers.index(status_col_name) + 1 
    col_letter_status = chr(64 + status_col_index)

    # 2. Setup the Stats Column (Elo_Rating)
    elo_col_name = "Elo_Rating"
    if elo_col_name in headers:
        elo_col_index = headers.index(elo_col_name) + 1
    else:
        headers.append(elo_col_name)
        worksheet.update('1:1', [headers])
        elo_col_index = len(headers)
    col_letter_elo = chr(64 + elo_col_index)

    # 3. Download the data
    all_data = worksheet.get_all_records()
    updates = []
    
    # 4. Check each stock to see if they need an update
    for row_index, row_data in enumerate(all_data):
        ticker = row_data.get("Ticker", "")
        current_status = str(row_data.get(status_col_name, "")).strip().upper()
        
        try:
            current_elo = float(row_data.get(elo_col_name, 1500))
        except ValueError:
            current_elo = 1500.0

        actual_sheet_row = row_index + 2 
        
        # 🟢 SCENARIO A: The VIPs (Active Stocks)
        if ticker in todays_active_tickers:
            if current_status != 'Y':
                updates.append({
                    'range': f"{col_letter_status}{actual_sheet_row}",
                    'values': [['Y']]
                })
                
        # 🔴 SCENARIO B: The Inactive Stocks
        else:
            # 1. Always update the badge if it's wrong
            if current_status != 'N':
                updates.append({
                    'range': f"{col_letter_status}{actual_sheet_row}",
                    'values': [['N']]
                })
                
            # 2. ONLY wipe the score if the toggle is flipped ON
            if wipe_inactive_elo and current_elo != 1500.0:
                updates.append({
                    'range': f"{col_letter_elo}{actual_sheet_row}",
                    'values': [[1500.0]]
                })
        
    # 5. Upload fixes
    if updates:
        worksheet.batch_update(updates)
        print(f"✅ Incremental clean-up complete! Pushed {len(updates)} specific updates to {tab_name}.")
    else:
        print(f"✅ No updates needed! The {tab_name} locker room is perfectly synced.")