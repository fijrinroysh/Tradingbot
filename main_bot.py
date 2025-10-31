# main_bot.py
# This is the main file you run to start the bot.

# Import our custom files
import sentiment_analyzer
import alpaca_trader

# --- Bot Settings ---
STOCK_TICKER = "INFY"  # What to trade
ORDER_QUANTITY = 2     # How much to trade
MIN_SENTIMENT_SCORE = 0.15  # How positive the news must be to buy
MAX_SENTIMENT_SCORE = -0.15 # How negative the news must be to sell


def run_sentiment_bot():
    """
    Runs the main trading logic.
    """
    print(f"--- Running Sentiment Bot for {STOCK_TICKER} ---")
    
    # 1. Get Sentiment
    # This calls the function from sentiment_analyzer.py
    score = sentiment_analyzer.get_summary_score(STOCK_TICKER)
    
    print("-------------------------------------------------")
    print(f"Overall {STOCK_TICKER} Sentiment Score: {score:.4f}")
    print("-------------------------------------------------")

    # 2. Make Trading Decision
    # This is the core "logic" of your bot
    if score >= MIN_SENTIMENT_SCORE:
        print("Decision: STRONG POSITIVE. Sending BUY order.")
        # This calls the function from alpaca_trader.py
        alpaca_trader.place_buy_order(STOCK_TICKER, ORDER_QUANTITY)
        
    elif score <= MAX_SENTIMENT_SCORE:
        print("Decision: STRONG NEGATIVE. Sending CLOSE position order.")
        # This calls the function from alpaca_trader.py
        alpaca_trader.close_existing_position(STOCK_TICKER)
        
    else:
        print(f"Decision: NEUTRAL ({score:.4f}). Holding position.")
    
    print("--- Bot run complete. ---")

# --- This line makes the script runnable ---
if __name__ == "__main__":
    run_sentiment_bot()