import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import config
from datetime import datetime, timedelta
import finnhub
import time

# Import the "brain" from its file
from lib.sentiment_analyzer import analyze_vader

# --- Live NewsAPI Pipeline (RENAMED) ---
def get_summary_score_newsapi(ticker):
    """
    Fetches LIVE news from NewsAPI, analyzes with VADER,
    and returns a single summary score.
    """
    print(f"Sentiment Analyzer (NewsAPI): Fetching news for {ticker}...")
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
            print("Sentiment Analyzer (NewsAPI): No articles found.")
            return 0.0

        all_scores = []
        for article in articles:
            text = f"{article.get('title', '')}. {article.get('description', '')}"
            score = analyze_vader(text)
            all_scores.append(score)

        if all_scores:
            return sum(all_scores) / len(all_scores)
        else:
            print("Sentiment Analyzer (NewsAPI): No usable article text found.")
            return 0.0

    except Exception as e:
        print(f"Sentiment Analyzer (NewsAPI): Error fetching/analyzing news: {e}")
        return 0.0

# --- Live Finnhub 24h Pipeline (RENAMED) ---
def get_24h_summary_score_finnhub(ticker):
    """
    Fetches all news from the LAST 24 HOURS from Finnhub,
    analyzes it with VADER, and returns a single summary score.
    """
    print(f"Sentiment Analyzer (Finnhub 24h): Fetching news for {ticker}...")
    try:
        finnhub_client = finnhub.Client(api_key=config.FINNHUB_KEY)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=1)
        
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        print(f"Data Loader (Finnhub): Fetching news from {start_str} to {end_str}...")
        news_list = finnhub_client.company_news(ticker, _from=start_str, to=end_str)
        print(f"Data Loader (Finnhub 24h): Fetched {len(news_list)} articles.")
        if not news_list:
            print("Sentiment Analyzer (Finnhub 24h): No articles found.")
            return 0.0

        all_scores = []
        for article in news_list:
            text = f"{article.get('headline', '')}. {article.get('summary', '')}"
            score = analyze_vader(text)
            all_scores.append(score)

        if all_scores:
            return sum(all_scores) / len(all_scores)
        else:
            return 0.0

    except Exception as e:
        print(f"Sentiment Analyzer (Finnhub 24h): Error fetching/analyzing news: {e}")
        return 0.0