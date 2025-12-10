import requests
import json
import config
import time
import lib.gvqm_senior_prompts as prompts
import re

# 1. Setup Model
raw_model = getattr(config, 'GEMINI_SENIOR_MODEL', "gemini-3-pro-preview")
MODEL_NAME = raw_model.replace("models/", "")
API_KEY = config.GEMINI_API_KEY
BASE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

def clean_json_text(text):
    try:
        text = text.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1: return text[start : end+1]
        return text
    except: return text

def rank_portfolio(candidates_list, top_n=5, lookback_days=10, prev_context=None):
    print(f"\n👨‍💼 [SENIOR] Reviewing {len(candidates_list)} candidates using {MODEL_NAME}...")
    
    if not prev_context: prev_context = {"date": "None", "top_tickers": "None"}
    
    prompt = prompts.SENIOR_MANAGER_PROMPT.format(
        count=len(candidates_list),
        max_trades=top_n,
        lookback=lookback_days,
        prev_date=prev_context.get('date'),
        prev_picks=prev_context.get('top_tickers'),
        candidates_data=json.dumps(candidates_list, indent=2)
    )

    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}], 
        "tools": [{"googleSearch": {}}], # Senior MUST verify info
        "safetySettings": safety_settings
    }
    
    # --- SMART RETRY LOOP ---
    for attempt in range(3):
        try:
            response = requests.post(f"{BASE_URL}?key={API_KEY}", headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
            
            if response.status_code == 200:
                try:
                    text = response.json()['candidates'][0]['content']['parts'][0]['text']
                    return json.loads(clean_json_text(text))
                except Exception as e:
                    print(f"   ❌ Senior Parsing Error: {e}")
                    return None
            elif response.status_code in [429, 503]:
                time.sleep((attempt + 1) * 10)
                continue
            else:
                print(f"   ❌ Senior API Error ({response.status_code}): {response.text}")
                return None
        except Exception as e:
            print(f"   ❌ Senior Connection Error: {e}")
            return None
    return None