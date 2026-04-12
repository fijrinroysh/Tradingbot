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
def log_report(winner_ticker, analysis):
    """
    Logs the simplified Junior Scout report (Winner and Rationale).
    """
    for attempt in range(3):
        try:
            client = get_client()
            if not client: return

            sh = client.open(SHEET_NAME)
            try: 
                sheet = sh.worksheet(JUNIOR_TAB_NAME)
            except: 
                sheet = sh.add_worksheet(title=JUNIOR_TAB_NAME, rows=1000, cols=3)

            # Check if headers exist
            if sheet.row_count < 1 or not sheet.row_values(1):
                sheet.append_row(["Date", "Winner_Chosen", "Scout_Rationale"])

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            rationale = analysis.get("rationale", "No rationale provided.")

            sheet.append_row([timestamp, winner_ticker, rationale])
            
            print(f"   ✅ [HISTORY] Logged Scout Report for {winner_ticker}.")
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
    """
    # Import locally to avoid circular import issues
    import lib.gvqm_minor_league as minor_league 
    
    try:
        # 1. Fetch the entire Minor League leaderboard
        leaderboard = minor_league.fetch_leaderboard("Junior_Elo")
        
        # 2. Build the "Last Played" map: {'AAPL': '2023-10-25', 'TSLA': '2023-10-20'}
        last_played_map = {}
        if leaderboard:
            for t, stats in leaderboard.items():
                date_str = stats.get('Last_Match', '')
                if date_str:
                    last_played_map[t] = date_str
                    
    except Exception as e:
        print(f"   ⚠️ [JUNIOR HISTORY] Could not read Elo staleness. Defaulting to raw list. Error: {e}")
        return distressed_tickers[:limit]

    # 3. Sort the Distressed Tickers into the Priority Queue
    prioritized_list = []
    
    for t in distressed_tickers:
        if t not in last_played_map:
            # PRIORITY 1: ROOKIE (Never played a match in the Minor League)
            # Give it an artificial date of year 1900 so it goes to the absolute front of the line
            prioritized_list.append({'ticker': t, 'last_played': '1900-01-01'})
        else:
            # PRIORITY 2/3: VETERAN (Has an Elo rating and a Last_Match date)
            prioritized_list.append({'ticker': t, 'last_played': last_played_map[t]})
            
    # 4. Sort the list by 'last_played' ASCENDING (Oldest dates first)
    prioritized_list.sort(key=lambda x: x['last_played'])
    
    # 5. Slice the top 'limit' (e.g., top 20 stalest/newest stocks)
    drafted_tickers = [item['ticker'] for item in prioritized_list[:limit]]
    
    return drafted_tickers