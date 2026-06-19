"""
Real-time News & Sentiment Analyzer for Indian Financial Markets.
Pulls RSS feeds, computes sentiment using VADER, and translates to Telugu.
Runs in a background thread so it NEVER blocks the API server.
"""

import time
import logging
import threading
from typing import Dict

logger = logging.getLogger(__name__)

# Cache settings
CACHE_DURATION = 300  # 5 minutes
_last_fetch_time = 0
_cached_sentiment_data: Dict = {"score": 0.0, "label": "Loading...", "top_headlines": []}
_fetch_lock = threading.Lock()
_fetch_thread = None

# Indian Market RSS Feeds
RSS_FEEDS = [
    "https://economictimes.indiatimes.com/markets/rssfeeds/2146842.cms",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://www.livemint.com/rss/markets"
]

class SentimentAnalyzer:
    def __init__(self):
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        from deep_translator import GoogleTranslator
        self.analyzer = SentimentIntensityAnalyzer()
        self.translator = GoogleTranslator(source='en', target='te')

    def fetch_and_analyze(self) -> Dict:
        """Fetch RSS feeds, calculate compound sentiment, and translate top headlines."""
        import feedparser
        all_entries = []

        # Fetch feeds with timeout
        for url in RSS_FEEDS:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:  # Top 10 from each source
                    if hasattr(entry, 'title'):
                        # Filter out old news (older than 72 hours)
                        published_time = entry.get('published_parsed')
                        if published_time:
                            import calendar
                            import time
                            pub_timestamp = calendar.timegm(published_time)
                            now_timestamp = time.time()
                            if now_timestamp - pub_timestamp > 86400: # 24 hours in seconds
                                continue
                        else:
                            continue # Skip if no date
                            
                        all_entries.append({
                            "title_en": entry.title,
                            "published": entry.get('published', ''),
                            "link": entry.get('link', '')
                        })
            except Exception as e:
                logger.error(f"Error fetching RSS feed {url}: {e}")

        if not all_entries:
            return {"score": 0.0, "label": "Neutral", "top_headlines": []}

        # Calculate Sentiment
        total_score = 0.0
        analyzed_headlines = []

        for item in all_entries:
            score = self.analyzer.polarity_scores(item["title_en"])["compound"]
            total_score += score
            item["sentiment"] = score
            analyzed_headlines.append(item)

        # Average compound score
        avg_score = total_score / len(analyzed_headlines) if analyzed_headlines else 0.0

        # Determine Label
        if avg_score > 0.5:
            label = "Highly Bullish"
        elif avg_score > 0.1:
            label = "Bullish"
        elif avg_score < -0.8:
            label = "Panic / Crash Mode"
        elif avg_score < -0.5:
            label = "Highly Bearish"
        elif avg_score < -0.1:
            label = "Bearish"
        else:
            label = "Neutral"

        # Sort by absolute sentiment impact
        analyzed_headlines.sort(key=lambda x: abs(x["sentiment"]), reverse=True)
        top_headlines = analyzed_headlines[:5]

        # Translate Top 5 to Telugu
        for item in top_headlines:
            try:
                item["title_te"] = self.translator.translate(item["title_en"])
            except Exception as e:
                logger.warning(f"Translation failed for '{item['title_en']}': {e}")
                item["title_te"] = item["title_en"]  # Fallback

        return {
            "score": round(avg_score, 2),
            "label": label,
            "top_headlines": top_headlines
        }


def _background_fetch():
    """Runs in a daemon thread: fetches sentiment and updates the cache."""
    global _last_fetch_time, _cached_sentiment_data
    logger.info("[Sentiment] Background fetch thread started.")
    while True:
        try:
            logger.info("[Sentiment] Fetching fresh Market News and Sentiment...")
            analyzer = SentimentAnalyzer()
            result = analyzer.fetch_and_analyze()
            with _fetch_lock:
                _cached_sentiment_data = result
                _last_fetch_time = time.time()
            logger.info(f"[Sentiment] Cache updated: {result['label']} ({result['score']})")
        except Exception as e:
            logger.error(f"[Sentiment] Background fetch failed: {e}")
        # Sleep for CACHE_DURATION before next refresh
        time.sleep(CACHE_DURATION)


def _ensure_background_thread():
    """Starts the background fetch thread once, at first call."""
    global _fetch_thread
    if _fetch_thread is None or not _fetch_thread.is_alive():
        _fetch_thread = threading.Thread(target=_background_fetch, daemon=True, name="SentimentFetcher")
        _fetch_thread.start()
        logger.info("[Sentiment] Daemon fetch thread launched.")


def get_current_sentiment() -> Dict:
    """Returns cached sentiment immediately. Triggers background refresh if needed."""
    _ensure_background_thread()

    current_time = time.time()
    with _fetch_lock:
        age = current_time - _last_fetch_time
        data = dict(_cached_sentiment_data)  # return a copy

    # If cache is stale and thread somehow stopped, re-launch
    if age > CACHE_DURATION + 10:
        _ensure_background_thread()

    return data
