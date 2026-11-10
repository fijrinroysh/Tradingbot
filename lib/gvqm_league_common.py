import gspread
from google.oauth2.service_account import Credentials
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import config

# --- US EASTERN TIMEZONE STANDARDIZATION ---
EASTERN_TZ = ZoneInfo("America/New_York")

def get_eastern_now() -> datetime:
    """Returns the current datetime localized to US Eastern Time (EST/EDT)."""
    return datetime.now(EASTERN_TZ)

def get_eastern_time_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Returns the current timestamp string localized to US Eastern Time (EST/EDT)."""
    return get_eastern_now().strftime(fmt)

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
                with open("google_credentials.json", "r", encoding="utf-8") as f:
                    creds_json = f.read()
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
    If wipe_inactive_elo is True (both Major and Minor Leagues), it resets inactive/demoted stocks to 1500 
    to prevent stale historical scores from biasing future match evaluations.
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

    # 6. 🌱 Auto-Register New Contenders Missing Entirely from Sheet
    existing_tickers = {
        str(r.get("Ticker", "")).strip().upper()
        for r in all_data
        if r.get("Ticker")
    }
    missing_active = [
        t.strip().upper()
        for t in todays_active_tickers
        if t and t.strip().upper() and t.strip().upper() not in existing_tickers
    ]
    
    if missing_active:
        new_rows = []
        for new_ticker in missing_active:
            new_row_map = {
                "Ticker": new_ticker,
                "Elo_Rating": 1500.0,
                "Wins": 0,
                "Losses": 0,
                "Win_Rate": "0.0%",
                "Last_Match": "",
                "Active_Contenders": "Y"
            }
            row_data = [new_row_map.get(header_name, "") for header_name in headers]
            new_rows.append(row_data)
        worksheet.append_rows(new_rows)
        print(f"   🌱 [LEAGUE SYNC] Registered {len(new_rows)} new active contender(s) into {tab_name}: {missing_active} (1500.0 baseline Elo).")

def banish_ticker(ticker):
    """
    Emergency Trapdoor Protocol: Forcefully banishes a ticker from the Senior League (Senior_Elo).
    Sets Active_Contenders = 'N' and Elo_Rating = 1500.0 immediately in Senior_Elo to terminate
    its Major League tenure and prevent re-buys, while preserving its Junior_Elo Minor League track record.
    """
    print(f"🚨 Banishing {ticker} from Senior League leaderboard (preserving Junior_Elo track record)...")
    client = get_client()
    if not client: return
    
    sheet = client.open(SHEET_NAME)
    tab_name = "Senior_Elo"
    try:
        worksheet = sheet.worksheet(tab_name)
        headers = worksheet.row_values(1)
        
        if "Active_Contenders" in headers and "Elo_Rating" in headers:
            status_col = chr(64 + headers.index("Active_Contenders") + 1)
            elo_col = chr(64 + headers.index("Elo_Rating") + 1)
            
            cell = worksheet.find(ticker, in_column=1)
            if cell:
                actual_row = cell.row
                updates = [
                    {'range': f"{status_col}{actual_row}", 'values': [['N']]},
                    {'range': f"{elo_col}{actual_row}", 'values': [[1500.0]]}
                ]
                worksheet.batch_update(updates)
                print(f"   🔨 Reset {ticker} to 1500.0 Elo in {tab_name} (Junior_Elo preserved).")
    except gspread.exceptions.WorksheetNotFound:
        pass
    except Exception as e:
        print(f"   ⚠️ Failed to banish {ticker} from {tab_name}: {e}")


# ==========================================
# 🧠 GOOGLE SHEETS MEMORY BANK (JSON IN CELL A1)
# ==========================================
def load_memory_bank(tab_name: str) -> dict:
    """Downloads the memory bank from Cell A1 of the designated worksheet."""
    client = get_client()
    if not client:
        return {}

    try:
        sheet = client.open(SHEET_NAME)
        try:
            worksheet = sheet.worksheet(tab_name)
        except Exception:
            print(f"☁️ [MEMORY] Creating new '{tab_name}' tab in Google Sheets...")
            worksheet = sheet.add_worksheet(title=tab_name, rows="10", cols="5")
        
        val = worksheet.acell('A1').value
        if val:
            return json.loads(val)
        return {}
    except Exception as e:
        print(f"⚠️ [MEMORY] Failed to load memory from {tab_name}: {e}")
        return {}


def save_memory_bank(tab_name: str, data: dict) -> None:
    """Uploads the memory bank JSON string to Cell A1 of the designated worksheet."""
    client = get_client()
    if not client:
        return

    try:
        sheet = client.open(SHEET_NAME)
        try:
            worksheet = sheet.worksheet(tab_name)
        except Exception:
            worksheet = sheet.add_worksheet(title=tab_name, rows="10", cols="5")
        
        json_str = json.dumps(data)
        worksheet.update('A1', [[json_str]])
    except Exception as e:
        print(f"⚠️ [MEMORY] Failed to save memory to {tab_name}: {e}")


def compute_rank_momentum(
    tab_name: str,
    current_standings: list,
    max_items: int = 3,
    label: str = "League",
    loader=None,
    saver=None
) -> list:
    """
    Downloads history from Sheets, calculates biggest movers, saves new snapshot.
    Enforces a strict 3-to-7 day lookback and 30-day snapshot pruning to comply
    with Google Sheets 50k character cell limits.
    """
    from datetime import timedelta
    
    load_fn = loader if loader is not None else (lambda: load_memory_bank(tab_name))
    save_fn = saver if saver is not None else (lambda d: save_memory_bank(tab_name, d))

    today_str = get_eastern_time_str("%Y-%m-%d")

    # 1. Download Memory Bank from Google Sheets
    print(f"☁️ [NOTIFIER] Loading {label} memory from Google Sheets...")
    history = load_fn()
    if not isinstance(history, dict):
        history = {}

    # 2. Save today's snapshot
    today_ranks = {ticker: rank for rank, (ticker, data) in enumerate(current_standings, start=1)}
    history[today_str] = today_ranks

    # Prune historical snapshots older than 30 days to enforce Google Sheets 50k character cell limit
    cutoff_date = (get_eastern_now() - timedelta(days=30)).strftime("%Y-%m-%d")
    history = {k: v for k, v in history.items() if k >= cutoff_date}

    # 3. Upload Memory Bank back to Google Sheets
    print(f"☁️ [NOTIFIER] Saving updated memory to Google Sheets...")
    save_fn(history)

    # 4. Bounded Lookback: Check 3 days ago, then 4, up to a maximum of 7 days
    past_ranks = None
    for days_back in range(3, 8):
        target_date = (get_eastern_now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        if target_date in history:
            past_ranks = history[target_date]
            break

    # If no data was found within the last 7 days, abandon the momentum check
    if not past_ranks:
        return []

    # 5. Calculate Jumps
    movers = []
    for ticker, current_rank in today_ranks.items():
        if ticker in past_ranks:
            past_rank = past_ranks[ticker]
            jump = past_rank - current_rank
            if jump > 0:
                movers.append({
                    "ticker": ticker, "jump": jump, "current": current_rank, "past": past_rank
                })

    return sorted(movers, key=lambda x: x['jump'], reverse=True)[:max_items]

