from flask import Flask, jsonify, request
import config 
import sentiment_analyzer
import alpaca_trader
import threading  # Import the threading library

# Create the web server app
app = Flask(__name__)

# --- Bot Settings ---
STOCK_TICKER = "AAPL"
ORDER_QUANTITY = 2
MIN_SENTIMENT_SCORE = 0.15
MAX_SENTIMENT_SCORE = -0.15

# ----------------------------------------------------
# ROUTE 1: HEALTH CHECK (for 10-minute keep-alive)
# ----------------------------------------------------
@app.route('/health')
def health_check():
    """
    This endpoint is used by a keep-alive service.
    It confirms the app is running.
    """
    return jsonify(status="ok"), 200

# ----------------------------------------------------
# ROUTE 2: TRADING LOGIC (for trade trigger)
# ----------------------------------------------------
def run_trade_logic():
    """
    This contains the actual bot logic.
    It will run in a separate thread so it doesn't block the web request.
    """
    print(f"--- Bot logic thread started ---")
    
    # 1. Get Sentiment
    score = sentiment_analyzer.get_summary_score(STOCK_TICKER)

    print("-------------------------------------------------")
    print(f"Overall {STOCK_TICKER} Sentiment Score: {score:.4f}")
    print("-------------------------------------------------")

    # 2. Make Trading Decision
    decision = "NEUTRAL (HOLD)"
    if score >= MIN_SENTIMENT_SCORE:
        decision = "STRONG POSITIVE (BUY)"
        alpaca_trader.place_buy_order(STOCK_TICKER, ORDER_QUANTITY)
        
    elif score <= MAX_SENTIMENT_SCORE:
        decision = "STRONG NEGATIVE (SELL)"
        alpaca_trader.close_existing_position(STOCK_TICKER)
        
    else:
        decision = f"NEUTRAL ({score:.4f}) (HOLD)"

    print(f"Decision: {decision}")
    print("--- Bot logic thread complete. ---")

@app.route('/tradingbot')
def trigger_sentiment_bot():
    """
    This endpoint is called by your 'hourly' UptimeRobot monitor.
    It starts the trading logic in a background thread and returns
    a response immediately.
    """
    print(f"--- /tradingbot route hit. Starting background thread. ---")
    
    # Create a new thread to run the trading logic
    # This keeps the web request from timing out
    thread = threading.Thread(target=run_trade_logic)
    thread.start()
    
    # Return an "Accepted" response immediately
    return jsonify(status="ok"), 200


# ----------------------------------------------------
# ROUTE 3: TRADINGVIEW WEBHOOK (UPGRADED FOR JSON)
# ----------------------------------------------------

def process_webhook_trade(trade_data):
    """
    Parses the webhook data (now a dictionary) and executes a trade.
    This runs in a background thread.
    """
    if not trade_data:
        print("Webhook Thread: ERROR! No JSON data received.")
        return

    # 1. SECURITY CHECK:
    # We check the 'secret' field from the JSON
    if trade_data.get("secret") != config.TRADINGVIEW_SECRET:
        print(f"Webhook Thread: SECURITY ALERT! Invalid secret. Ignoring trade.")
        return

    # 2. DATA VALIDATION:
    try:
        # Get data from the dictionary, using .get() for safety
        # .upper() handles TradingView's lowercase "buy" or "sell"
        action = trade_data.get("action", "").upper()
        ticker = trade_data.get("symbol", "").upper()
        quantity = float(trade_data.get("qty"))
        
        if not action or not ticker or not quantity:
            raise ValueError("Missing action, symbol, or qty")
            
    except Exception as e:
        print(f"Webhook Thread: ERROR! Invalid/Missing data in JSON. Error: {e}")
        return

    # 3. TRADING LOGIC:
    print(f"Webhook Thread: Validated trade: {action} {quantity} {ticker}")
    if action == "BUY":
        alpaca_trader.place_buy_order(ticker, quantity)
    
    elif action == "SELL":
        alpaca_trader.place_sell_order(ticker, quantity)
    
    elif action == "CLOSE":
        alpaca_trader.close_existing_position(ticker)
    
    else:
        print(f"Webhook Thread: Received unknown action: '{action}'. Ignoring.")

@app.route('/webhook', methods=['POST'])
def handle_tradingview_webhook():
    """
    This endpoint now expects a JSON payload from TradingView.
    """
    try:
        # --- THIS IS THE MAIN CHANGE ---
        # request.get_json() automatically parses JSON into a Python dictionary
        data = request.get_json()
        # --- END OF CHANGE ---
        
        if not data:
            print("--- /webhook route hit. No JSON data received. ---")
            return jsonify(status="error", message="No JSON data"), 400

        print(f"--- /webhook route hit. Received JSON: {data} ---")
        thread = threading.Thread(target=process_webhook_trade, args=(data,))
        thread.start()
        
        return jsonify(status="webhook_received"), 200
    
    except Exception as e:
        # This will catch errors if the data sent isn't valid JSON
        print(f"Error in /webhook route (data was not JSON?): {e}")
        return jsonify(status="error", message=str(e)), 400

# ----------------------------------------------------
# This makes the server run
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)