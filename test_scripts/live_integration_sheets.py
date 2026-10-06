import sys
import os
import random
import time

# Ensure lib modules can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.gvqm_league_common import get_client
import config

SHEET_NAME = getattr(config, 'GOOGLE_SHEET_NAME', "TradingBot_History")
TEST_TAB = "Live_Integration_Test"

def run_sheets_live_test():
    """
    Live Integration Test for Google Sheets API.
    Writes a random test value to a dedicated test tab in the Google Sheet,
    clears the local cache, and fetches it back directly from the server to
    prove that updates are physically arriving at the spreadsheet.
    """
    print("🚀 Starting Google Sheets Live Integration Test...")
    
    # 1. Connect
    client = get_client()
    if not client:
        print("❌ Failed to authenticate with Google Sheets.")
        return
        
    try:
        sh = client.open(SHEET_NAME)
        print(f"✅ Connected to Spreadsheet: '{SHEET_NAME}'")
    except Exception as e:
        print(f"❌ Could not open spreadsheet '{SHEET_NAME}'. Error: {e}")
        return

    # 2. Get or create test tab
    try:
        worksheet = sh.worksheet(TEST_TAB)
        print(f"✅ Found test tab '{TEST_TAB}'.")
    except:
        print(f"⚠️ Test tab '{TEST_TAB}' not found. Creating it...")
        worksheet = sh.add_worksheet(title=TEST_TAB, rows=10, cols=5)
        worksheet.append_row(["Test_ID", "Random_Value", "Timestamp"])
        
    # 3. Write a random value to the sheet
    test_id = "LIVE_TEST_1"
    random_val = str(random.randint(10000, 99999))
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"📝 Writing test data: [{test_id}, {random_val}, {timestamp}]")
    try:
        worksheet.append_row([test_id, random_val, timestamp])
        print("✅ Successfully pushed data to Google Sheets API.")
    except Exception as e:
        print(f"❌ Failed to append row: {e}")
        return
        
    # 4. Wait for Google's servers to sync
    time.sleep(2)
    
    # 5. Fetch all records back directly from Google
    print("🔄 Fetching records directly from Google Sheets to verify...")
    try:
        # Re-fetch the worksheet to ensure we don't have local cached data
        sh = client.open(SHEET_NAME)
        worksheet = sh.worksheet(TEST_TAB)
        records = worksheet.get_all_records()
        
        found = False
        for row in records:
            if str(row.get('Random_Value', '')) == random_val:
                found = True
                print(f"✅ VERIFIED! Found the exact random value '{random_val}' physically stored on the Google Sheet.")
                break
                
        if not found:
            print("❌ The data was pushed, but when we read the sheet back, the data was missing.")
            
    except Exception as e:
        print(f"❌ Failed to fetch records back from sheets: {e}")

if __name__ == "__main__":
    run_sheets_live_test()

