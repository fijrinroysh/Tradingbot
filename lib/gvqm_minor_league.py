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
                # 👇 THE NEW FILTER: Check the Active_Contender column
                # We strip spaces and make it uppercase just in case of typos in the sheet (e.g. ' y ')
                active_status = str(row.get("Active_Contenders", "N")).strip().upper()
                
                # 🛑 BOUNCER CHECK: Is it a 'Y'?
                if active_status == "Y":
                    ticker = row.get("Ticker")
                    
                    if ticker:
                        # ✅ It's active! Add it to our bot's memory for the day.
                        leaderboard[ticker] = {
                            "Elo_Rating": float(row.get("Elo_Rating", 1500)),
                            "Wins": int(row.get("Wins", 0)),
                            "Losses": int(row.get("Losses", 0)),
                            "Last_Match": str(row.get("Last_Match", ""))
                        }
                        
            # 4. Return only the filtered list of active players back to bot.py
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
                headers = worksheet.row_values(1)
                # Ensure our column exists just in case
                if "Active_Contenders" not in headers:
                    headers.append("Active_Contenders")
                    worksheet.update('1:1', [headers])
            except gspread.exceptions.WorksheetNotFound:
                # If creating from scratch, establish the headers immediately
                worksheet = sh.add_worksheet(title=league_name, rows=1000, cols=7)
                headers = ["Ticker", "Elo_Rating", "Wins", "Losses", "Win_Rate", "Last_Match", "Active_Contenders"]
                worksheet.append_row(headers)

            def update_row_in_sheet(ticker, stats):
                win_rate = f"{(stats['Wins'] / max(1, stats['Wins'] + stats['Losses'])) * 100:.1f}%"
                
                # 👇 THE UPGRADE: Map our data exactly to the column names
                data_map = {
                    "Ticker": ticker,
                    "Elo_Rating": stats['Elo_Rating'],
                    "Wins": stats['Wins'],
                    "Losses": stats['Losses'],
                    "Win_Rate": win_rate,
                    "Last_Match": stats['Last_Match'],
                    "Active_Contenders": "Y"
                }
                
                # Build the row array dynamically based on the actual header order
                row_data = [data_map.get(header_name, "") for header_name in headers]
                
                # Dynamically calculate the final column letter (e.g., 7 headers = 'G')
                end_col_letter = chr(64 + len(headers))
                
                cell = None
                try: 
                    cell = worksheet.find(ticker, in_column=1)
                except: 
                    pass
                
                if cell: 
                    # Dynamically update from 'A' to whatever our last column letter is
                    worksheet.update(values=[row_data], range_name=f"A{cell.row}:{end_col_letter}{cell.row}")
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
# 📊 HELPER: ENRICH CANDIDATES
# ==========================================
def _enrich_candidates(candidates, league_name):
    """
    Private helper function. Fetches the leaderboard and attaches 
    Elo and Last_Match data to every candidate so they are ready for math.
    """
    leaderboard = fetch_leaderboard(league_name)
    
    for c in candidates:
        t = c.get('ticker', c.get('Ticker', ''))
        stats = leaderboard.get(t, {})
        c['_elo'] = stats.get('Elo_Rating', 1500.0)
        
        last_match_str = stats.get('Last_Match', '')
        try:
            c['_last_match_dt'] = datetime.strptime(last_match_str, "%Y-%m-%d %H:%M:%S")
        except:
            c['_last_match_dt'] = datetime.min # Never fought = highest priority
            
    return candidates

# ==========================================
# ⚾ MINOR LEAGUE: THE CHESS LADDER
# ==========================================
def get_minor_league_matchups(candidates, match_count=3):
    """
    Finds the stalest stocks and pairs them against opponents with similar Elo.
    """
    # EDGE CASE GUARD: Not enough stocks to fight, or match count is zero
    if match_count < 1 or len(candidates) < 2:
        return []

    candidates = _enrich_candidates(candidates, "Junior_Elo")
    
    # 1. Sort by Staleness (who has been waiting the longest)
    candidates.sort(key=lambda x: x['_last_match_dt'])
    
    # 2. Grab only the number of fighters we need today
    brawl_pool = candidates[:(match_count * 2)]
    
    # 3. Sort those specific fighters by Elo so the matches are fair
    brawl_pool.sort(key=lambda x: x['_elo'], reverse=True)
    
    # 4. Pair them up
    matchups = []
    for i in range(0, len(brawl_pool) - 1, 2):
        matchups.append((brawl_pool[i], brawl_pool[i+1]))
        
    return matchups


# ==========================================
# 🥊 MAJOR LEAGUE: THE TITLE DEFENSE (Cross-Pollinated)
# ==========================================
def get_major_league_matchups(candidates, owned_tickers, match_count=3):
    """
    Forces your active portfolio to defend against challengers.
    Shuffles the lineups daily to ensure Champions don't fight the same 
    Rookie twice in a row, preventing wasted API calls.
    """
    import random # Ensure random is available for the shuffle
    
    # EDGE CASE GUARD
    if match_count < 1 or len(candidates) < 2:
        return []

    candidates = _enrich_candidates(candidates, "Senior_Elo")
    
    # Separate the Champions from the Challengers
    champions = [c for c in candidates if c.get('ticker', c.get('Ticker', '')) in owned_tickers]
    challengers = [c for c in candidates if c.get('ticker', c.get('Ticker', '')) not in owned_tickers]

    # 👇 THE FIX: SHUFFLE BOTH TEAMS 👇
    # This destroys the repetitive static loop and forces true cross-pollination
    random.shuffle(champions)
    random.shuffle(challengers)
    
    matchups = []
    for champ in champions:
        if not challengers: 
            break 
        
        # Pull a random challenger off the shuffled list
        random_challenger = challengers.pop(0) 
        matchups.append((champ, random_challenger))
        
        if len(matchups) >= match_count:
            break
            
    return matchups