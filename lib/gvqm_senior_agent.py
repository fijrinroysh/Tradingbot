import requests
import json
import config
import time
import re
import datetime
import lib.gvqm_senior_prompts as prompts

# ==========================================
# ⚙️ SYSTEM SETUP
# ==========================================
raw_model = getattr(config, 'GEMINI_SENIOR_MODEL', "gemini-3.1-pro-preview")

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
        text = re.sub(r'^```json\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text, flags=re.IGNORECASE)
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1: 
            return text[start : end+1]
        return text
    except: return text

# ==========================================
# 📡 CORE API ENGINE
# ==========================================
def _call_gemini_api(prompt, context_label="Request"):
    """Centralized API caller with Local File Debugging."""
    
    # --- 📝 DEBUG: Save Prompt to File ---
    if getattr(config, 'DEBUG_MODE', False):
        try:
            with open("senior_prompt_debug.txt", "a", encoding="utf-8") as f:
                f.write(f"\n{'='*50}\n👨‍💼 [SENIOR] PROMPT FOR: {context_label}\n{'-'*50}\n{prompt}\n{'='*50}\n")
        except Exception as e:
            pass

    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    gen_config = {"response_mime_type": "application/json"}
    thinking_level = getattr(config, 'SENIOR_THINKING_LEVEL', 'HIGH').upper()

    if "3." in MODEL_NAME or "thinking" in MODEL_NAME.lower():
        gen_config["thinkingConfig"] = {"thinkingLevel": thinking_level}
    else:
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
            throttle = getattr(config, 'API_THROTTLE_SECONDS', 0)
            if throttle > 0:
                time.sleep(throttle)
                
            response = requests.post(
                BASE_URL + f"?key={API_KEY}",
                headers={'Content-Type': 'application/json'},
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
                
                # --- 📝 DEBUG: Save Response to File ---
                if getattr(config, 'DEBUG_MODE', False):
                    try:
                        with open("senior_response_debug.txt", "a", encoding="utf-8") as f:
                            f.write(f"\n{'='*50}\n👨‍💼 [SENIOR] RESPONSE FOR: {context_label}\n{'-'*50}\n{raw_text}\n{'='*50}\n")
                    except Exception as e:
                        pass

                cleaned = clean_json_text(raw_text)
                return json.loads(cleaned)
                
            elif response.status_code == 429:
                log_debug(f"⚠️ Quota Exceeded (429). Waiting 60s for API bucket to reset...")
                time.sleep(60)
                continue
                
            elif response.status_code in [500, 502, 503, 504]:
                wait_time = (attempt + 1) * 10
                log_debug(f"⚠️ Server Error ({response.status_code}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
                
            else:
                log_debug(f"❌ API Error {response.status_code}: {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            log_debug(f"⚠️ API timed out. Retrying ({attempt+1}/{max_retries})...")
            time.sleep(5)
            continue
        except requests.exceptions.ConnectionError as e:
            log_debug(f"⚠️ Connection dropped by server: {e}. Retrying ({attempt+1}/{max_retries})...")
            time.sleep(5)
            continue
        except Exception as e:
            log_debug(f"⚠️ Attempt {attempt+1}/{max_retries} Failed: {e}")
            time.sleep(2)
            continue
            
    log_debug(f"❌ Failed to get valid response after {max_retries} attempts.")
    return None


# ==========================================
# 🥊 PHASE 2: THE HEAVYWEIGHT FIGHT
# ==========================================
def evaluate_matchup(candidate_a, candidate_b, risk_factor="Neutral", prev_context=None):
    """
    The 'Scout' Prompt. Evaluates two elite stocks to adjust the All-Time Elo.
    """
    ticker_a = candidate_a.get('ticker')
    ticker_b = candidate_b.get('ticker')
    
    log_debug(f"🤖 Analyzing Major League Matchup: {ticker_a} vs {ticker_b}...")

    prompt = prompts.SENIOR_MATCHUP_PROMPT.format(
        ticker_a=ticker_a, 
        ticker_b=ticker_b
    )
    
    # Removed the duplicate debug writing from here, since _call_gemini_api handles it natively!
    return _call_gemini_api(prompt, context_label=f"{ticker_a}_vs_{ticker_b}")


# ==========================================
# 📝 PHASE 3: THE PAPERWORK
# ==========================================
def generate_execution_paperwork(ticker, current_price):
    """
    The 'Paperwork' Prompt. 
    Triggered ONLY when the math decides a swap is required, or a stop needs trailing.
    """
    log_debug(f"📝 Drafting execution paperwork for {ticker} at ${current_price}...")

    prompt = prompts.SENIOR_PAPERWORK_PROMPT.format(
        ticker=ticker, 
        current_price=current_price
    )
    
    trade_plan = _call_gemini_api(prompt, context_label=f"Paperwork_{ticker}")
    
    # Extra safety net to prevent 0.00 stop loss executions
    if trade_plan:
        if trade_plan.get("stop_loss") == 0.0 or trade_plan.get("take_profit") == 0.0:
            log_debug(f"⚠️ AI returned 0.00 for stops. Rejecting paperwork.")
            return None
        log_debug(f"✅ Paperwork Approved. Action: {trade_plan.get('action')}. Stop Loss: ${trade_plan.get('stop_loss')}.")
        
    return trade_plan