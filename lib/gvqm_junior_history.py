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


import io
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# ==========================================
# 🧠 GOOGLE DRIVE MEMORY BANK (JSON)
# ==========================================
def get_drive_service():
    """Builds the Google Drive API Service using your existing credentials."""
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        if os.path.exists("google_credentials.json"):
            creds_json = open("google_credentials.json").read()
        else:
            return None
    
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def get_or_create_folder(drive_service, folder_name="GVQM_Memory_Bank"):
    """Finds the subfolder in Drive, or creates it if it doesn't exist."""
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = drive_service.files().list(q=query, fields="nextPageToken, files(id, name)").execute()
    items = results.get('files', [])

    if not items:
        # Create it
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = drive_service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')
    else:
        return items[0].get('id')

def load_history_from_drive(filename="minor_league_history.json"):
    """Downloads the memory bank from Google Drive."""
    service = get_drive_service()
    if not service: return {}

    folder_id = get_or_create_folder(service)
    
    # Check if file exists in the folder
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    if not items:
        return {} # File doesn't exist yet (first run)

    file_id = items[0].get('id')
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    
    return json.loads(fh.getvalue().decode('utf-8'))

def save_history_to_drive(data, filename="minor_league_history.json"):
    """Uploads the updated memory bank back to Google Drive."""
    service = get_drive_service()
    if not service: return

    folder_id = get_or_create_folder(service)
    
    # Check if file exists to update it, otherwise create it
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    file_metadata = {'name': filename, 'parents': [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(json.dumps(data, indent=4).encode('utf-8')),
                              mimetype='application/json', resumable=True)

    if not items:
        # Create new file
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    else:
        # Update existing file
        file_id = items[0].get('id')
        service.files().update(fileId=file_id, media_body=media).execute()