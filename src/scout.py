import feedparser
import json
from datetime import datetime
from tqdm import tqdm
from nlp_engine import UrduProcessor

class NewsScraper:
    def __init__(self):
        # Define our Pakistan-specific sources (English + Urdu)
        self.sources = {
            "Dawn": "https://www.dawn.com/feeds/home",
            "The News": "https://www.thenews.com.pk/rss/1/1",
            "Express Tribune": "https://tribune.com.pk/feed/home",
            "Jang": "https://jang.com.pk/rss/1/1",
            "Express Urdu": "https://www.express.pk/feed/",
            "BBC Urdu": "https://www.bbc.com/urdu/index.xml"
        }
        self.data = []
        self.filtered_data = []
        self.processor = UrduProcessor()

    def fetch_feeds(self):
        """Fetches, parses, and processes all defined RSS feeds."""
        for name, url in self.sources.items():
            print(f"Fetching from {name}...")
            feed = feedparser.parse(url)
            
            for entry in feed.entries:
                article = {
                    "source": name,
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", ""),
                    "fetched_at": datetime.now().isoformat()
                }
                
                # Apply Phase 2: NLP Processing (Detection + Normalization)
                processed_article = self.processor.process_article(article)
                self.data.append(processed_article)
        
        print(f"Total articles fetched: {len(self.data)}")

    def filter_articles(self):
        """Pivoting to Keyword exclusion for Ingestion Phase."""
        # Note: These are English. For now, we keep all Urdu articles 
        # as they require Urdu keywords or LLM classification (Phase 3).
        exclude_keywords = [
            "cricket", "match", "score", "wicket", "t20", "odi", 
            "entertainment", "film", "cinema", "showbiz", "drama", "actor",
            "weather", "earthquake", "magnitude"
        ]
        
        for article in self.data:
            # If it's Urdu, we keep it for now (safe bet for HRCP triage)
            if article.get('language') == 'urdu':
                self.filtered_data.append(article)
                continue
                
            # If it's English, apply the filter
            text = f"{article['title']} {article['summary']}".lower()
            if not any(word in text for word in exclude_keywords):
                self.filtered_data.append(article)
        
        print(f"Milestone reached: Kept {len(self.filtered_data)} articles for the next phase.")

    def save_to_file(self, filename="../data/filtered_news.json"):
        """Saves the filtered and processed data to the data folder."""
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.filtered_data, f, ensure_ascii=False, indent=4)
        print(f"Saved {len(self.filtered_data)} articles to {filename}")

if __name__ == "__main__":
    scraper = NewsScraper()
    scraper.fetch_feeds()
    scraper.filter_articles()
    scraper.save_to_file()
