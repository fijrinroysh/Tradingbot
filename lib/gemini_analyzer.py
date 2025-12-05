import google.generativeai as genai
import os
import time
import json
import sys
import config # Import the config file

# Handle API Key
if hasattr(config, 'GEMINI_API_KEY') and config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)
    
    # --- USE CONFIG MODEL NAME ---
    MODEL_NAME = getattr(config, 'GEMINI_MODEL_NAME', "models/gemini-2.0-flash")
    print(f"Gemini Analyzer: Using model '{MODEL_NAME}'")
    model = genai.GenerativeModel(MODEL_NAME)
    # -----------------------------
else:
    print("WARNING: GEMINI_API_KEY not found.")
    model = None

# Load Limits from Config
RPM_LIMIT = getattr(config, 'GEMINI_RPM_LIMIT', 2)
DAILY_LIMIT = getattr(config, 'GEMINI_DAILY_LIMIT', 50)
BATCH_TOKEN_LIMIT = getattr(config, 'GEMINI_MAX_BATCH_TOKENS', 30000)

def estimate_tokens(text):
    return len(text) / 4

def create_dynamic_batches(text_list, max_tokens_per_batch):
    """Packs articles into batches based on token limit."""
    batches = []
    current_batch = []
    current_tokens = 0
    PROMPT_OVERHEAD = 500 

    for text in text_list:
        text_tokens = estimate_tokens(text)
        
        if current_tokens + text_tokens + PROMPT_OVERHEAD > max_tokens_per_batch:
            if current_batch:
                batches.append(current_batch)
            current_batch = [text]
            current_tokens = text_tokens
        else:
            current_batch.append(text)
            current_tokens += text_tokens
            
    if current_batch:
        batches.append(current_batch)
    return batches

def analyze_text_gemini(text_list):
    if not model:
        return [0.0] * len(text_list)
    if not text_list:
        return []

    # 1. PRE-FLIGHT CHECK
    batches = create_dynamic_batches(text_list, BATCH_TOKEN_LIMIT)
    total_requests = len(batches)
    
    seconds_per_request = 60.0 / (RPM_LIMIT * 0.9) 
    estimated_time_min = (total_requests * seconds_per_request) / 60.0
    
    print(f"\n--- GEMINI ({MODEL_NAME}) PRE-FLIGHT CHECK ---")
    print(f"Total Articles:   {len(text_list)}")
    print(f"Planned Batches:  {total_requests} requests")
    print(f"Daily Limit:      {DAILY_LIMIT} requests")
    print(f"Estimated Time:   {estimated_time_min:.2f} minutes")
    
    if total_requests > DAILY_LIMIT:
        print(f"[CRITICAL] Job requires {total_requests} requests. Limit is {DAILY_LIMIT}.")
        raise ValueError("Gemini Daily Limit Exceeded")
    
    # 2. EXECUTE
    all_scores = []
    
    for i, batch in enumerate(batches):
        start_time = time.time()
        
        prompt = f"""
        Analyze the sentiment of these {len(batch)} news summaries.
        Return a JSON array of scores from -1.0 (Negative) to 1.0 (Positive).
        0.0 is Neutral.
        
        SUMMARIES:
        {json.dumps(batch)}
        """
        
        retry_count = 0
        max_retries = 3
        success = False
        
        while retry_count < max_retries:
            try:
                response = model.generate_content(
                    prompt, 
                    generation_config={"response_mime_type": "application/json"}
                )
                try:
                    clean = response.text.strip().replace("```json", "").replace("```", "")
                    batch_scores = json.loads(clean)
                except:
                    batch_scores = json.loads(response.text.strip())

                if isinstance(batch_scores, list):
                    if len(batch_scores) != len(batch):
                         # Simple fix for mismatches: Pad/Trim
                         if len(batch_scores) < len(batch):
                             batch_scores += [0.0] * (len(batch) - len(batch_scores))
                         else:
                             batch_scores = batch_scores[:len(batch)]
                    
                    all_scores.extend(batch_scores)
                    success = True
                    break 
                else:
                    raise ValueError("Output not a list")

            except Exception as e:
                if "429" in str(e) or "Quota" in str(e):
                    print(f"⚠️ Rate Limit (Batch {i+1}). Waiting 60s...")
                    time.sleep(60)
                    retry_count += 1
                else:
                    print(f"Error Batch {i+1}: {e}")
                    all_scores.extend([0.0] * len(batch))
                    success = True
                    break
        
        if not success:
            all_scores.extend([0.0] * len(batch))

        elapsed = time.time() - start_time
        sleep_needed = seconds_per_request - elapsed
        if sleep_needed > 0:
            time.sleep(sleep_needed)
            
        if (i+1) % 1 == 0:
            print(f"Progress: {i+1}/{total_requests} batches...")

    return all_scores