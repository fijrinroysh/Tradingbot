import requests
import json
import config
import time
import lib.gvqm_senior_prompts as prompts
import re
import datetime

# 1. Setup Model
raw_model = getattr(config, 'GEMINI_SENIOR_MODEL', "gemini-3.1-pro-preview")

# Ensure clean formatting for the REST API
if raw_model.startswith("models/"):
    MODEL_NAME = raw_model.replace("models/", "")
else:
    MODEL_NAME = raw_model

API_KEY = config.GEMINI_API_KEY
if not API_KEY:
    print("⚠️ [SENIOR] CRITICAL WARNING: GEMINI_API_KEY is missing.")

BASE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

def log_debug(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [SENIOR_AGENT] {message}")

def clean_json_text(text):
    try:
        text = text.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1: 
            return text[start : end+1]
        return text
    except: return text

def visualize_decision(candidates, decision):
    """Prints a human-readable 'Reality vs Decision' matrix for DUAL STRATEGY."""
    print("\n" + "="*80)
    print(f"📊 SENIOR DUAL-STRATEGY MATRIX ({len(candidates)} Candidates)")
    print("="*80)
    print(f"{'TICKER':<8} | {'STRATEGY':<10} | {'SCORE':<6} | {'ACTION':<15} | {'REASON'}")
    print("-" * 80)

    # decision['final_execution_orders'] is a list of DUAL OBJECTS
    dual_orders = decision.get('final_execution_orders', [])
    dec_map = {d['ticker']: d for d in dual_orders}

    for cand in candidates:
        ticker = cand.get('ticker')
        res = dec_map.get(ticker)
        
        if res:
            # Print Position Row
            if 'position_trade_analysis' in res:
                p = res['position_trade_analysis']
                print(f"{ticker:<8} | {'Position':<10} | {str(p.get('score')):<6} | {p.get('verdict'):<15} | {p.get('rationale')[:40]}...")

            # Print Swing Row
            if 'swing_trade_analysis' in res:
                s = res['swing_trade_analysis']
                print(f"{ticker:<8} | {'Swing':<10} | {str(s.get('score')):<6} | {s.get('verdict'):<15} | {s.get('rationale')[:40]}...")
            
            print("-" * 80)
        else:
            print(f"{ticker:<8} | {'SKIPPED':<10} | {'-':<6} | {'NO DECISION':<15} | ...")

    print("="*80 + "\n")

# --- HELPER: BIAS REMOVAL ---
def _remove_bias(candidate):
    """Removes bias text from a single candidate before prompt formatting."""
    clean_candidate = candidate.copy()
    bias_fields = [
        "Date",
        "Log_Price",
        "Position_Score",
        "Position_Verdict",
        "Position_Rationale",
        "Position_Action",
        "Swing_Score",
        "Swing_Verdict",
        "Swing_Rationale",
        "Swing_Action",
        "_wins",
        "_losses",
         "_daily_elo",
        "_senior_decision",
        "days_held",
        "avg_entry_price"
    ]
    for field in bias_fields:
        clean_candidate.pop(field, None)
    return clean_candidate


# --- THE NEW EVALUATE MATCHUP LOGIC ---
def evaluate_matchup(candidate_a, candidate_b, risk_factor="Neutral", prev_context=None):
    ticker_a = candidate_a.get('ticker')
    ticker_b = candidate_b.get('ticker')
    
    log_debug(f"🤖 [SENIOR AGENT] Analyzing Matchup: {ticker_a} vs {ticker_b} using {MODEL_NAME}...")

    # --- 🙈 THE BLIND TEST FILTER (Applied to Both) ---
    clean_a = _remove_bias(candidate_a)
    clean_b = _remove_bias(candidate_b)
    
    cand_a_str = json.dumps(clean_a, indent=2)
    cand_b_str = json.dumps(clean_b, indent=2)
    
    try:
        prompt = prompts.SENIOR_MANAGER_PROMPT.format(
            risk_factor=risk_factor,
            candidate_A_data=cand_a_str,
            candidate_B_data=cand_b_str 
        )
        
        # --- 📝 DEBUG: Write Senior Prompt ---
        if getattr(config, 'DEBUG_MODE', False):
            try:
                # Append mode so tournament matchups aren't overwritten
                with open("senior_prompt_debug.txt", "a", encoding="utf-8") as f:
                    f.write(f"\n--- DEBUG FOR {ticker_a}_vs_{ticker_b} ---\n")
                    f.write(prompt)
                    f.write("\n=========================================\n")
            except Exception as e:
                log_debug(f"⚠️ Failed to write prompt debug: {e}")

    except Exception as e:
        log_debug(f"❌ PROMPT FORMAT ERROR: {e}")
        return None
        
    # Safety Settings
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

    # Pull the desired thinking level from your config (defaults to HIGH if missing)
    thinking_level = getattr(config, 'SENIOR_THINKING_LEVEL', 'HIGH').upper()

    # Gemini 3.x series uses thinkingLevel, as do legacy "thinking" models
    if "3." in MODEL_NAME or "thinking" in MODEL_NAME.lower():
        gen_config["thinkingConfig"] = {"thinkingLevel": thinking_level}
    else:
        # Fallback for older models
        gen_config["temperature"] = 0.2 
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"googleSearch": {}}],
        "safetySettings": safety_settings,
        "generationConfig": gen_config
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 🛑 NEW: DYNAMIC CONFIGURABLE THROTTLE
            throttle = getattr(config, 'API_THROTTLE_SECONDS', 0)
            if throttle > 0:
                log_debug(f"⏳ Throttling API request for {throttle} seconds (Attempt {attempt+1})...")
                time.sleep(throttle)
                
            # ✅ NEW: The 120-second strict timeout prevents infinite hanging!
            # Since Senior logic is deep, 120s is safer for the PRO model
            response = requests.post(
                BASE_URL + f"?key={API_KEY}",
                headers={'Content-Type': 'application/json'},
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
                
                # --- 📝 DEBUG: Write Senior Response ---
                if getattr(config, 'DEBUG_MODE', False):
                    try:
                        # Append mode
                        with open("senior_response_debug.txt", "a", encoding="utf-8") as f:
                            f.write(f"\n--- RAW RESPONSE FOR {ticker_a}_vs_{ticker_b} ---\n")
                            f.write(raw_text)
                            f.write("\n=========================================\n")
                    except Exception as e:
                        log_debug(f"⚠️ Failed to write response debug: {e}")

                cleaned = clean_json_text(raw_text)
                return json.loads(cleaned)
            # 🛑 NEW: Dedicated Rate Limit Handler
            elif response.status_code == 429:
                # If we hit the limit, wait a full 60 seconds to clear the penalty box
                print(f"   ⚠️ Quota Exceeded (429). Waiting 60s for API bucket to reset...")
                time.sleep(60)
                continue
                
            # Standard server errors (500s)
            elif response.status_code in [500, 502, 503, 504]:
                wait_time = (attempt + 1) * 10
                print(f"   ⚠️ Server Error ({response.status_code}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue

                
            else:
                log_debug(f"❌ API Error {response.status_code}: {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            # Explicitly catching the infinite hang
            log_debug(f"⚠️ API timed out after 120 seconds. Retrying ({attempt+1}/{max_retries})...")
            time.sleep(5)
            continue
            
        except requests.exceptions.ConnectionError as e:
            # Catches "Silent Drops" where Google drops the connection
            log_debug(f"⚠️ Connection dropped by server: {e}. Retrying ({attempt+1}/{max_retries})...")
            time.sleep(5)
            continue
            
        except Exception as e:
            log_debug(f"⚠️ Attempt {attempt+1}/{max_retries} Failed: {e}")
            time.sleep(2)
            continue
            
    log_debug(f"❌ Failed to analyze Matchup {ticker_a} vs {ticker_b} after {max_retries} attempts.")
    return None