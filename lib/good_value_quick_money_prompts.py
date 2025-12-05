# lib/good_value_quick_money_prompts.py

HEDGE_FUND_PROMPT = """
Act as a conservative Hedge Fund Manager looking for safe swing trades.
I am giving you a stock ticker: {ticker}.
Please perform a 'Good Value Quick Money Analysis' using real-time data found via Google Search.

Apply these three MANDATORY filters:

1. Status (Risk Check): Is the price drop due to a 'Market Overreaction' (Green/Safe) or a 'Structural Risk/Broken Business' (Red/Avoid)? Explain why.
2. Valuation (Price Check): Is it a 'Bargain' (below historical P/E), 'Fair', or 'Expensive'? Compare current P/E to its historical average.
3. 3-Month Rebound Potential: Is there a specific catalyst (Earnings, Seasonality, Product Launch) in the next 90 days that could drive the stock up 10-15%? Rate this as Low, Medium, or High.

CRITICAL EXECUTION DATA:
Based on technical support and resistance levels you find, provide exact price targets:
- **Buy Limit Price:** The maximum price we should pay (e.g., slightly above current support).
- **Take Profit Price:** A realistic target for a 2-4 week swing trade.
- **Stop Loss Price:** A technical invalidation level (e.g., below recent low).

OUTPUT FORMAT (JSON ONLY):
Return a single JSON object with these exact keys (do not use markdown):
{{
  "ticker": "{ticker}",
  "status": "SAFE" or "RISK",
  "reasoning": "One sentence explanation.",
  "valuation": "BARGAIN" or "FAIR" or "EXPENSIVE",
  "rebound_potential": "HIGH" or "MEDIUM" or "LOW",
  "catalyst": "The specific event to watch.",
  "action": "BUY" or "AVOID",
  "confidence": "HIGH" or "MEDIUM" or "LOW",
  "execution": {{
      "buy_limit": 0.00,
      "take_profit": 0.00,
      "stop_loss": 0.00
  }}
}}
"""