from flask import Flask
import sentiment_analyzer
import alpaca_trader

# Create the web server app
app = Flask(__name__)

# --- Bot Settings ---
STOCK_TICKER = "AAPL"
ORDER_QUANTITY = 2
MIN_SENTIMENT_SCORE = 0.15
MAX_SENTIMENT_SCORE = -0.15


@app.route('/health')
def health_check():
    """
    This endpoint is used by keep-alive services like UptimeRobot
    to confirm the app is running.
    """
    # Returns a JSON response with a 200 OK status
    return jsonify(status="ok"), 200
# ----------------------------------------------------

# This is the main function that UptimeRobot will call
@app.route('/tradingbot')
def run_sentiment_bot():
    """
    Runs the main trading logic when the URL is visited.
    """
    print(f"--- Bot triggered by web request ---")

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
    print("--- Bot run complete. ---")

    # Return a simple message to UptimeRobot
    return f"Bot run complete. Decision: {decision}"

# This makes the server run
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)