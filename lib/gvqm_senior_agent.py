import requests
import json
import config
import time
import lib.gvqm_senior_prompts as prompts
import re
import datetime

# 1. Setup Model
raw_model = getattr(config, 'GEMINI_SENIOR_MODEL', "gemini-1.5-pro")
MODEL_NAME = raw_model.replace("models/", "")
API_KEY = config.GEMINI_API_KEY
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

# ... (analyze_single_ticker stays the same) ...
						

						

def analyze_single_ticker(candidate, risk_factor="Neutral", prev_context=None):
	   
																	  
	   
    ticker = candidate.get('ticker')
    log_debug(f"🤖 [SENIOR AGENT] Analyzing Single Ticker: {ticker}...")


    # --- 🙈 THE BLIND TEST FILTER ---
    # Create a copy so we don't delete data needed by the Python code later
    clean_candidate = candidate.copy()
    
    # List of fields to HIDE from the Senior Manager to prevent Bias
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
        "Swing_Action"
        ##"days_held",
        ##"avg_entry_price"
          
    ]
    
    for field in bias_fields:
        clean_candidate.pop(field, None)
    
    candidate_str = json.dumps(clean_candidate, indent=2)
    
    try:
        prompt = prompts.SENIOR_MANAGER_PROMPT.format(
            risk_factor=risk_factor,
										 
            ticker=ticker,
            candidate_data=candidate_str 
        )
        
        # --- 📝 DEBUG: Write Senior Prompt ---
        if getattr(config, 'DEBUG_MODE', False):
            try:
                with open("senior_prompt_debug.txt", "w", encoding="utf-8") as f:
                    f.write(f"--- DEBUG FOR {ticker} ---\n")
                    f.write(prompt)
            except Exception as e:
                log_debug(f"⚠️ Failed to write prompt debug: {e}")

    except Exception as e:
        log_debug(f"❌ PROMPT FORMAT ERROR: {e}")
        return None
    
    for attempt in range(3):
        try:
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "tools": [{"googleSearch": {}}],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": 0.0,  # 🔒 FORCES DETERMINISTIC LOGIC
                    "top_p": 0.1         # 🔒 ELIMINATES RANDOM GUESSING
                }
            }

            response = requests.post(
                BASE_URL + f"?key={API_KEY}",
                headers={'Content-Type': 'application/json'},
                json=payload
            )
            
            if response.status_code == 200:
                raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
                
                # --- 📝 DEBUG: Write Senior Response ---
                if getattr(config, 'DEBUG_MODE', False):
                    try:
                        with open("senior_response_debug.txt", "w", encoding="utf-8") as f:
                            f.write(f"--- RAW RESPONSE FOR {ticker} ---\n")
                            f.write(raw_text)
                    except Exception as e:
                        log_debug(f"⚠️ Failed to write response debug: {e}")

                cleaned = clean_json_text(raw_text)
                return json.loads(cleaned)
            
            elif response.status_code in [429, 503]:
                wait_time = (attempt + 1) * 5
                log_debug(f"⚠️ API Busy ({response.status_code}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
                
            else:
                log_debug(f"❌ API Error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            log_debug(f"⚠️ Attempt {attempt+1}/3 Failed: {e}")
            time.sleep(2)
            
    log_debug(f"❌ Failed to analyze {ticker} after 3 attempts.")
    return None