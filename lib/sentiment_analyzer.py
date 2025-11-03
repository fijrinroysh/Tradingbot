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


# --- UPDATED FUNCTION ---
def get_summary_score(ticker):
    """
    Fetches LIVE news and returns an aggregated VADER score.
    Now uses the 'analyze_vader' function.
    """
    print(f"Sentiment Analyzer: Fetching news for {ticker}...")
    url = (f"https://newsapi.org/v2/everything?"
           f"q={ticker}&"
           f"sortBy=publishedAt&"
           f"language=en&"
           f"apiKey={config.NEWS_API_KEY}")
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        articles = data.get("articles", [])

        if not articles:
            print("Sentiment Analyzer: No articles found.")
            return 0.0

        all_scores = []
        for article in articles:
            text = f"{article.get('title', '')}. {article.get('description', '')}"
            
            # --- THIS IS THE CHANGE ---
            # Call our new, clean function
            score = analyze_vader(text)
            all_scores.append(score)
            # --- END OF CHANGE ---

        if all_scores:
            summary_score = sum(all_scores) / len(all_scores)
            return summary_score
        else:
            print("Sentiment Analyzer: No usable article text found.")
            return 0.0

    except Exception as e:
        print(f"Sentiment Analyzer: Error fetching/analyzing news: {e}")
        return 0.0