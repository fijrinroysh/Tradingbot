import sys
import os
import json

# Ensure lib modules can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.gvqm_senior_agent import _call_gemini_api

def run_gemini_live_test():
    """
    Live Integration Test for the Gemini API.
    Sends a highly constrained, deterministic prompt to Gemini to ensure
    the API is responsive, authentication is working, and our JSON stripping
    logic successfully parses the response.
    """
    print("🚀 Starting Gemini API Live Integration Test...")

    # A deterministic test prompt forcing Gemini to return a specific JSON structure
    test_prompt = """
    You are an automated test system. 
    Please return a JSON object with a single key "status" and the value "INTEGRATION_SUCCESS".
    Do not include any other text, markdown, or explanation. Just the JSON.
    """
    
    print("📝 Sending deterministic test prompt to Gemini...")
    
    try:
        # We use a dummy context label for logging purposes
        response = _call_gemini_api(test_prompt, context_label="Live_Test_Ping")
        
        if response:
            print(f"📥 Received parsed response from Gemini: {json.dumps(response)}")
            
            # Verify the content
            if response.get("status") == "INTEGRATION_SUCCESS":
                print("✅ VERIFIED! Gemini is active, authentication is valid, and JSON parsing is working flawlessly.")
            else:
                print(f"❌ Gemini responded, but the JSON structure was unexpected. Expected 'status': 'INTEGRATION_SUCCESS'. Got: {response}")
        else:
            print("❌ Gemini failed to return a valid response. Check API keys or rate limits.")
            
    except Exception as e:
        print(f"❌ Critical failure during Gemini API call: {e}")

if __name__ == "__main__":
    run_gemini_live_test()
