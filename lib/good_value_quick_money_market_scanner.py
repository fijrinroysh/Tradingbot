import yfinance as yf
import pandas as pd
import requests
import io
import config  # ✅ NEW: Import config to grab the variable

def get_sp500_tickers():
    """
    Fetches the current S&P 500 tickers from Wikipedia.
    Includes a fallback list.
    """
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    fallback = ['PGR', 'AMZN', 'META', 'CRM', 'LMT']  # Minimal fallback list]
    
    try:
        # Use requests with a browser header to avoid 403 Forbidden errors
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        table = pd.read_html(io.StringIO(response.text))
        tickers = table[0]['Symbol'].tolist()
        
        return tickers

    except Exception as e:
        print(f"Scanner: Error fetching S&P 500 list ({e}). Using fallback.")
        return fallback

def find_distressed_stocks(sma_window=None, sma_multiplier=None):
    """
    SCREENS the S&P 500 for stocks trading BELOW their configured SMA * multiplier.
    """
    # ✅ NEW: Pull parameters from config. Fallback to 250 days and 1.0 (0% drop) if missing.
    if sma_window is None:
        sma_window = getattr(config, 'SCANNER_SMA_WINDOW', 250)
    if sma_multiplier is None:
        sma_multiplier = getattr(config, 'SCANNER_SMA_MULTIPLIER', 1.0)
        
    print("Scanner: Fetching S&P 500 tickers...")
    tickers = get_sp500_tickers()
    
    # Ensure tickers are Yahoo-compatible (BRK.B -> BRK-B)
    tickers = [t.replace('.', '-') for t in tickers]
    
    distressed_candidates = []
    
    # Dynamic print statement to show the exact percentage drop you are screening for
    drop_pct = round((1 - sma_multiplier) * 100, 1)
    if drop_pct > 0:
        print(f"Scanner: Screening {len(tickers)} stocks for {drop_pct}% BELOW the {sma_window}-day SMA...")
    else:
        print(f"Scanner: Screening {len(tickers)} stocks for {sma_window}-day SMA breakdown...")
        
    print("Scanner: Downloading data in bulk (this may take 1-3 minutes)...")
    
    # Dynamically calculate how many years of data we need to fulfill the SMA window
    years_needed = max(2, int(sma_window / 252) + 2)
    fetch_period = f"{years_needed}y"
    
    try:
        data = yf.download(
            tickers, 
            period=fetch_period,   # Now dynamic based on your config!
            interval="1d", 
            progress=False,    
            auto_adjust=True,  
            threads=True      
        )['Close']

    except Exception as e:
        print(f"Scanner Critical Error: {e}")
        return []
    
    print("Scanner: Calculating indicators and filtering...")
    
    for ticker in tickers:
        try:
            if ticker not in data.columns:
                continue
                
            prices = data[ticker].dropna()
            
            # Uses dynamic sma_window
            if len(prices) < sma_window:
                continue 
                
            current_price = prices.iloc[-1]
            sma_target = prices.rolling(window=sma_window).mean().iloc[-1]
            
            # 🛑 NEW: Calculate the distress threshold based on the multiplier
            distress_threshold = sma_target * sma_multiplier
            
            if current_price < distress_threshold:
                distressed_candidates.append(ticker)
                
        except Exception:
            continue

    print(f"Scanner: Found {len(distressed_candidates)} potential candidates trading below your SMA threshold.")
    return distressed_candidates