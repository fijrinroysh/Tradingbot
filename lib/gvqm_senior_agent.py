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
    v4.1: Updated to handle 'HIDDEN' strings safely.
    """
    # Get Risk Context for Header
    risk_factor = getattr(config, 'RISK_FACTOR', 1.0)
    mode = "NEUTRAL"
    if risk_factor > 1.0: mode = "AGGRESSIVE"
    elif risk_factor < 1.0: mode = "CONSERVATIVE"

    print("\n" + "="*82)
    print(f"🔮 SENIOR MANAGER: NEURAL DECISION MATRIX | RISK: {risk_factor} ({mode})")
    print("="*82)

    orders_map = {o.get('ticker'): o for o in decision.get('final_execution_orders', [])}

    for cand in candidates:
        ticker = cand.get('ticker')
        order = orders_map.get(ticker)
        
        if not order: continue

        # --- PREPARE DATA ---
        price = cand.get('current_price', 0)
        held = cand.get('shares_held', 0)
												   
        
        # Handle HIDDEN Entry Price safely
        raw_entry = cand.get('avg_entry_price', 0)
        if isinstance(raw_entry, (int, float)):
            entry_str = f"${raw_entry:.2f}"
        else:
            entry_str = str(raw_entry) # "HIDDEN"

        curr_tp = cand.get('current_active_tp', '-') or '-'
        curr_sl = cand.get('current_active_sl', '-') or '-'
        
        pending_buy = cand.get('pending_buy_limit')
        if pending_buy and pending_buy != "MKT" and str(pending_buy).replace('.','',1).isdigit() and float(pending_buy) > 0:
            pending_str = f"PENDING BUY @ ${float(pending_buy):.2f}"
        elif pending_buy == "MKT":
             pending_str = "PENDING BUY @ MKT"
        else:
            pending_str = "No Pending Orders"

        # --- RANK DATA ---
										   
        rank = order.get('rank', 'N/A') 
        prev_rank = order.get('previous_rank', 'N/A')
		
        action = order.get('action', 'HOLD')
        
        # --- PILLARS ---
        why_safe = order.get('justification_safe', 'N/A')
        why_bargain = order.get('justification_bargain', 'N/A')
        why_rebound = order.get('justification_rebound', 'N/A')
        
        params = order.get('confirmed_params', {})
        new_limit = params.get('buy_limit', '-')
        new_tp = params.get('take_profit', '-')
        new_sl = params.get('stop_loss', '-')

        color = "\033[90m" # Grey (Hold)
        if action == "OPEN_NEW": color = "\033[92m" # Green
        elif action == "UPDATE_EXISTING": color = "\033[96m" # Cyan
        reset = "\033[0m"

        # --- DRAW TABLE ---
        print(f"{color}" + "-"*82)
										  
        print(f" {ticker:<6} | {action:<15} | RANK: {rank}")
        print("-" * 82 + f"{reset}")
        
        print(f" {'INPUT (Context)':<38} | {'OUTPUT (Decision)':<38}")
        print(f" {'-'*38} | {'-'*38}")
        
        # Row 1: Price
        r1_left = f"Price:    ${price}"
        r1_right = f"Limit:    ${new_limit}"
        print(f" {r1_left:<38} | {r1_right:<38}")
        
        # Row 2: Held
        if held > 0:
            r2_left = f"Held:     {held} @ {entry_str}"
        else:
            r2_left = f"Held:     0 shares"
            
        r2_right = f"Targets:  TP: ${new_tp} / SL: ${new_sl}"
        print(f" {r2_left:<38} | {r2_right:<38}")

        # Row 3: Active Bracket
        r3_left = f"Active:   TP: ${curr_tp} / SL: ${curr_sl}"
        r3_right = f"Prev Rank: {prev_rank}" 
        print(f" {r3_left:<38} | {r3_right:<38}")
        
        # Row 4: Pending
        r4_left = f"Status:   {pending_str}"
        print(f" {r4_left:<38} |")

		
			   
		  
        
        print(f" {'-'*80}")
        print(f" 🛡️ Safe:    {why_safe[:70]}")
        print(f" 💰 Bargain: {why_bargain[:70]}")
        print(f" 📈 Rebound: {why_rebound[:70]}")
        print("")

    print("="*82 + "\n")

def rank_portfolio(candidates_list, top_n=5, risk_factor=1.0, lookback_days=10, prev_context=None):
    log_debug(f"Starting analysis for {len(candidates_list)} candidates using model: {MODEL_NAME}")
    
    if not prev_context: prev_context = {"date": "None", "prev_report": "None"}
    


    try:
																
        prompt = prompts.SENIOR_MANAGER_PROMPT.format(
            count=len(candidates_list),
            max_trades=top_n, 
            risk_factor=risk_factor, 
            lookback=lookback_days,
            prev_date=prev_context.get('date'),	
            prev_report=prev_context.get('prev_report', 'None'),
            candidates_data=json.dumps(candidates_list, indent=2)
        )

        if getattr(config, 'DEBUG_MODE', False):
					   
																						
            print("\n" + "="*60)
            print(f"🧠 [SENIOR] DEBUG: PROMPT GENERATED | Risk: {risk_factor} ")
            print("="*60)					
																				  
						 
            # Save prompt to file
												 
            filename = "senior_prompt_debug.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(prompt)
				
            print(f"📝 Prompt saved to file: {filename}")
					

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
        "safetySettings": safety_settings,
        "generationConfig": {
            "temperature": 1.0,
            #"maxOutputTokens": 15000 
        }
    }
    
    # --- RETRY LOOP ---
	
    #[CORRECTION] Use your existing URL construction
    url = f"{BASE_URL}?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}						
    for attempt in range(3):
        try:
            log_debug(f"Attempt {attempt+1}/3: Sending request to Google AI...")
		 
            
            # Request
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            
			  
						 
   
            if response.status_code == 200:
																   
                try:
                    response_json = response.json()
                    
                    # 1. Safety/Empty Check
                    if not response_json.get('candidates'):
                        log_debug(f"❌ Error: No candidates returned. Raw: {response.text}")
                        return None
                    
                    first_candidate = response_json['candidates'][0]
                    finish_reason = first_candidate.get('finishReason', 'UNKNOWN')

                    # 2. Check for Content Blocking (The Zombie Check)
                    # If 'content' is missing OR 'parts' is missing, it's a block.
                    if 'content' not in first_candidate:
																					  
                        log_debug(f"❌ Error: Content BLOCKED. Finish Reason: {finish_reason}")
                        return None
                        
										
                    parts = first_candidate['content'].get('parts', [])
                    if not parts:
                         log_debug(f"❌ Error: Content exists but 'parts' is empty. Finish Reason: {finish_reason}")
                         # Debug: Dump the full candidate to see what went wrong
                         log_debug(f"   ⚠️ Dump: {json.dumps(first_candidate)}")
                         return None
                         
                    text = parts[0].get('text', "")

                    # [NEW] WRITE RAW RESPONSE TO FILE FOR DEBUGGING
                    if getattr(config, 'DEBUG_MODE', False):
                        debug_filename = "senior_response_debug.txt"
                        with open(debug_filename, "w", encoding="utf-8") as f:
                            f.write(text)
                        print(f"📝 Raw AI Response saved to: {debug_filename}")

                    cleaned_json = clean_json_text(text)
                    decision_data = json.loads(cleaned_json)

                    visualize_decision(candidates_list, decision_data)

                    return decision_data

                except Exception as e:
                    log_debug(f"❌ Senior Parsing Error: {e}")
																  
                    if getattr(config, 'DEBUG_MODE', False):
                        with open("senior_response_ERROR_debug.txt", "w", encoding="utf-8") as f:
                            f.write(response.text) 
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
        
def analyze_single_ticker(candidate, risk_factor="Neutral", prev_context=None):
    """
    Analyzes ONE stock in isolation.
    Returns a partial decision object (list of 1 order).
    """
    ticker = candidate.get('ticker')
    print(f"🤖 [SENIOR AGENT] Analyzing Single Ticker: {ticker}...")
    
    # 1. Format Single Data Block
    # We pass the full candidate dict as a formatted string
    candidate_str = json.dumps(candidate, indent=2)
    
    # 2. Prepare Prompt
    prompt = prompts.SENIOR_MANAGER_PROMPT.format(
        risk_factor=risk_factor,
        candidate_data=candidate_str,
        ticker=ticker
    )
    
    # 3. Call AI
    try:
        response = requests.post(
            BASE_URL + f"?key={API_KEY}",
            headers={'Content-Type': 'application/json'},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }
        )
        
        if response.status_code == 200:
            cleaned = clean_json_text(response.json()['candidates'][0]['content']['parts'][0]['text'])
            return json.loads(cleaned)
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Exception analyzing {ticker}: {e}")
        return None