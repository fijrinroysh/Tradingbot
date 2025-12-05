# lib/good_value_quick_money_market_scanner.py
import yfinance as yf
import pandas as pd

def get_sp500_tickers():
    """Fetches S&P 500 tickers."""
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    fallback = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'AMD', 'INTC', 'PYPL']
    
    try:
        table = pd.read_html(url)
        return table[0]['Symbol'].tolist()
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