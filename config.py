# config.py
import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()
# Store all your secret keys here

# 1. NewsAPI Key
NEWS_API_KEY = "41c62705f4db4931a0a7e551870a6d87"

# 2. Alpaca Paper Trading Keys
ALPACA_KEY_ID = "PKXCY2TEO63WB6MWUNWP6L3S3N"
ALPACA_SECRET_KEY = "7FiWKR9LSCqb1eQRrivkLZv4dnfQoLEHBmp6uUDELgsg"
TRADINGVIEW_SECRET = "IAMIRONMAN"



# 4. FINNHUB API KEY (for backtesting)
FINNHUB_KEY = "d43pmk1r01qge0cuufvgd43pmk1r01qge0cuug00"
# ---

# 5. POLYGON API KEY (for backtesting)
POLYGON_API_KEY = "Qm7GVhYIJmQ6gTaMO5TPsSYLVh_BLMPc"




# --- GEMINI RATE LIMITS (Free Tier) ---
#GEMINI_MODEL_NAME = "models/gemini-2.0-flash"
# Requests Per Minute (RPM)
#GEMINI_RPM_LIMIT = 15 
# Tokens Per Minute (TPM)
#GEMINI_TPM_LIMIT = 1_000_000 
#GEMINI_DAILY_LIMIT = 1500     # Requests per day
# Max tokens we want to send in one batch (buffer for safety)
#GEMINI_MAX_BATCH_TOKENS = 10_000 
# --------------------------------------




# Pro limits are stricter (50/day), so we maximise the batch size
GEMINI_RPM_LIMIT = 2          # Requests per minute (Very slow!)
GEMINI_TPM_LIMIT = 32_000     # Tokens per minute
GEMINI_DAILY_LIMIT = 50       # Strict daily limit for Pro
GEMINI_MAX_BATCH_TOKENS = 30_000 # Pro has a huge context window, so we use it
# --------------------------------------

# 4. SCALABLE SENTIMENT SETTINGS (NEW)
# Add any tickers you want to the list below
SENTIMENT_TICKERS = ["AAPL", "MSFT", "GOOG", "TSLA", "AMZN", "META", "NFLX",  "NVDA", "VOO"]
#SENTIMENT_TICKERS = ["INFY"]
 
# Define the quantity to trade for EACH ticker
# For example, you might want to trade $100 worth of each
# (Alpaca supports fractional shares)
SENTIMENT_TRADE_VALUE = 1000 # This is in dollars

MIN_SENTIMENT_SCORE = 0.4  # How positive the news must be to buy
MAX_SENTIMENT_SCORE = -0.4 # How negative the news must be to sell

# --- GOOD VALUE QUICK MONEY BOT SETTINGS ---

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # <-- This is now safe
# --- GEMINI SETTINGS (Pro Model) ---
# We use the stable 2.5 Pro model from your list


GEMINI_MODEL_NAME = "models/gemini-2.5-pro"


# Max Gemini calls to use for the daily scan (keep < 50 for free tier)

DAILY_SCAN_LIMIT = int(os.getenv("DAILY_SCAN_LIMIT"))

# Dollar amount to invest in each "High Conviction" Buy
INVEST_PER_TRADE = int(os.getenv("INVEST_PER_TRADE"))


