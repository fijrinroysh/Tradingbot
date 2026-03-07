import requests
import json
import config
import time
import lib.gvqm_junior_prompts as prompts
import re
import os

# 1. Setup Model
raw_model = getattr(config, 'GEMINI_JUNIOR_MODEL', "gemini-3.1-pro-preview")

# Ensure clean formatting for the REST API
if raw_model.startswith("models/"):
    MODEL_NAME = raw_model.replace("models/", "")
else:
    MODEL_NAME = raw_model

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

# --- UPGRADED FOR 1v1 MATCHMAKING ---
def evaluate_matchup(candidate_a, candidate_b):
    ticker_a = candidate_a.get('ticker', candidate_a.get('Ticker', 'UNKNOWN'))
    price_a = candidate_a.get('current_price', candidate_a.get('Price', 0.0))
    
    ticker_b = candidate_b.get('ticker', candidate_b.get('Ticker', 'UNKNOWN'))
    price_b = candidate_b.get('current_price', candidate_b.get('Price', 0.0))

    print(f"🤖 [JUNIOR] Matchup Analysis: {ticker_a} vs {ticker_b} using {MODEL_NAME}...")
    
    # Using the new dual-input prompt format
    prompt = prompts.HEDGE_FUND_PROMPT.format(
        ticker_A=ticker_a, price_A=price_a,
        ticker_B=ticker_b, price_B=price_b
    )
    
    # --- 📝 DEBUG: Write Junior Prompt ---
    if getattr(config, 'DEBUG_MODE', False):
        try:
            with open("junior_prompt_debug.txt", "w", encoding="utf-8") as f:
                f.write(f"--- DEBUG FOR {ticker_a}_vs_{ticker_b} ---\n")
                f.write(prompt)
        except Exception as e:
            print(f"   ⚠️ Failed to write prompt debug: {e}")
            
    # Safety Settings (Block None to prevent refusals)
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    # 🎯 DYNAMIC GENERATION CONFIGURATION
    gen_config = {
        "response_mime_type": "application/json"
    }

    # Pull the desired thinking level from your config (defaults to LOW if missing)
    thinking_level = getattr(config, 'JUNIOR_THINKING_LEVEL', 'LOW').upper()

    # Gemini 3.x series uses thinkingLevel, as do legacy "thinking" models
    if "3." in MODEL_NAME or "thinking" in MODEL_NAME.lower():
        gen_config["thinkingConfig"] = {"thinkingLevel": thinking_level}
    else:
        # Fallback for Gemini 1.5 and standard 2.0 Flash
        gen_config["temperature"] = 0.2 
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}], 
        "tools": [{"googleSearch": {}}],         # ✅ GROUNDING RETAINED
        "safetySettings": safety_settings,
        "generationConfig": gen_config           # ✅ DYNAMIC THINKING CONFIG APPLIED
    }
    
    # Retry Loop
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # ⏱️ The 90-second strict timeout prevents infinite hanging!
            response = requests.post(
                f"{BASE_URL}?key={API_KEY}", 
                headers={'Content-Type': 'application/json'}, 
                data=json.dumps(payload),
                timeout=90  
            )
            
            if response.status_code == 200:
                result_json = response.json()
                try:
                    candidates = result_json.get('candidates', [])
                    if not candidates: return None
                    
                    parts = candidates[0].get('content', {}).get('parts', [])
                    if not parts: return None
                        
                    text = parts[0].get('text', "")

                    # --- 📝 DEBUG: Write Junior Response ---
                    if getattr(config, 'DEBUG_MODE', False):
                        try:
                            # Use append mode so we don't overwrite multiple matchups
                            with open("junior_response_debug.txt", "a", encoding="utf-8") as f:
                                f.write(f"\n--- RAW RESPONSE FOR {ticker_a}_vs_{ticker_b} ---\n")
                                f.write(text)
                                f.write("\n=========================================\n")
                        except Exception as e:
                            print(f"   ⚠️ Failed to write response debug: {e}")
                    
                    # --- NEW ROBUST CLEANING ---
                    cleaned_json = clean_json_text(text)
                    
                    if not cleaned_json:
                        print(f"   ⚠️ Response contained no JSON. Raw: {text[:50]}...")
                        return None
                        
                    return json.loads(cleaned_json)
                    # ---------------------------

                except json.JSONDecodeError:
                    print(f"   ❌ JSON Decode Error. Content was not valid JSON.")
                    return None
                except Exception as e:
                    print(f"   ❌ Parsing Structure Error: {e}")
                    return None
            
            # Explicitly catch 502 (Bad Gateway), 429 (Rate Limit) and other server errors
            elif response.status_code in [429, 500, 502, 503, 504]:
                wait = (attempt + 1) * 10
                print(f"   ⚠️ API Busy or Server Error ({response.status_code}). Retrying in {wait}s...")
                time.sleep(wait)
                continue
            
            else:
                # Log full error for 400 Bad Request or other client errors
                print(f"   ❌ API Error {response.status_code}: {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            # Explicitly catching the infinite hang
            print(f"   ⚠️ [JUNIOR] Gemini API timed out after 90 seconds. Retrying ({attempt+1}/{max_retries})...")
            time.sleep(5)
            continue
            
        except requests.exceptions.ConnectionError as e:
            # Catches "Silent Drops" where Google drops the connection
            print(f"   ⚠️ [JUNIOR] Connection dropped by server: {e}. Retrying ({attempt+1}/{max_retries})...")
            time.sleep(5)
            continue
            
        except Exception as e:
            print(f"   ❌ Connection Error: {e}")
            return None
            
    print(f"   ❌ [JUNIOR] Matchup completely failed after {max_retries} retries. Skipping.")
    return None