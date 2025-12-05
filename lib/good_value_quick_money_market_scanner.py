import yfinance as yf
import pandas as pd
import requests
import io

def get_sp500_tickers():
    """
    Fetches the current S&P 500 tickers from Wikipedia.
    Includes a fallback list and fixes formatting (BRK.B -> BRK-B).
    """
    url = '-https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    fallback = ['UNH' ]
    
    try:
        # Use requests with a browser header to avoid 403 Forbidden errors
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        table = pd.read_html(io.StringIO(response.text))
        tickers = table[0]['Symbol'].tolist()
        
        # --- FIX: Replace dots with hyphens for Yahoo Finance ---
        # Example: BRK.B -> BRK-B, BF.B -> BF-B
        tickers = [t.replace('.', '-') for t in tickers]
        # -------------------------------------------------------
        
        return tickers

    except Exception as e:
        print(f"Scanner: Error fetching S&P 500 list ({e}). Using fallback.")
        return fallback

def find_distressed_stocks():
    """
    SCREENS the S&P 500 for stocks trading BELOW their 250-day SMA.
    """
    print("Scanner: Fetching S&P 500 tickers...")
    tickers = get_sp500_tickers()
    
    distressed_candidates = []
    
    print(f"Scanner: Screening {len(tickers)} stocks for 250-SMA breakdown...")
    print("Scanner: Downloading data in bulk (this may take 1-2 minutes)...")
    
    try:
        # Download 2 years of data to ensure we have enough for 250 SMA
        data = yf.download(tickers, period="2y", interval="1d", progress=True, threads=True)['Close']
    except Exception as e:
        print(f"Scanner Critical Error: {e}")
        return []
    
    print("Scanner: Calculating indicators and filtering...")
    
    for ticker in tickers:
        try:
            # Handle case where bulk download might miss a column
            if ticker not in data.columns:
                continue
                
            prices = data[ticker].dropna()
            
            if len(prices) < 250:
                continue 
                
            current_price = prices.iloc[-1]
            sma_250 = prices.rolling(window=250).mean().iloc[-1]
            
            if current_price < sma_250:
                distressed_candidates.append(ticker)
                
        except Exception:
            continue

    print(f"Scanner: Found {len(distressed_candidates)} potential candidates trading below 250 SMA.")
    return distressed_candidates