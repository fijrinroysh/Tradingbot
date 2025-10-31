# (All your imports and Blueprint setup are unchanged)
from flask import Blueprint, jsonify, request
import sentiment_analyzer
import alpaca_trader
import threading
import config

main_routes = Blueprint('main_routes', __name__)

# ----------------------------------------------------
# ROUTE 1: HEALTH CHECK (No Change)
# ----------------------------------------------------
@main_routes.route('/health')
def health_check():
    return jsonify(status="ok"), 200

# ----------------------------------------------------
# ROUTE 2: SENTIMENT TRADER (UPDATED)
# ----------------------------------------------------

def process_ticker_sentiment(ticker, trade_value):
    """
    This is the "worker" function for the sentiment bot.
    """
    print(f"--- [Thread: {ticker}] Starting sentiment analysis ---")
    
    score = sentiment_analyzer.get_summary_score(ticker)
    
    print(f"--- [Thread: {ticker}] Score: {score:.4f} ---")

    # --- THIS IS THE ONLY CHANGE ---
    if score >= config.MIN_SENTIMENT_SCORE:
        print(f"--- [Thread: {ticker}] Decision: POSITIVE. Placing BUY order. ---")
        # It now calls the new "notional" function
        alpaca_trader.place_notional_buy_order(ticker, trade_value)
        
    elif score <= config.MAX_SENTIMENT_SCORE:
        print(f"--- [Thread: {ticker}] Decision: NEGATIVE. Closing position. ---")
        alpaca_trader.close_existing_position(ticker)
        
    else:
        print(f"--- [Thread: {ticker}] Decision: NEUTRAL. Holding. ---")
    # --- END OF CHANGE ---

def run_sentiment_logic():
    """
    This is the "master" function for the sentiment bot.
    (This code is unchanged)
    """
    print(f"--- Sentiment logic thread started for all tickers ---")
    threads = []
    
    tickers_to_trade = config.SENTIMENT_TICKERS
    value_to_trade = config.SENTIMENT_TRADE_VALUE
    
    for ticker in tickers_to_trade:
        t = threading.Thread(
            target=process_ticker_sentiment, 
            args=(ticker, value_to_trade)
        )
        threads.append(t)
        t.start()
        print(f"Started worker thread for {ticker}...")

    for t in threads:
        t.join()
        
    print(f"--- All sentiment logic threads have completed. ---")

@main_routes.route('/tradingbot')
def trigger_sentiment_bot():
    """
    (This code is unchanged)
    """
    print(f"--- /tradingbot route hit. Starting background logic. ---")
    thread = threading.Thread(target=run_sentiment_logic)
    thread.start()
    return jsonify(status="sentiment_job_for_all_tickers_started"), 202

# ----------------------------------------------------
# ROUTE 3: TRADINGVIEW WEBHOOK (No Change)
# This route continues to work as-is, calling
# place_buy_order() and place_sell_order()
# ----------------------------------------------------
def process_webhook_trade(trade_data):
    """
    (This code is unchanged)
    """
    if not trade_data:
        print("Webhook Thread: ERROR! No JSON data received.")
        return

    if trade_data.get("secret") != config.TRADINGVIEW_SECRET:
        print(f"Webhook Thread: SECURITY ALERT! Invalid secret. Ignoring trade.")
        return

    try:
        action = trade_data.get("action", "").upper()
        ticker = trade_data.get("symbol", "").upper()
        quantity = float(trade_data.get("qty"))
        
        if not action or not ticker or not quantity:
            raise ValueError("Missing action, symbol, or qty")
            
    except Exception as e:
        print(f"Webhook Thread: ERROR! Invalid/Missing data in JSON. Error: {e}")
        return

    print(f"Webhook Thread: Validated trade: {action} {quantity} {ticker}")
    if action == "BUY":
        alpaca_trader.place_buy_order(ticker, quantity) # Calls the original qty function
    elif action == "SELL":
        alpaca_trader.place_sell_order(ticker, quantity) # Calls the original qty function
    elif action == "CLOSE":
        alpaca_trader.close_existing_position(ticker)
    else:
        print(f"Webhook Thread: Received unknown action: '{action}'. Ignoring.")

@main_routes.route('/webhook', methods=['POST'])
def handle_tradingview_webhook():
    """
    (This code is unchanged)
    """
    try:
        data = request.get_json()
        if not data:
            print("--- /webhook route hit. No JSON data received. ---")
            return jsonify(status="error", message="No JSON data"), 400

        print(f"--- /webhook route hit. Received JSON: {data} ---")
        thread = threading.Thread(target=process_webhook_trade, args=(data,))
        thread.start()
        
        return jsonify(status="webhook_received"), 200
    
    except Exception as e:
        print(f"Error in /webhook route (data was not JSON?): {e}")
        return jsonify(status="error", message=str(e)), 400