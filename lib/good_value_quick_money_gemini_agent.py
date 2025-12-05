import google.generativeai as genai
from google.generativeai import types
import config # Import Config
import json
import time
import lib.good_value_quick_money_prompts as prompts

if hasattr(config, 'GEMINI_API_KEY'):
    genai.configure(api_key=config.GEMINI_API_KEY)

# --- USE CONFIG MODEL NAME ---
MODEL_NAME = getattr(config, 'GEMINI_MODEL_NAME', "models/gemini-2.5-pro")
# -----------------------------

# Configure Search Tool
tools = [
    types.Tool(
        google_search_retrieval=types.GoogleSearchRetrieval(
            disable_attribution=False
        )
    )
]

model = genai.GenerativeModel(MODEL_NAME, tools=tools)

def analyze_stock(ticker):
    print(f"Agent: Analyzing {ticker} with {MODEL_NAME} & Search...")
    
    prompt = prompts.HEDGE_FUND_PROMPT.format(ticker=ticker)
    
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        
        try:
            return json.loads(response.text)
        except:
            clean = response.text.strip().replace("```json", "").replace("```", "")
            return json.loads(clean)

    except Exception as e:
        print(f"Agent Error on {ticker}: {e}")
        return None