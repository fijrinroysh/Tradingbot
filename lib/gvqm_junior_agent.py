import requests
import json
import config
import time
import lib.gvqm_junior_prompts as prompts
import re
import os

# 1. Setup Model
raw_model = getattr(config, 'GEMINI_JUNIOR_MODEL', "gemini-2.0-flash")
MODEL_NAME = raw_model.replace("models/", "")

API_KEY = config.GEMINI_API_KEY
if not API_KEY:
    print("⚠️ [JUNIOR] CRITICAL WARNING: GEMINI_API_KEY is missing.")

BASE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

def clean_json_text(text):
    """
    Scans the text for the first JSON object using Regex.
    Returns None if no JSON object is found.
    """
    try:
        # Look for the first '{' and the last '}' across multiple lines
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return match.group(0)
        else:
            return None
    except:
        return None

def analyze_stock(ticker, current_price):
    print(f"🤖 [JUNIOR] Analyzing {ticker} using {MODEL_NAME}...")
    
    prompt = prompts.HEDGE_FUND_PROMPT.format(ticker=ticker, current_price=current_price)
    
    # Safety Settings (Block None to prevent refusals)
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}], 
        "tools": [{"googleSearch": {}}],
        "safetySettings": safety_settings 
    }
    
    # Retry Loop
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{BASE_URL}?key={API_KEY}", 
                headers={'Content-Type': 'application/json'}, 
                data=json.dumps(payload)
            )
            
            if response.status_code == 200:
                result_json = response.json()
                try:
                    candidates = result_json.get('candidates', [])
                    if not candidates: return None
                    
                    parts = candidates[0].get('content', {}).get('parts', [])
                    if not parts: return None
                        
                    text = parts[0].get('text', "")
                    
                    # --- NEW ROBUST CLEANING ---
                    cleaned_json = clean_json_text(text)
                    
                    if not cleaned_json:
                        print(f"   ⚠️ Response contained no JSON. Raw: {text[:50]}...")
                        # If the AI was chatty, we treat it as a fail and maybe retry or skip
                        return None
                        
                    return json.loads(cleaned_json)
                    # ---------------------------

                except json.JSONDecodeError:
                    print(f"   ❌ JSON Decode Error. Content was not valid JSON.")
                    return None
                except Exception as e:
                    print(f"   ❌ Parsing Structure Error: {e}")
                    return None
            
            elif response.status_code in [429, 503]:
                wait = (attempt + 1) * 10
                print(f"   ⚠️ API Busy ({response.status_code}). Retrying in {wait}s...")
                time.sleep(wait)
                continue
            
            else:
                print(f"   ❌ API Error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            print(f"   ❌ Connection Error: {e}")
            return None
            
    return None