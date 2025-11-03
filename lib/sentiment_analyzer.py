import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import config  # Import our keys

# Initialize VADER once when the file is imported
analyzer = SentimentIntensityAnalyzer()


# --- NEW REUSABLE FUNCTION ---
def analyze_vader(text):
    """
    Analyzes a single string with VADER and returns the compound score.
    This function can now be imported by other scripts (like the backtester).
    """
    if not text or not text.strip(". "):
        return 0.0  # Return neutral for empty/invalid text
    
    try:
        score = analyzer.polarity_scores(text)
        return score['compound']
    except Exception as e:
        print(f"VADER Error analyzing text: '{text[:50]}...'. Error: {e}")
        return 0.0 # Return neutral on error
# --- END NEW FUNCTION ---

