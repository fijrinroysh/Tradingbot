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