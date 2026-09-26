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
client = gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=SCOPES))

sh = client.open("TradingBot_History_Test")
worksheet = sh.worksheet("Junior_Elo")
records = worksheet.get_all_records()

for r in records:
    ticker = r.get("Ticker")
    if ticker in ["CEG", "VST", "COIN"]:
        print(f"Ticker: {ticker} | Active: {r.get('Active_Contenders')} | Elo: {r.get('Elo_Rating')}")
