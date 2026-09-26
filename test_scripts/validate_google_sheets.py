import os
import json
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()
creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
if not creds_json:
    creds_json = open("google_credentials.json").read()

creds_dict = json.loads(creds_json)
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
client = gspread.authorize(creds)

sheet_name = os.getenv("GOOGLE_SHEET_NAME", "TradingBot_History_Test")
print(f"Connecting to {sheet_name}...")
sh = client.open(sheet_name)
junior_tab = sh.worksheet("Junior_Elo")

records = junior_tab.get_all_records()
print("Total records in Junior_Elo:", len(records))
inactive_records = [r for r in records if r.get('Active_Contenders') == 'N']
print("Inactive records in Junior_Elo:", len(inactive_records))
for r in inactive_records[:5]:
    print(f"Ticker: {r.get('Ticker')}, Active: {r.get('Active_Contenders')}, Elo: {r.get('Elo_Rating')}")
