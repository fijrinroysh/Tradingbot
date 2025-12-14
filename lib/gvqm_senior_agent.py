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

# --- NEW VISUALIZATION ENGINE ---								  
def visualize_decision(candidates, decision):
    """
    Prints a human-readable 'Reality vs Decision' matrix.
    v2.0: Fixed width columns, Pending Buy visibility, Full-width Reason.
    """
    print("\n" + "="*82)
    print("🔮 SENIOR MANAGER: NEURAL DECISION MATRIX")
    print("="*82)

    # Map orders for O(1) lookup
    orders_map = {o.get('ticker'): o for o in decision.get('final_execution_orders', [])}

    for cand in candidates:
        ticker = cand.get('ticker')
        order = orders_map.get(ticker)
        
																		
																				
        if not order: continue

        # --- PREPARE DATA ---
        # Input Side (Reality)
        price = cand.get('current_price', 0)
        held = cand.get('shares_held', 0)
        curr_tp = cand.get('current_active_tp', '-') or '-'
        curr_sl = cand.get('current_active_sl', '-') or '-'
        
        # PENDING BUY LOGIC
        pending_buy = cand.get('pending_buy_limit')
        if pending_buy and pending_buy != "MKT" and float(pending_buy) > 0:
            pending_str = f"PENDING BUY @ ${pending_buy}"
        elif pending_buy == "MKT":
             pending_str = "PENDING BUY @ MKT"
        else:
            pending_str = "No Pending Orders"

        score = cand.get('conviction_score', 'N/A')
        status_tag = cand.get('status', 'N/A')

        # Output Side (Decision)
        action = order.get('action', 'HOLD')
        reason = order.get('reason', 'No reason provided')
        params = order.get('confirmed_params', {})
        new_limit = params.get('buy_limit', '-')
        new_tp = params.get('take_profit', '-')
        new_sl = params.get('stop_loss', '-')

        # Color Coding
													   
        color = "\033[90m" # Grey
        if action == "OPEN_NEW": color = "\033[92m" # Green
        elif action == "UPDATE_EXISTING": color = "\033[96m" # Cyan
        reset = "\033[0m"

        # --- DRAW TABLE (Strict 38-char columns + 3 char separator) ---
        print(f"{color}" + "-"*82)
        print(f" {ticker:<6} | {action}")
        print("-" * 82 + f"{reset}")
        
        # Header
        print(f" {'INPUT (Context)':<38} | {'OUTPUT (Decision)':<38}")
        print(f" {'-'*38} | {'-'*38}")
																			
        
        # Row 1: Price vs Limit
        print(f" Price:    ${str(price):<28} | Limit:    ${str(new_limit)}")
        
        # Row 2: Held vs Targets
        p_str = f"{held} shares"
        # Format targets string carefully
        t_str = f"TP: ${new_tp} / SL: ${new_sl}"
        print(f" Held:     {p_str:<28} | Targets:  {t_str}")

        # Row 3: Active Bracket
															  
        b_str = f"TP: ${curr_tp} / SL: ${curr_sl}"
        print(f" Active:   {b_str:<28} |")
        
        # Row 4: Pending Status (NEW)
        print(f" Status:   {pending_str:<28} |")

        # Row 5: Junior Intel
        j_str = f"{status_tag} (Score: {score})"
        print(f" Junior:   {j_str:<28} |")
        
        # Footer: Reason (Full Width for readability)
        print(f" {'-'*80}")
        print(f" Reason:   {reason}")
        print("")

    print("="*82 + "\n")

def rank_portfolio(candidates_list, top_n=5, lookback_days=10, prev_context=None):
    log_debug(f"Starting analysis for {len(candidates_list)} candidates using model: {MODEL_NAME}")
    
    if not prev_context: prev_context = {"date": "None", "top_tickers": "None"}
    
    # Construct Prompt
    try:
        prompt = prompts.SENIOR_MANAGER_PROMPT.format(
            count=len(candidates_list),
            max_trades=top_n,
            lookback=lookback_days,
            prev_date=prev_context.get('date'),
            prev_picks=prev_context.get('top_tickers'),
            prev_report=prev_context.get('ceo_report', 'None'),
            candidates_data=json.dumps(candidates_list, indent=2)
        )
										   
							
													   
					 
										
							
		
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

                    # --- TRIGGER VISUALIZATION ---
                    visualize_decision(candidates_list, decision_data)
                    # -----------------------------

					
                    return decision_data
                except Exception as e:
                    log_debug(f"❌ Senior Parsing Error: {e}")
                    # Print raw text if parse fails so we can debug
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
