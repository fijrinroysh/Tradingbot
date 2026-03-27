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
# Default: "gemini-3-flash-preview" (Free/Cheap). Can switch to "gemini-3-pro-preview" if needed.
#GEMINI_JUNIOR_MODEL = "gemini-3.1-pro-preview"
GEMINI_JUNIOR_MODEL = "gemini-3.1-flash-lite-preview"
JUNIOR_THINKING_LEVEL = "HIGH"  # Fast, cheap scouting for the Minor League

# SENIOR MANAGER: High reasoning, final decision.
# Default: "gemini-3-pro-preview" (Smartest).
#GEMINI_SENIOR_MODEL = "gemini-3.1-pro-preview"
GEMINI_SENIOR_MODEL = "gemini-3.1-flash-lite-preview"

SENIOR_THINKING_LEVEL = "HIGH" # Deep, rigorous reasoning for the Major League

# API Rate Limiting (Set to 15 for Free Tier, 0 for Paid Tier)
API_THROTTLE_SECONDS = 0


# Market Scanner Settings
 # Number of days for the Moving Average filter (e.g. 250, 150, 50)
SCANNER_SMA_WINDOW = 250

#Instead of just asking, "Is the price below the MA?", we need to ask, "Is the price at least 20% BELOW the MA?"
SCANNER_SMA_MULTIPLIER = float(os.getenv("SCANNER_SMA_MULTIPLIER", 0.85))  
# 0.85: Means the stock must be 15% below the MA.



# --- STRATEGY LIMITS ---
# 1. JUNIOR LIMIT: How many stocks to analyze per day.
# If using Flash, set to 200+. If using Pro, set to ~20 to stay within limits.
# This ensures you cover the 200-stock universe in chunks (e.g., 20/day = 10 days).
DAILY_SCAN_LIMIT = int(os.getenv("DAILY_SCAN_LIMIT", 5))
SENIOR_DRAFT_LIMIT = int(os.getenv("SENIOR_DRAFT_LIMIT", 3))# How many top candidates Senior Manager drafts for final review (e.g., 5-10)




# Dollar amount to invest in each "High Conviction" Buy
INVEST_PER_TRADE = int(os.getenv("INVEST_PER_TRADE"))


GOOGLE_SHEET_STRATEGY_TAB = "Executive_Briefs"
GOOGLE_SHEET_SENIOR_DECISIONS_TAB = "Senior_Decisions"
TRADE_LOG_TAB = "Trade_Log"

# 2. Alpaca Paper Trading Keys
ALPACA_KEY_ID = os.getenv("ALPACA_KEY_ID")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY") 

# --- EMAIL NOTIFICATION SETTINGS ---

NOTIFY_EMAIL = os.getenv("EMAIL") # Can be the same as sender
EMAIL_PASSWORD =  os.getenv("EMAIL_PASSWORD")  # The 16-character App Password

RESEND_API_KEY =  os.getenv("RESEND_API_KEY")# Get this from Resend dashboard
EMAIL_SENDER = "onboarding@resend.dev" # Or your verified domain email
EMAIL_RECIPIENT = os.getenv("EMAIL")



GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "TradingBot_History")
DEBUG_MODE = os.getenv("DEBUG_MODE", False)



# ==========================================
# 🧠 SENIOR MANAGER PSYCHOLOGY (RISK DIAL)
# ==========================================
# This variable controls the "Aggression" of the portfolio allocation.
# It acts as a multiplier for your capacity constraints (Zone A Cutoff).
#
# VALUES:
#   1.0  = NEUTRAL (Standard). Strict adherence to max_trades.
#   >1.0 = AGGRESSIVE (Expand). Example: 1.2 allows "Good" stocks (B1) to be bought.
#   <1.0 = CONSERVATIVE (Contract). Example: 0.8 restricts buys to "Perfect" (A1) only.
#
# USAGE: 
#   If max_trades = 5 and RISK_FACTOR = 1.2 -> Effective Capacity ~6 stocks.
#   If max_trades = 5 and RISK_FACTOR = 0.8 -> Effective Capacity ~4 stocks.

RISK_FACTOR = float(os.getenv("RISK_FACTOR", 1.0))  # Default: 1.0 (Neutral)


