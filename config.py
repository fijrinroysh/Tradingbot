# config.py
import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()
# Store all your secret keys here

# 1. NewsAPI Key
NEWS_API_KEY = "41c62705f4db4931a0a7e551870a6d87"


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
## JUNIOR ANALYST: High volume, initial filtering. 
# Default: "gemini-2.0-flash" (Free/Cheap). Can switch to "gemini-3-pro-preview" if needed.
GEMINI_JUNIOR_MODEL = "gemini-3-pro-preview"

# SENIOR MANAGER: High reasoning, final decision.
# Default: "gemini-3-pro-preview" (Smartest).
GEMINI_SENIOR_MODEL = "gemini-3-pro-preview"

# --- STRATEGY LIMITS ---
# 1. JUNIOR LIMIT: How many stocks to analyze per day.
# If using Flash, set to 200+. If using Pro, set to ~20 to stay within limits.
# This ensures you cover the 200-stock universe in chunks (e.g., 20/day = 10 days).
DAILY_SCAN_LIMIT = int(os.getenv("DAILY_SCAN_LIMIT", 20))
#DAILY_SCAN_LIMIT = 10
COOLDOWN_DAYS = int(os.getenv("COOLDOWN_DAYS", 10)) # <--- NEW: Default 10 Days


# Dollar amount to invest in each "High Conviction" Buy
INVEST_PER_TRADE = int(os.getenv("INVEST_PER_TRADE"))

# --- SENIOR MANAGER SETTINGS ---
SENIOR_TOP_PICKS = int(os.getenv("SENIOR_TOP_PICKS", 5)) 
SENIOR_LOOKBACK_DAYS = int(os.getenv("COOLDOWN_DAYS", 10)) # <--- NEW


# 2. Alpaca Paper Trading Keys
ALPACA_KEY_ID = os.getenv("ALPACA_KEY_ID") 
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY") 

# --- EMAIL NOTIFICATION SETTINGS ---
EMAIL_SENDER = os.getenv("EMAIL")
EMAIL_RECIPIENT = os.getenv("EMAIL") # Can be the same as sender
EMAIL_PASSWORD =  os.getenv("EMAIL_PASSWORD")  # The 16-character App Password


