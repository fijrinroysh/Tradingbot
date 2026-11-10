import gspread
from google.oauth2.service_account import Credentials
import datetime
import os
import json
import config
import time
import math
from lib.gvqm_league_common import (
    get_client,
    get_eastern_now,
    get_eastern_time_str,
    load_memory_bank,
    save_memory_bank,
    compute_rank_momentum
)

SHEET_NAME = getattr(config, 'GOOGLE_SHEET_NAME', "TradingBot_History")
JUNIOR_TAB_NAME = "Junior_Decisions"

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

            timestamp = get_eastern_time_str("%Y-%m-%d %H:%M")
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
def filter_candidates(active_contenders, limit=20):
    """
    Acts as a Priority Queue for all active Minor League contenders (distressed + protected).
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
        return active_contenders[:limit]

    prioritized_list = []
    
    for t in active_contenders:
        if t not in last_played_map:
            # PRIORITY 1: ROOKIE 
            prioritized_list.append({'ticker': t, 'last_played': '1900-01-01'})
        else:
            # PRIORITY 2/3: VETERAN 
            prioritized_list.append({'ticker': t, 'last_played': last_played_map[t]})
            
    prioritized_list.sort(key=lambda x: x['last_played'])
    drafted_tickers = [item['ticker'] for item in prioritized_list[:limit]]
    
    return drafted_tickers


# ==========================================
# 🧠 GOOGLE SHEETS MEMORY BANK (JSON IN A CELL)
# ==========================================
def load_history_from_sheets():
    """Downloads the memory bank from a dedicated tab in Google Sheets."""
    return load_memory_bank("Junior_Memory_Bank")


def save_history_to_sheets(data):
    """Uploads the updated memory bank back to Cell A1 in Google Sheets."""
    save_memory_bank("Junior_Memory_Bank", data)


def get_rising_stars(current_standings):
    """
    Downloads history from Sheets, calculates biggest movers, saves new snapshot.
    Enforces a strict 7-day memory limit to avoid using outdated ranks.
    """
    draft_limit = getattr(config, 'SENIOR_DRAFT_LIMIT', 3)
    limit = int(draft_limit) if draft_limit >= 1.0 else 3
    return compute_rank_momentum(
        "Junior_Memory_Bank",
        current_standings,
        max_items=limit,
        label="Minor League",
        loader=load_history_from_sheets,
        saver=save_history_to_sheets
    )