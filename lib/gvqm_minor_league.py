import gspread
from google.oauth2.service_account import Credentials
import os
import json
import config
from datetime import datetime
import time

# --- SETUP ---
SHEET_NAME = getattr(config, 'GOOGLE_SHEET_NAME', "TradingBot_History")

def get_client():
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json and os.path.exists("google_credentials.json"):
        try:
            creds_json = open("google_credentials.json").read()
        except:
            return None
    if not creds_json: return None
    
    try:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"⚠️ [MATCHMAKER] Auth Error: {e}")
        return None

# ==========================================
# 🧮 THE ELO MATH
# ==========================================
def calculate_elo(winner_rating, loser_rating, k_factor=32):
    """
    Standard Chess Elo Formula.
    k_factor determines how much ratings change per match (32 is standard).
    """
    expected_winner = 1 / (1 + 10 ** ((loser_rating - winner_rating) / 400))
    expected_loser = 1 / (1 + 10 ** ((winner_rating - loser_rating) / 400))
    
    new_w = winner_rating + k_factor * (1 - expected_winner)
    new_l = loser_rating + k_factor * (0 - expected_loser)
    
    return round(new_w, 1), round(new_l, 1)

# ==========================================
# 📊 LEADERBOARD MANAGEMENT (WITH RETRIES)
# ==========================================
def fetch_leaderboard(league_name="Junior_Elo"):
    """
    Returns a dict mapping tickers to their current Elo stats.
    Includes a retry loop to prevent Google Sheets connection drops.
    """
    client = get_client()
    if not client: return {}

    for attempt in range(3):
        try:
            sh = client.open(SHEET_NAME)
            try:
                worksheet = sh.worksheet(league_name)
            except gspread.exceptions.WorksheetNotFound:
                return {} # Normal if it's the first run
            
            data = worksheet.get_all_records()
            leaderboard = {}
            for row in data:
                ticker = row.get('Ticker')
                if ticker:
                    leaderboard[ticker] = {
                        'Elo_Rating': float(row.get('Elo_Rating', 1500)),
                        'Wins': int(row.get('Wins', 0)),
                        'Losses': int(row.get('Losses', 0)),
                        'Last_Match': row.get('Last_Match', '')
                    }
            return leaderboard

        except gspread.exceptions.WorksheetNotFound:
            return {}
        except Exception as e:
            print(f"   ⚠️ [MATCHMAKER] Google Sheets connection dropped (fetch). Retrying ({attempt+1}/3)...")
            time.sleep(2) # Wait 2 seconds and try again
            
    return {} # If it fails 3 times, return empty

def record_match_result(league_name, winner_ticker, loser_ticker):
    """
    Updates the Elo ratings for the winner and loser in Google Sheets.
    Includes a retry loop to prevent Google Sheets connection drops.
    """
    client = get_client()
    if not client: return

    # 1. Fetch current standings
    leaderboard = fetch_leaderboard(league_name)
    w_stats = leaderboard.get(winner_ticker, {'Elo_Rating': 1500.0, 'Wins': 0, 'Losses': 0})
    l_stats = leaderboard.get(loser_ticker, {'Elo_Rating': 1500.0, 'Wins': 0, 'Losses': 0})

    # 2. Calculate New Elo
    new_w_elo, new_l_elo = calculate_elo(w_stats['Elo_Rating'], l_stats['Elo_Rating'])

    # 3. Update Stats dict
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    w_stats.update({'Elo_Rating': new_w_elo, 'Wins': w_stats['Wins'] + 1, 'Last_Match': timestamp})
    l_stats.update({'Elo_Rating': new_l_elo, 'Losses': l_stats['Losses'] + 1, 'Last_Match': timestamp})

    # 4. Write to Google Sheets (With Retry Loop)
    for attempt in range(3):
        try:
            sh = client.open(SHEET_NAME)
            
            try:
                worksheet = sh.worksheet(league_name)
            except gspread.exceptions.WorksheetNotFound:
                worksheet = sh.add_worksheet(title=league_name, rows=1000, cols=6)
                worksheet.append_row(["Ticker", "Elo_Rating", "Wins", "Losses", "Win_Rate", "Last_Match"])

            def update_row_in_sheet(ticker, stats):
                win_rate = f"{(stats['Wins'] / max(1, stats['Wins'] + stats['Losses'])) * 100:.1f}%"
                row_data = [ticker, stats['Elo_Rating'], stats['Wins'], stats['Losses'], win_rate, stats['Last_Match']]
                
                cell = None
                try: 
                    cell = worksheet.find(ticker, in_column=1)
                except: 
                    pass
                
                if cell: 
                    # 🛠️ UPDATED FOR GSPREAD 6.0+ COMPATIBILITY
                    worksheet.update(values=[row_data], range_name=f"A{cell.row}:F{cell.row}")
                else: 
                    worksheet.append_row(row_data)

            # Update both rows
            update_row_in_sheet(winner_ticker, w_stats)
            update_row_in_sheet(loser_ticker, l_stats)
            
            print(f"   🏆 [{league_name}] {winner_ticker} ({new_w_elo}) def. {loser_ticker} ({new_l_elo})")
            return # Success! Exit the retry loop.

        except Exception as e:
            print(f"   ⚠️ [MATCHMAKER] Google Sheets connection dropped (write). Retrying ({attempt+1}/3)...")
            time.sleep(2)

# ==========================================
# 🥊 MATCHMAKING ENGINE
# ==========================================
def get_next_matchups(candidates, league_name="Junior_Elo", match_count=3):
    """
    Pairs stocks with similar Elo ratings so they fight evenly.
    Works for BOTH Junior and Senior Leagues!
    """
    leaderboard = fetch_leaderboard(league_name)
    
    for c in candidates:
        t = c.get('ticker', c.get('Ticker', ''))
        c['_elo'] = leaderboard.get(t, {}).get('Elo_Rating', 1500.0)
        
    # Sort by Elo so we can pair neighbors
    candidates.sort(key=lambda x: x['_elo'], reverse=True)
    
    matchups = []
    for i in range(0, len(candidates) - 1, 2):
        if len(matchups) >= match_count:
            break
        matchups.append((candidates[i], candidates[i+1]))
        
    return matchups