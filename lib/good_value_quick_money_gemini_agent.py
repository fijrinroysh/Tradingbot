import requests
import json
import config
import time
import lib.good_value_quick_money_prompts as prompts
import os
import re

# 1. Get API Key
API_KEY = getattr(config, 'GEMINI_API_KEY', None) or os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("CRITICAL ERROR: GEMINI_API_KEY is missing.")

# 2. Define Model Endpoint
raw_model_name = getattr(config, 'GEMINI_MODEL_NAME', "models/gemini-2.0-flash")
MODEL_NAME = raw_model_name.replace("models/", "")
BASE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

def clean_json_text(text):
    """Robustly extracts JSON from markdown wrappers."""
    try:
        text = text.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            return text[start : end+1]
        return text
    except:
        return text

def analyze_stock(ticker, current_price):
    print(f"🤖 [AGENT] Analyzing {ticker} (Price: ${current_price:.2f})")
    print(f"   Using Model: {MODEL_NAME} via REST API")
    
    prompt_text = prompts.HEDGE_FUND_PROMPT.format(ticker=ticker, current_price=current_price)
    
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "tools": [{"googleSearch": {}}] 
    }
    
    url = f"{BASE_URL}?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}

    # --- RETRY LOGIC FOR 503/429 ERRORS ---
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            
            # If successful (200), break the loop and continue
            if response.status_code == 200:
                break
            
            # If Overloaded (503) or Rate Limited (429), wait and retry
            if response.status_code in [429, 503]:
                wait_time = (attempt + 1) * 10 # Wait 10s, then 20s, then 30s
                print(f"   ⚠️ API Busy/Overloaded ({response.status_code}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            # If other error (400, 403), stop immediately
            print(f"❌ [AGENT] API Error ({response.status_code}): {response.text}")
            return None

        except Exception as e:
            print(f"❌ [AGENT] Connection Failed: {e}")
            return None
    else:
        # This executes if the loop finishes without 'break' (all retries failed)
        print(f"❌ [AGENT] Failed after {max_retries} attempts. Skipping {ticker}.")
        return None
    # --------------------------------------

    # 6. Parse Response (Only reached if status_code == 200)
    try:
        result_json = response.json()
        candidates = result_json.get('candidates', [])
        if not candidates: 
            print("❌ [AGENT] Error: No response candidates returned.")
            return None
        
        # Check Grounding
        grounding = candidates[0].get('groundingMetadata', {}).get('searchEntryPoint')
        if grounding:
            print(f"   ✅ Google Search Used")
        else:
            print(f"   ⚠️ Search NOT Used (Internal knowledge only)")

        # Extract Text
        content_parts = candidates[0].get('content', {}).get('parts', [])
        if not content_parts: return None
        text_response = content_parts[0].get('text', "")

        # 7. Decode JSON
        try:
            cleaned_text = clean_json_text(text_response)
            analysis = json.loads(cleaned_text)
            print(f"   📝 Verdict: {analysis.get('action')} | Risk: {analysis.get('status')}")
            return analysis
        except json.JSONDecodeError:
            print(f"❌ [AGENT] Failed to parse JSON.")
            return None

    except Exception as e:
        print(f"❌ [AGENT] Parsing Exception: {e}")
        return None