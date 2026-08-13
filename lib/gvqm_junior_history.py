import gspread
from google.oauth2.service_account import Credentials
import datetime
import os
import json
import config
import time

SHEET_NAME = getattr(config, 'GOOGLE_SHEET_NAME', "TradingBot_History")
JUNIOR_TAB_NAME = "Junior_Decisions"

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

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
        print(f"⚠️ [JUNIOR HISTORY] Auth Error: {e}")
        return None

# ==========================================
# 📤 WRITING (JUNIOR SCOUTING REPORTS)
# ==========================================
def log_report(winner_ticker, analysis, opponent="Unknown"):
    """
    Logs the 4-column Junior Scout report: Date, Matchup, Winner, Rationale.
    Matches the Senior Decisions symmetry.
    """
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return

            sh = client.open(SHEET_NAME)
            
            # 💡 SYMMETRY: Using the same 4 headers as Senior_Decisions
            headers = ["Date", "Matchup", "Winner", "Rationale"]
            
            try: 
                sheet = sh.worksheet(JUNIOR_TAB_NAME)
            except: 
                sheet = sh.add_worksheet(title=JUNIOR_TAB_NAME, rows=1000, cols=4)
                sheet.append_row(headers)

            # Check if headers exist or need updating from 3-cols to 4-cols
            first_row = sheet.row_values(1)
            if not first_row or len(first_row) < 4:
                sheet.insert_row(headers, index=1)

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            matchup_str = f"{winner_ticker} vs {opponent}"
            rationale = analysis.get("rationale", "No rationale provided.")

            sheet.append_row([timestamp, matchup_str, winner_ticker, rationale])
            
            print(f"   ✅ [HISTORY] Logged Junior Matchup: {matchup_str}.")
            return

        except Exception as e:
            print(f"⚠️ Junior History Log Error (Attempt {attempt+1}/3): {e}")
            time.sleep(2)

# ==========================================
# 🗂️ THE PRIORITY QUEUE (Staleness Filter)
# ==========================================
def filter_candidates(distressed_tickers, limit=20):
    """
    Acts as a Priority Queue. 
    Reads the 'Last_Match' date directly from the Minor League Elo Scoreboard
    so BOTH winners and losers get their staleness accurately tracked.

    It ensures that fresh stocks and stocks that haven't been checked in a long time get priority, 
    while preventing the bot from looking at the exact same stocks day after day.
    """
    import lib.gvqm_minor_league as minor_league 
    
    try:
        leaderboard = minor_league.fetch_leaderboard("Junior_Elo")
        
        last_played_map = {}
        if leaderboard:
            for t, stats in leaderboard.items():
                date_str = stats.get('Last_Match', '')
                if date_str:
                    last_played_map[t] = date_str
                    
    except Exception as e:
        print(f"   ⚠️ [JUNIOR HISTORY] Could not read Elo staleness. Defaulting to raw list. Error: {e}")
        return distressed_tickers[:limit]

    prioritized_list = []
    
    for t in distressed_tickers:
        if t not in last_played_map:
            # PRIORITY 1: ROOKIE 
            prioritized_list.append({'ticker': t, 'last_played': '1900-01-01'})
        else:
            # PRIORITY 2/3: VETERAN 
            prioritized_list.append({'ticker': t, 'last_played': last_played_map[t]})
            
    prioritized_list.sort(key=lambda x: x['last_played'])
    drafted_tickers = [item['ticker'] for item in prioritized_list[:limit]]
    
    return drafted_tickers


import io
import json
# ==========================================
# 🧠 GOOGLE SHEETS MEMORY BANK (JSON IN A CELL)
# ==========================================
def load_history_from_sheets():
    """Downloads the memory bank from a dedicated tab in Google Sheets."""
    client = get_client() # Uses your existing gspread authentication!
    if not client: return {}

    try:
        sheet = client.open(SHEET_NAME)
        # Try to find the Junior_Memory_Bank tab, create it if it doesn't exist
        try:
            worksheet = sheet.worksheet("Junior_Memory_Bank")
        except:
            print("☁️ [MEMORY] Creating new 'Junior_Memory_Bank' tab in Google Sheets...")
            worksheet = sheet.add_worksheet(title="Junior_Memory_Bank", rows="10", cols="5")
        
        # Read the JSON string from Cell A1
        val = worksheet.acell('A1').value
        if val:
            return json.loads(val)
        return {}
    except Exception as e:
        print(f"⚠️ [MEMORY] Failed to load memory from sheets: {e}")
        return {}

def save_history_to_sheets(data):
    """Uploads the updated memory bank back to Cell A1 in Google Sheets."""
    client = get_client()
    if not client: return

    try:
        sheet = client.open(SHEET_NAME)
        try:
            worksheet = sheet.worksheet("Junior_Memory_Bank")
        except:
            worksheet = sheet.add_worksheet(title="Junior_Memory_Bank", rows="10", cols="5")
        
        # Convert dictionary to string and dump it into Cell A1
        json_str = json.dumps(data)
        worksheet.update('A1', [[json_str]])
    except Exception as e:
        print(f"⚠️ [MEMORY] Failed to save memory to sheets: {e}")

def update_active_contenders_flag(tab_name, todays_active_tickers):
    """
    Looks at the Master ELO tab, finds (or creates) the 'Active_Contender' column, 
    and updates the active status (Y/N) for all stocks at once.
    """
    print(f"📋 Updating active contenders on the {tab_name} tab...")
    client = get_client()
    if not client: return
    
    sheet = client.open(SHEET_NAME)
    worksheet = sheet.worksheet(tab_name)
    
    # 1. Look at the very top row (The Headers)
    headers = worksheet.row_values(1)
    target_col_name = "Active_Contenders"
    
    # 2. Check if our column exists. If not, add it!
    if target_col_name not in headers:
        print(f"   ⚠️ '{target_col_name}' column missing. Adding it now...")
        headers.append(target_col_name)
        # Update row 1 with the new header list
        worksheet.update('1:1', [headers]) 
        # The new column is at the very end
        col_index = len(headers) 
    else:
        # Find exactly where it is (Add 1 because Google Sheets starts counting at 1, not 0)
        col_index = headers.index(target_col_name) + 1 
        
    # Convert the column number to a letter (e.g., 1 = A, 2 = B, ... 7 = G)
    # Note: chr(65) is 'A' in computer logic, so we add 64 to our index!
    col_letter = chr(64 + col_index)

    # 3. Download the rest of the data so we know who is on the list
    all_data = worksheet.get_all_records()
    
    updates = []
    
    # 4. Go row by row and hand out the 'Y' and 'N' badges
    for row_index, row_data in enumerate(all_data):
        ticker = row_data.get("Ticker", "")
        
        if ticker in todays_active_tickers:
            new_status = 'Y'
        else:
            new_status = 'N'
            
        # Add 2 because row 1 is the header, and data starts on row 2
        actual_sheet_row = row_index + 2 
        
        # Now it dynamically builds the exact cell (e.g., "G2", "H3", etc.)
        cell_to_update = f"{col_letter}{actual_sheet_row}" 
        
        updates.append({
            'range': cell_to_update,
            'values': [[new_status]]
        })
        
    # 5. Upload all the badges back to Google Sheets in one giant batch!
    if updates:
        worksheet.batch_update(updates)
        print(f"✅ Active contenders successfully updated in column '{col_letter}' on the {tab_name} tab!")