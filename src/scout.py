import feedparser
import json
from datetime import datetime
from transformers import pipeline
import torch
from tqdm import tqdm

class NewsScraper:
    def __init__(self):
        # Define our Pakistan-specific sources
        self.sources = {
            "Dawn": "https://www.dawn.com/feeds/home",
            "The News": "https://www.thenews.com.pk/rss/1/1",
            "Express Tribune": "https://tribune.com.pk/feed/home"
        }
        self.data = []
        device = 0 if torch.cuda.is_available() else -1
        self.filtered_data = []
    def fetch_feeds(self):
        """Fetches and parses all defined RSS feeds."""
        for name, url in self.sources.items():
            print(f"Fetching from {name}...")
            feed = feedparser.parse(url)
            
            for entry in feed.entries:
                # We extract the bare minimum for now
                article = {
                    "source": name,
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", ""),
                    "fetched_at": datetime.now().isoformat()
                }
                self.data.append(article)
        
        print(f"Total articles fetched: {len(self.data)}")

    def filter_articles(self):
        """Pivoting to Keyword exclusion for Ingestion Phase."""
        exclude_keywords = [
            "cricket", "match", "score", "wicket", "t20", "odi", 
            "entertainment", "film", "cinema", "showbiz", "drama", "actor",
            "weather", "earthquake", "magnitude" # Optional: remove disasters too
        ]
        
        for article in self.data:
            text = f"{article['title']} {article['summary']}".lower()
            
            # Simple but robust: keep it if it DOESN'T contain an exclusion keyword
            if not any(word in text for word in exclude_keywords):
                self.filtered_data.append(article)
        print(f"Milestone reached: Kept {len(self.filtered_data)} articles for the next phase.")


    def save_to_file(self, filename="filtered_news.json"):
        """Saves only the filtered data."""
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.filtered_data, f, ensure_ascii=False, indent=4)
        print(f"Saved {len(self.filtered_data)} articles to {filename}")

if __name__ == "__main__":
    scraper = NewsScraper()
    scraper.fetch_feeds()
    scraper.filter_articles()
    scraper.save_to_file() # Uncomment this once you verify it works!
