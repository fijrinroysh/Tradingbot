# config.py
# Store all your secret keys here

# 1. NewsAPI Key
NEWS_API_KEY = "41c62705f4db4931a0a7e551870a6d87"

# 2. Alpaca Paper Trading Keys
ALPACA_KEY_ID = "PKWMQDBXMMYIUO61F9X4"
ALPACA_SECRET_KEY = "KYfU5eXz4oMhcTdwouYEiDKfKElOoW2S034I4tSU"
TRADINGVIEW_SECRET = "IAMIRONMAN"


# 4. SCALABLE SENTIMENT SETTINGS (NEW)
# Add any tickers you want to the list below
SENTIMENT_TICKERS = ["AAPL", "MSFT", "GOOG", "TSLA"]

# Define the quantity to trade for EACH ticker
# For example, you might want to trade $100 worth of each
# (Alpaca supports fractional shares)
SENTIMENT_TRADE_VALUE = 100 # This is in dollars