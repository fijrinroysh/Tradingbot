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
        if start != -1 and end != -1: return text[start : end+1]
        return text
    except: return text

# --- VISUALIZATION ENGINE ---                                                                            
def visualize_decision(candidates, decision):
    """
    Prints a human-readable 'Reality vs Decision' matrix.
    v3.0: Now includes 3-Pillar Justifications.
    """
    print("\n" + "="*82)
    print("🔮 SENIOR MANAGER: NEURAL DECISION MATRIX")
    print("="*82)

    orders_map = {o.get('ticker'): o for o in decision.get('final_execution_orders', [])}

    for cand in candidates:
        ticker = cand.get('ticker')
        order = orders_map.get(ticker)
        
        if not order: continue

        # --- PREPARE DATA ---
        price = cand.get('current_price', 0)
        held = cand.get('shares_held', 0)
        avg_entry = cand.get('avg_entry_price', 0) 
        
        curr_tp = cand.get('current_active_tp', '-') or '-'
        curr_sl = cand.get('current_active_sl', '-') or '-'
        
        pending_buy = cand.get('pending_buy_limit')
        if pending_buy and pending_buy != "MKT" and float(pending_buy) > 0:
            pending_str = f"PENDING BUY @ ${pending_buy}"
        elif pending_buy == "MKT":
             pending_str = "PENDING BUY @ MKT"
        else:
            pending_str = "No Pending Orders"

        score = cand.get('conviction_score', 'N/A')
        status_tag = cand.get('status', 'N/A')

        action = order.get('action', 'HOLD')
        
        # --- NEW PILLARS ---
        why_safe = order.get('justification_safe', 'N/A')
        why_bargain = order.get('justification_bargain', 'N/A')
        why_rebound = order.get('justification_rebound', 'N/A')
        
        params = order.get('confirmed_params', {})
        new_limit = params.get('buy_limit', '-')
        new_tp = params.get('take_profit', '-')
        new_sl = params.get('stop_loss', '-')

        color = "\033[90m" 
        if action == "OPEN_NEW": color = "\033[92m" 
        elif action == "UPDATE_EXISTING": color = "\033[96m" 
        reset = "\033[0m"

        # --- DRAW TABLE ---
        print(f"{color}" + "-"*82)
        print(f" {ticker:<6} | {action}")
        print("-" * 82 + f"{reset}")
        
        print(f" {'INPUT (Context)':<38} | {'OUTPUT (Decision)':<38}")
        print(f" {'-'*38} | {'-'*38}")
        
        # Row 1: Price
        r1_left = f"Price:    ${price}"
        r1_right = f"Limit:    ${new_limit}"
        print(f" {r1_left:<38} | {r1_right:<38}")
        
        # Row 2: Held
        if held > 0:
            r2_left = f"Held:     {held} @ ${avg_entry:.2f}"
        else:
            r2_left = f"Held:     0 shares"
            
        r2_right = f"Targets:  TP: ${new_tp} / SL: ${new_sl}"
        print(f" {r2_left:<38} | {r2_right:<38}")

        # Row 3: Active Bracket
        r3_left = f"Active:   TP: ${curr_tp} / SL: ${curr_sl}"
        r3_right = "" 
        print(f" {r3_left:<38} | {r3_right:<38}")
        
        # Row 4: Pending
        r4_left = f"Status:   {pending_str}"
        print(f" {r4_left:<38} |")

        # Row 5: Junior
        r5_left = f"Junior:   {status_tag} (Score: {score})"
        print(f" {r5_left:<38} |")
        
        print(f" {'-'*80}")
        print(f" 🛡️ Safe:    {why_safe[:70]}")
        print(f" 💰 Bargain: {why_bargain[:70]}")
        print(f" 📈 Rebound: {why_rebound[:70]}")
        print("")

    print("="*82 + "\n")

def rank_portfolio(candidates_list, top_n=5, lookback_days=10, prev_context=None):
    log_debug(f"Starting analysis for {len(candidates_list)} candidates using model: {MODEL_NAME}")
    
    if not prev_context: prev_context = {"date": "None", "top_tickers": "None"}
    
    try:
        prompt = prompts.SENIOR_MANAGER_PROMPT.format(
            count=len(candidates_list),
            max_trades=top_n,
            lookback=lookback_days,
            prev_date=prev_context.get('date'),
            #prev_picks=prev_context.get('top_tickers'),
            prev_report=prev_context.get('ceo_report', 'None'),
            candidates_data=json.dumps(candidates_list, indent=2)
        )

        # ==============================================================================
        # 🧠 [SENIOR] PROMPT AUDIT LOGGING
        # ==============================================================================
        print("\n" + "="*60)
        print(f"🧠 [SENIOR] DEBUG: FINAL PROMPT TRANSMITTED AT {datetime.datetime.now()}")
        print("="*60)
        print(prompt)
        print("="*60 + "\n")
        # ==============================================================================
    except Exception as e:
        log_debug(f"CRITICAL: Failed to construct prompt. Error: {e}")
        return None

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
    
    # --- RETRY LOOP ---
    for attempt in range(3):
        try:
            log_debug(f"Attempt {attempt+1}/3: Sending request to Google AI...")
            start_time = time.time()
            
            response = requests.post(f"{BASE_URL}?key={API_KEY}", headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
            
            elapsed = round(time.time() - start_time, 2)
            log_debug(f"Response received in {elapsed}s. Status Code: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    text = response.json()['candidates'][0]['content']['parts'][0]['text']
                    cleaned_json = clean_json_text(text)
                    decision_data = json.loads(cleaned_json)

                    visualize_decision(candidates_list, decision_data)

                    # [REMOVED] Redundant sheet logging. 
                    # Handled by routes.py -> senior_history.log_detailed_decisions

                    return decision_data
                except Exception as e:
                    log_debug(f"❌ Senior Parsing Error: {e}")
                    print(f"RAW TEXT: {text[:200]}...") 
                    return None
            elif response.status_code in [429, 503]:
                time.sleep((attempt + 1) * 10)
                continue
            else:
                log_debug(f"❌ Senior API Error ({response.status_code}): {response.text}")
                return None
        except Exception as e:
            log_debug(f"❌ Senior Connection Error: {e}")
            return None
    return None