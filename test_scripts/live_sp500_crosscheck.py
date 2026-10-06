import sys
import os
import pandas as pd
import requests
from bs4 import BeautifulSoup

# Ensure lib modules can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.good_value_quick_money_market_scanner import get_sp500_tickers

def fetch_sp500_alternative_source():
    """
    Fetches S&P 500 tickers from Slickcharts as an alternative validation source.
    Note: Slickcharts requires a User-Agent.
    """
    try:
        url = 'https://www.slickcharts.com/sp500'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', {'class': 'table table-hover table-borderless table-sm'})
            
            tickers = []
            for row in table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) > 2:
                    ticker = cols[2].text.strip()
                    # Standardize format similar to pandas read_html
                    ticker = ticker.replace('.', '-') 
                    tickers.append(ticker)
            return tickers
    except Exception as e:
        print(f"⚠️ Failed to fetch alternative source: {e}")
        return []

def run_sp500_live_test():
    """
    Live Integration Test for S&P 500 Ticker Extraction.
    Downloads the active ticker list via the bot's standard method (Wikipedia)
    and cross-checks the total count and overlap with an alternative source
    to guarantee we aren't accidentally missing a huge chunk of the index.
    """
    print("🚀 Starting S&P 500 Live Extraction Cross-Check...")
    
    # 1. Fetch using the bot's primary logic
    try:
        print("📥 Fetching tickers using Primary Source (Wikipedia)...")
        primary_tickers = get_sp500_tickers()
        primary_count = len(primary_tickers)
        print(f"✅ Primary Source returned {primary_count} tickers.")
    except Exception as e:
        print(f"❌ Failed to fetch primary tickers: {e}")
        return
        
    # 2. Assert logical boundaries (S&P 500 has ~503 tickers due to dual-class shares)
    if primary_count < 495:
        print(f"❌ ERROR: Primary fetch returned abnormally low ticker count ({primary_count}). List might be corrupted.")
    elif primary_count > 510:
        print(f"❌ ERROR: Primary fetch returned abnormally high ticker count ({primary_count}). Parsing issue likely.")
    else:
        print("✅ Primary ticker count is within the healthy logical boundary (495 - 510).")

    # 3. Fetch using alternative source (Slickcharts)
    print("\n📥 Fetching tickers using Alternative Validation Source (Slickcharts)...")
    alt_tickers = fetch_sp500_alternative_source()
    alt_count = len(alt_tickers)
    
    if alt_count > 0:
        print(f"✅ Alternative Source returned {alt_count} tickers.")
        
        # Cross-reference
        primary_set = set(primary_tickers)
        alt_set = set(alt_tickers)
        
        overlap = primary_set.intersection(alt_set)
        missing_from_primary = alt_set - primary_set
        
        print(f"\n📊 Match Analysis:")
        print(f"  - Tickers matching in both sources: {len(overlap)}")
        print(f"  - Match Percentage: {(len(overlap) / max(1, alt_count)) * 100:.2f}%")
        
        if len(missing_from_primary) > 15:
            print(f"⚠️ WARNING: High number of mismatches detected. Missing from primary: {list(missing_from_primary)[:10]}...")
        else:
            print("✅ Cross-check successful. The primary list is highly accurate.")
    else:
        print("⚠️ Could not load alternative source. Relying on primary boundaries.")

if __name__ == "__main__":
    run_sp500_live_test()

