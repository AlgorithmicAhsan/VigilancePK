import email.utils
import feedparser
import html
import re
import socket
from datetime import datetime, timezone

# Seconds to wait on a single feed before giving up. feedparser has no timeout
# argument, so we bound it at the socket layer - without this one unresponsive
# host hangs the whole sync indefinitely.
FEED_TIMEOUT_SECONDS = 20

# Some publishers reject requests without a recognisable agent string.
USER_AGENT = "Vigilance-PK/1.0 (+human rights monitoring; RSS reader)"

TAG_PATTERN = re.compile(r"<[^>]+>")
SPACE_PATTERN = re.compile(r"\s+")


def clean_text(value) -> str:
    """Plain text from an RSS field (ADR-020).

    Summaries arrive as HTML. Left in, the tags were embedded, classified and
    shown as noise. Tags go first, then entities are decoded, so an encoded
    "&lt;script&gt;" ends up as harmless literal text, never as markup.
    """
    text = TAG_PATTERN.sub(" ", str(value or ""))
    return SPACE_PATTERN.sub(" ", html.unescape(text)).strip()


def is_urdu(text) -> bool:
    """Arabic-script characters mean Urdu for our feeds (ADR-021)."""
    return any("\u0600" <= ch <= "\u06ff" for ch in text or "")


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

    def fetch_feeds(self):
        """Fetches, parses, and processes all defined RSS feeds."""
        # Reset so a second call on the same instance does not double-count.
        self.data = []
        socket.setdefaulttimeout(FEED_TIMEOUT_SECONDS)

        for name, url in self.sources.items():
            print(f"Fetching from {name}...")
            try:
                feed = feedparser.parse(url, agent=USER_AGENT)
            except Exception as e:
                print(f"WARNING: could not fetch {name}: {e}")
                continue

            if getattr(feed, "bozo", False) and not feed.entries:
                print(f"WARNING: {name} returned no usable entries ({getattr(feed, 'bozo_exception', 'unknown error')}).")
                continue

            for entry in feed.entries:
                # Normalize published date to a timezone-aware ISO string.
                # Mixing aware and naive values here breaks the string sort
                # that /feed relies on, so everything is coerced to UTC.
                raw_date = entry.get("published", "") or entry.get("updated", "")
                published_iso = ""
                if raw_date:
                    try:
                        dt = email.utils.parsedate_to_datetime(raw_date)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        published_iso = dt.astimezone(timezone.utc).isoformat()
                    except (TypeError, ValueError) as e:
                        # Leave it empty rather than substituting "now": a
                        # fabricated timestamp sorts undated items to the top
                        # of the feed as if they were breaking news.
                        print(f"DEBUG: unparseable date from {name}: {raw_date!r} ({e})")

                # Try to extract image URL
                image_url = ""
                if hasattr(entry, 'media_content') and entry.media_content:
                    image_url = entry.media_content[0].get('url', '')
                elif hasattr(entry, 'links'):
                    for link in entry.links:
                        if 'image' in link.get('type', ''):
                            image_url = link.get('href', '')
                            break

                title = clean_text(entry.get("title", ""))
                summary = clean_text(entry.get("summary", ""))
                self.data.append({
                    "source": name,
                    "title": title,
                    "link": entry.get("link", ""),
                    "published": published_iso,
                    "summary": summary,
                    "image": image_url,
                    "language": "urdu" if is_urdu(title) or is_urdu(summary) else "english",
                    "fetched_at": datetime.now(timezone.utc).isoformat()
                })
        
        print(f"Total articles fetched: {len(self.data)}")

    # Whole-word matching only. Plain substring matching silently discarded
    # real reports: "score" hit "Scores of protesters killed", "match" hit
    # "matched", and so on - exactly the headlines this project exists to catch.
    EXCLUDE_KEYWORDS = [
        "cricket", "match", "score", "wicket", "t20", "odi",
        "entertainment", "film", "cinema", "showbiz", "drama", "actor",
        "weather", "earthquake", "magnitude"
    ]
    EXCLUDE_PATTERN = re.compile(
        r"\b(" + "|".join(re.escape(w) for w in EXCLUDE_KEYWORDS) + r")\b",
        re.IGNORECASE,
    )

    def filter_articles(self):
        """Pivoting to Keyword exclusion for Ingestion Phase."""
        # Note: These are English. For now, we keep all Urdu articles
        # as they require Urdu keywords or LLM classification (Phase 3).
        self.filtered_data = []

        for article in self.data:
            # If it's Urdu, we keep it for now
            if article.get('language') == 'urdu':
                self.filtered_data.append(article)
                continue
                
            # If it's English, apply the filter
            text = f"{article['title']} {article['summary']}"
            if not self.EXCLUDE_PATTERN.search(text):
                self.filtered_data.append(article)
        
        print(f"Milestone reached: Kept {len(self.filtered_data)} articles for the next phase.")

    def scrape_all(self):
        """One-call method to fetch, filter and return news."""
        self.fetch_feeds()
        self.filter_articles()
        return self.filtered_data
