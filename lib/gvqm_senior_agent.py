import requests

import json

import config

import time

import re

import datetime
from lib.gvqm_league_common import get_eastern_time_str

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

    timestamp = get_eastern_time_str("%Y-%m-%d %H:%M:%S")

    print(f"[{timestamp}] [SENIOR_AGENT] {message}")



def _extract_and_format_citations(grounding_metadata):
    """
    Extracts search queries and deduplicated citation sources from Gemini groundingMetadata.
    Returns:
        tuple: (queries, citations) where citations is a list of dicts with 'title' and 'uri'.
    """
    if not grounding_metadata:
        return [], []
    
    queries = grounding_metadata.get('webSearchQueries', [])
    chunks = grounding_metadata.get('groundingChunks', [])
    
    citations = []
    seen_uris = set()
    for chunk in chunks:
        web = chunk.get('web', {})
        uri = web.get('uri')
        title = (web.get('title') or '').strip() or 'Web Source'
        if uri and uri not in seen_uris:
            seen_uris.add(uri)
            citations.append({'title': title, 'uri': uri})
            
    return queries, citations

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

    

    gen_config = {}

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

                timeout=90

            )

            

            if response.status_code == 200:

                data = response.json()

                if 'candidates' not in data or not data['candidates']:

                    log_debug(f"⚠️ API returned 200 but omitted candidates: {list(data.keys())}. Retrying ({attempt+1}/{max_retries})...")

                    time.sleep(3)

                    continue



                candidate = data['candidates'][0]
                gm = candidate.get('groundingMetadata', {})
                queries, citations = _extract_and_format_citations(gm)
                if queries:
                    log_debug(f"🌐 Google Search Grounding verified ({len(queries)} queries):")
                    log_debug(f"   🔍 Queries: {queries[:3]}")
                    if citations:
                        sources_summary = " | ".join(f"[{i+1}] {c['title']}" for i, c in enumerate(citations[:5]))
                        if len(citations) > 5:
                            sources_summary += f" (+{len(citations)-5} more)"
                        log_debug(f"   📚 Sources ({len(citations)}): {sources_summary}")

                raw_text = candidate['content']['parts'][0]['text']
                
                # --- 📝 DEBUG: Save Response to File ---
                if getattr(config, 'DEBUG_MODE', False):
                    try:
                        debug_header = []
                        if queries:
                            debug_header.append("🔍 SEARCH QUERIES:")
                            for q in queries:
                                debug_header.append(f"  • {q}")
                        if citations:
                            debug_header.append(f"\n📚 CITATIONS ({len(citations)} sources):")
                            for i, c in enumerate(citations):
                                debug_header.append(f"  [{i+1}] {c['title']}\n      URL: {c['uri']}")
                        debug_section = "\n".join(debug_header) + "\n" + ("-"*50) + "\n" if debug_header else ""

                        with open("senior_response_debug.txt", "a", encoding="utf-8") as f:
                            f.write(f"\n{'='*50}\n👨‍💼 [SENIOR] RESPONSE FOR: {context_label}\n{'-'*50}\n{debug_section}{raw_text}\n{'='*50}\n")
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

def _format_price(price):

    if price is not None and isinstance(price, (int, float)) and price > 0:

        return f"${price:.2f}"

    return "N/A"



def evaluate_matchup(candidate_a, candidate_b, risk_factor="Neutral", prev_context=None):

    """

    The 'Scout' Prompt. Evaluates two elite stocks to adjust the All-Time Elo.

    """

    ticker_a = candidate_a.get('ticker', candidate_a.get('Ticker', 'UNKNOWN'))

    price_a_val = candidate_a.get('current_price', candidate_a.get('price', candidate_a.get('Price')))

    price_a_str = _format_price(price_a_val)

    

    ticker_b = candidate_b.get('ticker', candidate_b.get('Ticker', 'UNKNOWN'))

    price_b_val = candidate_b.get('current_price', candidate_b.get('price', candidate_b.get('Price')))

    price_b_str = _format_price(price_b_val)

    

    log_debug(f"🤖 Analyzing Major League Matchup: {ticker_a} ({price_a_str}) vs {ticker_b} ({price_b_str})...")



    prompt = prompts.SENIOR_MATCHUP_PROMPT.format(

        ticker_a=ticker_a, 

        price_a=price_a_str,

        ticker_b=ticker_b,

        price_b=price_b_str

    )

    

    return _call_gemini_api(prompt, context_label=f"{ticker_a}_vs_{ticker_b}")





# ==========================================

# 📝 PHASE 3: THE BATCH PAPERWORK

# ==========================================

def generate_batch_execution_paperwork(portfolio_dict):

    """ 

    The 'Batch Paperwork' Prompt. 

    Accepts a dictionary of { "TICKER": current_price, "TICKER2": current_price }

    Returns a dictionary of execution paperwork objects.

    """

    from lib.gvqm_senior_paperwork_prompt import SENIOR_PAPERWORK_PROMPT



    # Convert the Python dictionary into a clean JSON string for the prompt

    portfolio_json_str = json.dumps(portfolio_dict, indent=2)

    prompt = SENIOR_PAPERWORK_PROMPT.format(portfolio_json=portfolio_json_str)



    log_debug(f"📝 Submitting Batch Paperwork Request for: {list(portfolio_dict.keys())}...")

    

    # We expect a dictionary back where keys are the tickers

    response_data = _call_gemini_api(prompt, "Batch_Paperwork")



    if not response_data:

        return {}



    # Safety Check: Did the AI return a list instead of a dict by mistake?

    if isinstance(response_data, list):

        log_debug("⚠️ AI returned a list instead of a dictionary. Attempting to parse...")

        fixed_dict = {}

        for item in response_data:

            # Try to find the ticker name inside the list item if it exists

            if isinstance(item, dict) and 'ticker' in item:

                fixed_dict[item['ticker']] = item

        return fixed_dict

        

    log_debug(f"✅ Successfully parsed batch paperwork for {len(response_data)} stocks.")

    return response_data