import sys
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import config
import math
from datetime import datetime
import time
from lib.gvqm_league_common import get_client, get_eastern_time_str

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

# --- SETUP ---
SHEET_NAME = getattr(config, 'GOOGLE_SHEET_NAME', "TradingBot_History")

# Google Sheets client is imported from lib.gvqm_league_common

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
def fetch_leaderboard(league_name="Junior_Elo", active_only=True):
    """
    Returns a dict mapping tickers to their current Elo stats.
    Includes a retry loop to prevent Google Sheets connection drops.
    If active_only is True (default), returns only Active_Contenders == 'Y'.
    If active_only is False, returns all sheet records to preserve historical stats.
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
                active_status = str(row.get("Active_Contenders", "N")).strip().upper()
                
                if not active_only or active_status == "Y":
                    ticker = row.get("Ticker")
                    
                    if ticker:
                        leaderboard[ticker] = {
                            "Elo_Rating": float(row.get("Elo_Rating", 1500)),
                            "Wins": int(row.get("Wins", 0)),
                            "Losses": int(row.get("Losses", 0)),
                            "Last_Match": str(row.get("Last_Match", "")),
                            "Active_Contenders": active_status
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

    # 1. Fetch current standings (including inactive/unflagged to preserve historical record)
    leaderboard = fetch_leaderboard(league_name, active_only=False)
    w_stats = leaderboard.get(winner_ticker, {'Elo_Rating': 1500.0, 'Wins': 0, 'Losses': 0})
    l_stats = leaderboard.get(loser_ticker, {'Elo_Rating': 1500.0, 'Wins': 0, 'Losses': 0})

    # 2. Calculate New Elo
    new_w_elo, new_l_elo = calculate_elo(w_stats['Elo_Rating'], l_stats['Elo_Rating'])

    # 3. Update Stats dict
    timestamp = get_eastern_time_str("%Y-%m-%d %H:%M:%S")
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
    Preserves existing _elo and _last_match_dt if already present on candidate.
    Reads all sheet records (active_only=False) to preserve genuine historical
    timestamps even if a candidate was previously inactive.
    """
    leaderboard = fetch_leaderboard(league_name, active_only=False)
    
    for c in candidates:
        t = c.get('ticker', c.get('Ticker', ''))
        stats = leaderboard.get(t, {})
        if 'Elo_Rating' in stats:
            c['_elo'] = stats['Elo_Rating']
        elif '_elo' not in c:
            c['_elo'] = 1500.0
            
        last_match_str = stats.get('Last_Match', '')
        if last_match_str:
            try:
                c['_last_match_dt'] = datetime.strptime(last_match_str, "%Y-%m-%d %H:%M:%S")
            except:
                c['_last_match_dt'] = datetime.min
        elif '_last_match_dt' not in c:
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
# ⚖️ HELPER: JUNIOR ELO TIE-BREAKER
# ==========================================
def junior_tiebreak_key(ticker, junior_board):
    """
    Secondary sort key for Major League tie-breaking.
    Active Junior_Elo contenders (higher Elo first) strictly beat tickers
    with no active Junior_Elo row (lowest priority).
    """
    stats = junior_board.get(ticker) if isinstance(junior_board, dict) else None
    if isinstance(stats, dict) and 'Elo_Rating' in stats:
        return (0, -float(stats['Elo_Rating']))
    return (1, 0.0)


def _format_primary_tie_val(val):
    if isinstance(val, datetime):
        return "never fought" if val == datetime.min else val.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(val, (int, float)):
        return f"{val:.1f}"
    return str(val)


def _format_junior_desc(ticker, junior_board):
    stats = junior_board.get(ticker) if isinstance(junior_board, dict) else None
    if isinstance(stats, dict) and 'Elo_Rating' in stats:
        return f"{ticker} (Jr {float(stats['Elo_Rating']):.1f})"
    return f"{ticker} (no active Junior Elo)"


def _log_junior_tiebreaks(items, junior_board, primary_fn, label, ticker_fn=lambda x: x[0]):
    """
    Walks adjacent sorted items that share the same primary value.
    Emits a pipeline log line only when Junior Elo actually resolved the order
    (i.e. at least two tied tickers had distinct junior_tiebreak_key values).
    """
    n = len(items)
    i = 0
    while i < n:
        p_val = primary_fn(items[i])
        j = i + 1
        while j < n and primary_fn(items[j]) == p_val:
            j += 1
        if j - i > 1:
            group = items[i:j]
            distinct_jks = {junior_tiebreak_key(ticker_fn(item), junior_board) for item in group}
            if len(distinct_jks) > 1:
                ordered_desc = " > ".join(_format_junior_desc(ticker_fn(item), junior_board) for item in group)
                print(f"   ⚖️ TIE-BREAK ({label} {_format_primary_tie_val(p_val)}): {ordered_desc}")
        i = j


def rank_senior_board(senior_board, junior_board=None):
    """
    Ranks Senior_Elo contenders by:
      1. Senior Elo descending
      2. Active Junior Elo descending (missing active Junior row = lowest priority)
      3. Google Sheet row order (via Python's stable sort)
    Returns list[(ticker, data)] and logs every tie resolved by Junior Elo.
    """
    if not senior_board:
        return []
    if junior_board is None:
        junior_board = fetch_leaderboard("Junior_Elo")
    ranked = sorted(
        senior_board.items(),
        key=lambda x: (
            -float(x[1].get('Elo_Rating', 1500.0)),
            junior_tiebreak_key(x[0], junior_board)
        )
    )
    _log_junior_tiebreaks(
        ranked,
        junior_board,
        primary_fn=lambda x: float(x[1].get('Elo_Rating', 1500.0)),
        label="Senior Elo",
        ticker_fn=lambda x: x[0]
    )
    return ranked


# ==========================================
# 🥊 MAJOR LEAGUE: THE TITLE DEFENSE (Cross-Pollinated)
# ==========================================
def get_major_league_matchups(candidates, owned_tickers=None, match_count=None, junior_board=None):
    """
    Pairs Major League contenders using an adjacent-Elo ladder matching system.
    Sorts contenders by staleness (_last_match_dt ascending, Junior Elo tie-break),
    extracts the active brawl pool, sorts by Senior_Elo descending (Junior Elo tie-break),
    and pairs adjacent fighters.
    Dynamically scales match count based on MAJOR_LEAGUE_BUY_PCT when match_count is None.
    """
    # EDGE CASE GUARD: Not enough stocks to fight
    if len(candidates) < 2:
        return []

    # Dynamic match count calculation if omitted
    if match_count is None:
        buy_pct = getattr(config, 'MAJOR_LEAGUE_BUY_PCT', 0.30)
        target = math.ceil(len(candidates) * buy_pct) if isinstance(buy_pct, float) and buy_pct <= 1.0 else int(buy_pct)
        match_count = min(len(candidates) // 2, max(1, target))

    if match_count < 1:
        return []

    candidates = _enrich_candidates(candidates, "Senior_Elo")
    if junior_board is None:
        junior_board = fetch_leaderboard("Junior_Elo")
    ticker_of = lambda c: c.get('ticker', c.get('Ticker', ''))
    jk = lambda c: junior_tiebreak_key(ticker_of(c), junior_board)

    # 1. Sort by Staleness (who has been waiting the longest / never fought; Junior Elo breaks ties)
    candidates.sort(key=lambda x: (x['_last_match_dt'], jk(x)))
    _log_junior_tiebreaks(
        candidates,
        junior_board,
        primary_fn=lambda c: c['_last_match_dt'],
        label="Matchmaking Staleness",
        ticker_fn=ticker_of
    )

    # 2. Grab only the number of fighters we need today
    brawl_pool = candidates[:(match_count * 2)]

    # 3. Sort those specific fighters by Senior Elo descending (Junior Elo breaks ties; stable on full tie)
    brawl_pool.sort(key=lambda x: (-float(x['_elo']), jk(x)))
    _log_junior_tiebreaks(
        brawl_pool,
        junior_board,
        primary_fn=lambda c: float(c.get('_elo', 1500.0)),
        label="Matchmaking Senior Elo",
        ticker_fn=ticker_of
    )

    # 4. Pair them up
    matchups = []
    for i in range(0, len(brawl_pool) - 1, 2):
        matchups.append((brawl_pool[i], brawl_pool[i+1]))

    return matchups
