import os
import json
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import time

load_dotenv()
creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
if not creds_json:
    creds_json = open("google_credentials.json").read()

creds_dict = json.loads(creds_json)
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
client = gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=SCOPES))

sheet_name = os.getenv("GOOGLE_SHEET_NAME", "TradingBot_History_Test")
print(f"Connecting to {sheet_name} to mock data...")
sh = client.open(sheet_name)
worksheet = sh.worksheet("Junior_Elo")

# Find CEG and VST and set their Elo to 2500 and 2400 (Top ranks)
# Find COIN and set its Elo to 1500 (Not top rank)
# Also set their Active_Contenders to 'Y' initially

records = worksheet.get_all_records()
headers = worksheet.row_values(1)
ticker_col = headers.index("Ticker") + 1
elo_col = headers.index("Elo_Rating") + 1
status_col = headers.index("Active_Contenders") + 1

updates = []
for i, r in enumerate(records):
    row_idx = i + 2
    ticker = r.get("Ticker")
    if ticker == "CEG":
        updates.append({'range': f"{chr(64+elo_col)}{row_idx}", 'values': [[2500.0]]})
        updates.append({'range': f"{chr(64+status_col)}{row_idx}", 'values': [['Y']]})
    elif ticker == "VST":
        updates.append({'range': f"{chr(64+elo_col)}{row_idx}", 'values': [[2400.0]]})
        updates.append({'range': f"{chr(64+status_col)}{row_idx}", 'values': [['Y']]})
    elif ticker == "COIN":
        updates.append({'range': f"{chr(64+elo_col)}{row_idx}", 'values': [[1500.0]]})
        updates.append({'range': f"{chr(64+status_col)}{row_idx}", 'values': [['Y']]})

if updates:
    worksheet.batch_update(updates)
    print(f"Mocked CEG (2500), VST (2400), and COIN (1500) as Active.")
else:
    print("Tickers not found in sheet to mock.")

