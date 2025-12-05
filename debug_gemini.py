import sys
import os

print("--- PYTHON ENVIRONMENT DEBUG ---")
print(f"Python Executable: {sys.executable}")

try:
    import google.generativeai as genai
    print(f"GenAI Library Version: {genai.__version__}")
    print(f"GenAI File Location: {genai.__file__}")
    
    print("\n--- INSPECTING TYPES ---")
    # Let's see what tool-related classes actually exist in your library
    import google.generativeai.types as types
    
    attributes = dir(types)
    search_related = [a for a in attributes if "Search" in a]
    tool_related = [a for a in attributes if "Tool" in a]
    
    print(f"Available 'Search' attributes: {search_related}")
    print(f"Available 'Tool' attributes:   {tool_related}")

    print("\n--- ATTEMPTING DIRECT IMPORT ---")
    try:
        from google.generativeai.types import GoogleSearch
        print("✅ SUCCESS: 'GoogleSearch' class was imported successfully.")
    except ImportError:
        print("❌ FAILURE: Could not import 'GoogleSearch'.")
    except AttributeError:
        print("❌ FAILURE: 'types' module has no attribute 'GoogleSearch'.")

except ImportError:
    print("CRITICAL: google-generativeai is not installed in this environment.")
except Exception as e:
    print(f"UNKNOWN ERROR: {e}")

print("\n--------------------------------")