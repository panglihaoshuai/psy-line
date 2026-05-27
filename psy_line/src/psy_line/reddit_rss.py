"""Reddit RSS feed reader.

Uses RSS feeds to get Reddit posts without API authentication.
"""

import feedparser
import re
from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class RedditPost:
    """A Reddit post from RSS feed."""
    id: str
    title: str
    content: str
    subreddit: str
    author: str
    published: datetime
    link: str
    score: int
    num_comments: int


class RedditRSSClient:
    """Client for Reddit RSS feeds."""

    # RSS feed URLs for popular crypto subreddits
    SUBREDDIT_FEEDS = {
        "CryptoCurrency": "https://www.reddit.com/r/CryptoCurrency/.rss",
        "Bitcoin": "https://www.reddit.com/r/Bitcoin/.rss",
        "ethereum": "https://www.reddit.com/r/ethereum/.rss",
        "SatoshiBets": "https://www.reddit.com/r/SatoshiBets/.rss",
        "SOLMarkets": "https://www.reddit.com/r/SOLMarkets/.rss",
        "ethtrader": "https://www.reddit.com/r/ethtrader/.rss",
    }

    def __init__(self):
        self._session = None

    def _get_session(self):
        """Lazy HTTP session."""
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": "PSY_line RSS Reader/1.0"
            })
        return self._session

    def fetch_posts(
        self,
        subreddits: List[str],
        limit: int = 25,
        keywords: Optional[List[str]] = None,
    ) -> List[RedditPost]:
        """
        Fetch posts from Reddit RSS feeds.

        Args:
            subreddits: List of subreddit names to fetch
            limit: Max posts per subreddit
            keywords: Optional keywords to filter (title/content must contain one)

        Returns:
            List of RedditPost objects
        """
        posts = []
        seen_ids = set()

        for subreddit in subreddits:
            feed_url = self.SUBREDDIT_FEEDS.get(subreddit)
            if not feed_url:
                feed_url = f"https://www.reddit.com/r/{subreddit}/.rss"

            try:
                session = self._get_session()
                response = session.get(feed_url, timeout=10)
                response.raise_for_status()

                feed = feedparser.parse(response.content)

                for entry in feed.entries[:limit]:
                    post_id = entry.get("id", "")
                    if post_id in seen_ids:
                        continue

                    title = str(entry.get("title", ""))
                    content_raw = entry.get("summary", "") or entry.get("content", "")
                    content_raw = str(content_raw) if content_raw else ""

                    # Clean HTML from content
                    content = re.sub(r"<[^>]+>", "", content_raw)
                    content = re.sub(r"\s+", " ", content).strip()

                    # Apply keyword filter
                    if keywords:
                        text_lower = (title + " " + content).lower()
                        if not any(kw.lower() in text_lower for kw in keywords):
                            continue

                    # Parse metadata
                    author = "unknown"
                    if hasattr(entry, "author"):
                        author = str(entry.author)

                    published = datetime.now()
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        import time
                        published = datetime.fromtimestamp(time.mktime(entry.published_parsed))  # pyright: ignore[reportArgumentType]

                    score = 0
                    num_comments = 0

                    # Try to extract from link
                    link = str(entry.get("link", ""))

                    # Extract upvotes from reddit_ups if available
                    if hasattr(entry, "reddit_upvotes"):
                        try:
                            score = int(str(entry.reddit_upvotes))  # pyright: ignore[reportArgumentType]
                        except (ValueError, TypeError):
                            pass

                    seen_ids.add(post_id)
                    posts.append(RedditPost(
                        id=str(post_id),  # pyright: ignore[reportArgumentType]
                        title=title[:500],  # Truncate long titles
                        content=content[:1000],
                        subreddit=subreddit,
                        author=author,
                        published=published,
                        link=link,
                        score=score,
                        num_comments=num_comments,
                    ))

            except Exception as e:
                print(f"Error fetching r/{subreddit}: {e}", file=__import__("sys").stderr)
                continue

        return posts

    def fetch_hot_posts(self, subreddits: List[str], limit: int = 25) -> List[RedditPost]:
        """Fetch hot/trending posts (alias for fetch_posts with hot sorting)."""
        # Reddit RSS doesn't support sorting, so this is the same as fetch_posts
        return self.fetch_posts(subreddits, limit=limit)
