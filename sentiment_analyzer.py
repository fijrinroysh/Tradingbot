# sentiment_analyzer.py
import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import config  # Import our keys

# Initialize VADER once when the file is imported
analyzer = SentimentIntensityAnalyzer()

def get_summary_score(ticker):
    """
    Fetches news for a ticker and returns a single, aggregated
    VADER compound score.
    """
    print(f"Sentiment Analyzer: Fetching news for {ticker}...")
    url = (f"https://newsapi.org/v2/everything?"
           f"q={ticker}&"
           f"sortBy=publishedAt&"
           f"language=en&"
           f"apiKey={config.NEWS_API_KEY}")  # Use key from config
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        articles = data.get("articles", [])

        if not articles:
            print("Sentiment Analyzer: No articles found.")
            return 0.0  # Return a neutral score

        all_scores = []
        for article in articles:
            # Combine title and description for better accuracy
            text = f"{article.get('title', '')}. {article.get('description', '')}"
            
            if not text.strip(". "):
                continue  # Skip if title/description are empty
                
            score = analyzer.polarity_scores(text)
            all_scores.append(score['compound'])

        if all_scores:
            summary_score = sum(all_scores) / len(all_scores)
            return summary_score
        else:
            print("Sentiment Analyzer: No usable article text found.")
            return 0.0  # Return a neutral score

    except Exception as e:
        print(f"Sentiment Analyzer: Error fetching/analyzing news: {e}")
        return 0.0  # Return neutral on error