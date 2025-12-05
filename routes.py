from flask import Blueprint, jsonify, request
import threading
import config
import sys, os 
import time 

# --- Add root folder to path to import 'lib' ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(SCRIPT_DIR)
sys.path.append(parent_dir)

# Import the modules for the "Good Value Quick Money" Strategy


import lib.good_value_quick_money_alpaca_trader as good_value_quick_money_alpaca_trader
from lib.good_value_quick_money_market_scanner import find_distressed_stocks
from lib.good_value_quick_money_history_manager import filter_candidates, mark_as_analyzed
from lib.good_value_quick_money_gemini_agent import analyze_stock


# --- Import our project modules ---
import alpaca_trader
# Import the functions from our clean, live-data loader
from lib.live_data_loader import  get_24h_summary_score_gemini

main_routes = Blueprint('main_routes', __name__)

# ----------------------------------------------------
# ROUTE 1: HEALTH CHECK
# ----------------------------------------------------
@main_routes.route('/health')
def health_check():
    """
    This endpoint is used by keep-alive services like UptimeRobot
    to confirm the app is running.
    """
    return jsonify(status="ok"), 200

# ----------------------------------------------------
# ROUTE 2: DAILY SENTIMENT BOT
# ----------------------------------------------------
def run_daily_sentiment_bot():
    """
    This is the main logic for the daily bot.
    It loops through all tickers in the config, gets their
    24-hour sentiment from Finnhub, and places trades.
    """
    print(f"--- [DAILY BOT] Starting daily run for all tickers ---")
    
    for ticker in config.SENTIMENT_TICKERS:
        try:
            # Get the 24-hour summary score from Finnhub
            score = get_24h_summary_score_gemini(ticker)
            
            print(f"--- [DAILY BOT: {ticker}] Score: {score:.4f} ---")

            # Make Trade Decision based on config thresholds
            if score >= config.MIN_SENTIMENT_SCORE:
                print(f"--- [DAILY BOT: {ticker}] Decision: POSITIVE. Placing BUY order. ---")
                alpaca_trader.place_notional_buy_order(ticker, config.SENTIMENT_TRADE_VALUE)
                
            elif score <= config.MAX_SENTIMENT_SCORE:
                print(f"--- [DAILY BOT: {ticker}] Decision: NEGATIVE. Closing position. ---")
                alpaca_trader.close_existing_position(ticker)
                
            else:
                print(f"--- [DAILY BOT: {ticker}] Decision: NEUTRAL. Holding. ---")
            
            # To respect API rate limits
            time.sleep(2) 

        except Exception as e:
            print(f"--- [DAILY BOT: {ticker}] CRITICAL ERROR for this ticker: {e} ---")
            # Continue to the next ticker

@main_routes.route('/sentimentbot')
def trigger_sentiment_bot():
    """
    This is the main endpoint for your daily UptimeRobot scheduler.
    It starts the daily logic in a background thread.
    """
    print(f"--- /tradingbot route hit. Starting background daily logic. ---")
    
    # Run in a thread so the web request finishes immediately
    thread = threading.Thread(target=run_daily_sentiment_bot)
    thread.start()
    
    return jsonify(status="daily_sentiment_job_started"), 202

# ----------------------------------------------------
# ROUTE 3: TRADINGVIEW WEBHOOK
# ----------------------------------------------------
def process_webhook_trade(trade_data):
    """
    Parses webhook data AND checks 24h sentiment before trading.
    """
    try:
        # 1. SECURITY CHECK
        if trade_data.get("secret") != config.TRADINGVIEW_SECRET:
            print(f"Webhook Thread: SECURITY ALERT! Invalid secret. Ignoring trade.")
            return

        # 2. DATA VALIDATION
        action = trade_data.get("action", "").upper()
        ticker = trade_data.get("symbol", "").upper()
        quantity = float(trade_data.get("qty"))
        
        if not action or not ticker or not quantity:
            raise ValueError("Missing action, symbol, or qty")

        print(f"Webhook Thread: Validated signal: {action} {quantity} {ticker}")

        # 3. SENTIMENT CONFIRMATION STEP (Now uses Finnhub)
        # --- UPDATE: Use Gemini for Confirmation ---
        print(f"Webhook Thread: Checking Gemini sentiment for {ticker}...")
        sentiment_score = get_24h_summary_score_gemini(ticker)
        print(f"Webhook Thread: Gemini Score: {sentiment_score:.4f}")
        # -------------------------------------------
        # 4. TRADING LOGIC WITH FILTER
        if action == "BUY":
            # Only buy if sentiment is NOT negative
            if sentiment_score > -0.10: 
                print(f"Webhook Thread: Sentiment is positive/neutral. Confirming BUY.")
                alpaca_trader.place_buy_order(ticker, quantity)
            else:
                print(f"Webhook Thread: Sentiment is negative. VETOING BUY signal.")
                
        elif action == "SELL":
            # Only sell if sentiment is NOT positive
            if sentiment_score < 0.10:
                print(f"Webhook Thread: Sentiment is negative/neutral. Confirming SELL.")
                alpaca_trader.place_sell_order(ticker, quantity)
            else:
                print(f"Webhook Thread: Sentiment is positive. VETOING SELL signal.")
        
        elif action == "CLOSE":
            alpaca_trader.close_existing_position(ticker)
            
    except Exception as e:
        print(f"--- CRITICAL THREAD ERROR in 'process_webhook_trade': {e} ---")

@main_routes.route('/webhook', methods=['POST'])
def handle_tradingview_webhook():
    """
    This is the endpoint for TradingView alerts.
    """
    try:
        data = request.get_json()
        if not data:
            print("--- /webhook route hit. No JSON data received. ---")
            return jsonify(status="error", message="No JSON data"), 400

        print(f"--- /webhook route hit. Received JSON: {data} ---")
        
        # Run in a thread to prevent timeouts and handle errors
        thread = threading.Thread(target=process_webhook_trade, args=(data,))
        thread.start()
        
        return jsonify(status="webhook_received"), 200
    
    except Exception as e:
        print(f"Error in /webhook route (data was not JSON?): {e}")
        return jsonify(status="error", message=str(e)), 400




# ----------------------------------------------------
# ROUTE 4: GOOD VALUE QUICK MONEY BOT SCAN
# ----------------------------------------------------
def run_good_value_quick_money_scan():
    print("--- [GOOD VALUE QUICK MONEY BOT] Starting Daily Scan ---")
    
    # 1. Find targets
    candidates = find_distressed_stocks()
    if not candidates: return

    # 2. Filter History
    # USE CONFIG HERE
    to_analyze = filter_candidates(candidates, config.DAILY_SCAN_LIMIT)
    
    if not to_analyze:
        print("[GOOD VALUE QUICK MONEY BOT] No fresh candidates.")
        return

    print(f"[GOOD VALUE QUICK MONEY BOT] Analyzing {len(to_analyze)} tickers...")
    
    # 3. Analyze & Trade
    for ticker in to_analyze:
        # 1. Get Real-Time Price from Alpaca
        current_price = good_value_quick_money_alpaca_trader.get_current_price(ticker)
        
        if not current_price:
            print(f"   > Skipping {ticker}: Could not fetch real-time price.")
            continue # Skip if we can't get a price
        result = analyze_stock(ticker, current_price)
        mark_as_analyzed(ticker)
        
        if result:
            # ... (Check Action/Status/Confidence) ...
            action = result.get('action')
            status = result.get('status')
            conf = result.get('confidence')
            reasoning = result.get('reasoning')
            print(f"   > {ticker} (${current_price}): {action} | {status} | {conf} | {reasoning}")
            
            if action == "BUY" and status == "SAFE" and conf == "HIGH":
                print(f"*** HIGH CONVICTION BUY: {ticker} ***")
                print(f"   > Justification: {reasoning}")
                
                exec_plan = result.get('execution', {})
                
                # USE CONFIG HERE
                good_value_quick_money_alpaca_trader.place_smart_trade(
                    ticker, 
                    config.INVEST_PER_TRADE, # <-- New Setting
                    exec_plan.get('buy_limit'),
                    exec_plan.get('take_profit'),
                    exec_plan.get('stop_loss')
                )
        else: print(f" No actionable insight for {ticker}.")
        time.sleep(5)
        
    print("--- [GOOD VALUE QUICK MONEY BOT] Daily Scan Complete ---")


@main_routes.route('/tradingbot')
def trigger_good_value_quick_money_scan():
    """
    Triggered by UptimeRobot once per day (e.g., at 9:45 AM).
    """
    print("--- /tradingbot route hit! Starting background job... ---")
    thread = threading.Thread(target=run_good_value_quick_money_scan)
    thread.start()
    return jsonify(status="good_value_quick_money_scan_started"), 202
# ----------------------------------------------------
# This makes the server run (when run locally)
if __name__ == "__main__":
    # This part is only for local testing, not for Render
    print("Starting Flask server for local testing...")
    app = Flask(__name__)
    app.register_blueprint(main_routes)
    app.run(host='0.0.0.0', port=10000)