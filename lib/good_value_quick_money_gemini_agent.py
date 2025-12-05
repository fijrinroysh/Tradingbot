import requests
import json
import config
import time
import lib.good_value_quick_money_prompts as prompts
import os
import re # Need regex for robust cleaning

# 1. Get API Key
API_KEY = getattr(config, 'GEMINI_API_KEY', None) or os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("CRITICAL ERROR: GEMINI_API_KEY is missing.")

# 2. Define Model Endpoint
raw_model_name = getattr(config, 'GEMINI_MODEL_NAME', "models/gemini-2.0-flash")
MODEL_NAME = raw_model_name.replace("models/", "")
BASE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

def clean_json_text(text):
    """
    Robustly extracts JSON from a model response that might contain
    markdown or conversational filler.
    """
    # 1. Remove Markdown code blocks
    text = text.strip()
    if "```" in text:
        text = text.replace("```json", "").replace("```", "")
    
    # 2. Find the first '{' and last '}' to isolate the object
    # This fixes cases where the model says "Here is the analysis: { ... }"
    start = text.find('{')
    end = text.rfind('}')
    
    if start != -1 and end != -1:
        text = text[start : end+1]
        
    return text

def analyze_stock(ticker,current_price):
    
    print(f"Agent: Analyzing {ticker} @ ${current_price} with {MODEL_NAME} & Search...")
    
    
    # Pass the price to the prompt
    prompt_text = prompts.HEDGE_FUND_PROMPT.format(ticker=ticker, current_price=current_price)
    
    # 3. Construct the Payload
    # REMOVED: "generationConfig": {"responseMimeType": "application/json"}
    # We rely on the prompt to request JSON format.
    payload = {
        "contents": [{
            "parts": [{"text": prompt_text}]
        }],
        "tools": [
            {"googleSearch": {}} 
        ]
    }
    
    try:
        # 4. Send Request
        url = f"{BASE_URL}?key={API_KEY}"
        headers = {'Content-Type': 'application/json'}
        
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        
        # 5. Handle Errors
        if response.status_code != 200:
            print(f"Agent API Error ({response.status_code}): {response.text}")
            return None
            
        # 6. Parse Response
        result_json = response.json()
        
        try:
            candidates = result_json.get('candidates', [])
            if not candidates: return None
                
            content = candidates[0].get('content', {})
            parts = content.get('parts', [])
            if not parts: return None
                
            text_response = parts[0].get('text', "")
            
            # Debug: Confirm Search was used
            grounding_meta = candidates[0].get('groundingMetadata', {})
            if grounding_meta.get('searchEntryPoint'):
                print(f"   > [Verified] Google Search was used.")

            # 7. Parse the JSON output (using our robust cleaner)
            try:
                cleaned_text = clean_json_text(text_response)
                return json.loads(cleaned_text)
            except json.JSONDecodeError as e:
                print(f"Agent: Failed to decode JSON. Text was:\n{text_response[:100]}...")
                return None
                
        except Exception as parse_error:
            print(f"Agent: Failed to parse response structure: {parse_error}")
            return None

    except Exception as e:
        print(f"Agent Connection Error on {ticker}: {e}")
        return None