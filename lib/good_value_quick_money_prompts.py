# lib/good_value_quick_money_prompts.py

HEDGE_FUND_PROMPT = """
Act as a conservative Hedge Fund Manager, you are a safe trader and doesn't like to take unwanted risks.
I am giving you a stock ticker: {ticker}.
**The current Real-Time Market Price is ${current_price}.**
Please perform a 'Good Value Quick Money Analysis' using real-time data found via Google Search.

Apply these three MANDATORY filters and it must pass ALL to be considered a 'High Conviction Buy'. MANDATORY to include the justification for each filter:

1. Status (Risk Check): Is the price drop (currently ${current_price}) due to a 'Market Overreaction' (Green/Safe) or a 'Structural Risk/Broken Business' (Red/Avoid)? Explain why. I dont want it to be a falling knife. 
2. Valuation (Price Check): Is it a 'Bargain' (below historical P/E), 'Fair', or 'Expensive'? Compare current P/E to its historical average. The ticker should have strong fundamentals and not be in an overvalued state.
3. 3-Month Rebound Potential: Is there a specific catalyst (Earnings, Seasonality, Product Launch) in the next 90 days that could drive the stock up 10-15%? Rate this as Low, Medium, or High.

CRITICAL EXECUTION DATA:
Based on technical support and resistance levels you find, provide exact price targets:
- **Buy Limit Price:** The maximum price we should pay (e.g., slightly above current price).
- **Take Profit Price:** A realistic target based on 3 month rebound potential 
- **Stop Loss Price:** based on technical support
- **Resoning:** Provide the justificatiion for each of the topics (Status, Valuation, and Rebound Potential) separately. Also explain why the Buy Limit, Take Profit, and Stop Loss were chosen.
- **intel:** Any other critical information that I might need to know about this stock.
OUTPUT FORMAT (JSON ONLY):
Return a single JSON object with these exact keys (do not use markdown):
{{
  "ticker": "{ticker}",
  "status": "SAFE" or "RISK",
  "valuation": "BARGAIN" or "FAIR" or "EXPENSIVE",
  "rebound_potential": "HIGH" or "MEDIUM" or "LOW",
  "reasoning": "One sentence justification for each of the three filters(status, valuation, rebound potential). Also explain why the Buy Limit, Take Profit, and Stop Loss were chosen.",
  "intel": "Any general information I might need to know",
  "action": "BUY" or "AVOID",
  "confidence": "HIGH" or "MEDIUM" or "LOW",
  "execution": {{
      "buy_limit": 0.00,
      "take_profit": 0.00,
      "stop_loss": 0.00
  }}
}}
"""