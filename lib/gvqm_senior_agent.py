import requests
import json
import config
import time
import lib.gvqm_senior_prompts as prompts
import re
import datetime
import traceback

# 1. Setup Model
raw_model = getattr(config, 'GEMINI_SENIOR_MODEL', "gemini-1.5-pro")
MODEL_NAME = raw_model.replace("models/", "")
API_KEY = config.GEMINI_API_KEY
BASE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

def log_debug(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [SENIOR_AGENT] {message}")

def save_debug_file(filename, content):
    """
    Helper to save debug artifacts.
    CRITICAL: Only runs if DEBUG_MODE is True.
    """
    if getattr(config, 'DEBUG_MODE', False):
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(str(content))
            log_debug(f"🐛 [DEBUG] Saved {filename}")
        except Exception as e:
            # Silent fail in production logic to avoid stopping the trade
            print(f"⚠️ Debug Write Failed for {filename}: {e}")

def clean_json_text(text):
    """
    Robust JSON extraction. 
    Removes markdown, finds the first '{' and last '}'.
    """
    try:
        text = text.strip()
        # Remove markdown code blocks
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        
        # Find the JSON object
        start = text.find('{')
        end = text.rfind('}')
        
        if start != -1 and end != -1: 
            return text[start : end+1]
        return text
    except: return text

def visualize_decision(candidates, decision):
    """Prints a human-readable 'Reality vs Decision' matrix."""
    print("\n" + "="*60)
    print(f"📊 SENIOR DECISION MATRIX ({len(candidates)} Candidates)")
    print("="*60)
    print(f"{'TICKER':<8} | {'SCORE':<6} | {'ACTION':<15} | {'REASON'}")
    print("-" * 60)

    dec_map = {d['ticker']: d for d in decision.get('final_execution_orders', [])}

    for cand in candidates:
        ticker = cand.get('ticker')
        res = dec_map.get(ticker, {})
        
        score = res.get('conviction_score', '-')
        action = res.get('action', 'SKIPPED')
        reason = res.get('reason', 'No decision made.')[:50]
        
        # Color coding
        if action == "OPEN_NEW": action_str = f"\033[92m{action}\033[0m"
        elif action == "UPDATE_EXISTING": action_str = f"\033[94m{action}\033[0m"
        else: action_str = action

        print(f"{ticker:<8} | {str(score):<6} | {action_str:<24} | {reason}")
    print("="*60 + "\n")

# ==============================================================================
# 🧠 CORE LOGIC: SINGLE TICKER ANALYSIS
# ==============================================================================

def analyze_single_ticker(candidate, risk_factor="Neutral", prev_context=None):
    """
    Analyzes ONE stock in isolation using Google Search & Retry Logic.
    Includes PRODUCTION-SAFE Debug Logging.
    """
    ticker = candidate.get('ticker')
    log_debug(f"🤖 [SENIOR AGENT] Analyzing Single Ticker: {ticker}...")
    
    # 1. Format Data
    candidate_str = json.dumps(candidate, indent=2)
    
    # 2. Prepare Prompt
    try:
        prompt = prompts.SENIOR_MANAGER_PROMPT.format(
            risk_factor=risk_factor,
            candidate_data=candidate_str,
            candidates_data=candidate_str, # Fallback alias
            ticker=ticker,
            count="1"
        )
    except Exception as e:
        log_debug(f"❌ PROMPT FORMAT ERROR: {e}")
        return None

    # 🐛 DEBUG 1: DUMP PROMPT (Only if Debug Mode)
    save_debug_file("senior_prompt_debug.txt", prompt)
    
    # 3. Call AI with RETRY LOOP
    for attempt in range(3):
        try:
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                # ✅ Google Search for Grounding
                "tools": [{"googleSearch": {}}],
                "generationConfig": {"response_mime_type": "application/json"}
            }

            response = requests.post(
                BASE_URL + f"?key={API_KEY}",
                headers={'Content-Type': 'application/json'},
                json=payload
            )
            
            if response.status_code == 200:
                try:
                    raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
                    
                    # 🐛 DEBUG 2: DUMP RAW RESPONSE (Only if Debug Mode)
                    save_debug_file("senior_response_debug.txt", raw_text)
                    
                    cleaned = clean_json_text(raw_text)
                    return json.loads(cleaned)

                except Exception as parse_error:
                    # 🐛 DEBUG 3: DUMP ERROR RESPONSE (JSON Fail)
                    error_log = f"JSON PARSE ERROR: {parse_error}\n\nRAW TEXT:\n{raw_text}"
                    save_debug_file("senior_response_ERROR_debug.txt", error_log)
                    log_debug(f"❌ JSON Parse Error on attempt {attempt+1}")
                    return None
            
            elif response.status_code in [429, 503]:
                wait_time = (attempt + 1) * 5
                log_debug(f"⚠️ API Busy ({response.status_code}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
                
            else:
                # 🐛 DEBUG 3: DUMP ERROR RESPONSE (API Fail)
                error_msg = f"API STATUS: {response.status_code}\nRESPONSE: {response.text}"
                save_debug_file("senior_response_ERROR_debug.txt", error_msg)
                log_debug(f"❌ API Error {response.status_code}")
                return None
                
        except Exception as e:
            log_debug(f"⚠️ Attempt {attempt+1}/3 Failed: {e}")
            # 🐛 DEBUG 3: DUMP EXCEPTION
            save_debug_file("senior_response_ERROR_debug.txt", traceback.format_exc())
            time.sleep(2)
            
    log_debug(f"❌ Failed to analyze {ticker} after 3 attempts.")
    return None