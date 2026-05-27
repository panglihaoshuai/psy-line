"""Reddit scraper module."""

import re
from typing import List, Optional


class RedditScraper:
    """Scraper for Reddit comments."""

    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        # Lazy import praw only when actually needed
        self._reddit = None

    @property
    def reddit(self):
        """Lazy reddit instance."""
        if self._reddit is None:
            import praw
            self._reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
            )
        return self._reddit

    def fetch_comments(
        self,
        subreddits: List[str],
        time_range: str = "24h",
        limit: int = 100,
        keywords: Optional[List[str]] = None,
        keywords_mode: str = "include",
    ) -> List[dict[str, object]]:
        """
        Fetch and deduplicate crypto-related comments from subreddits.

        Args:
            subreddits: List of subreddit names to fetch from
            time_range: Time range for posts ("1h", "24h", "7d")
            limit: Max number of comments to fetch
            keywords: List of keywords to filter by (default: None = no filter)
            keywords_mode: "include" (only comments with keyword) or "exclude" (remove comments with keyword)

        Returns:
            List of comment dicts with: id, body, subreddit, score, created_utc, permalink
        """
        # Mapping of time_range to Reddit's time filter
        time_filters = {"1h": "hour", "24h": "day", "7d": "week"}
        time_filter = time_filters.get(time_range, "day")

        seen_ids = set()
        comments = []

        for subreddit_name in subreddits:
            try:
                subreddit = self.reddit.subreddit(subreddit_name)
                for submission in subreddit.top(time_filter=time_filter, limit=limit // len(subreddits)):
                    # Get top comments from submission
                    submission.comments.replace_more(limit=10)
                    for comment in submission.comments.list()[:20]:
                        if comment.id in seen_ids:
                            continue
                        if comment.author is None:  # Deleted
                            continue
                        body = self._clean_text(comment.body)
                        if not body:
                            continue

                        # Apply keyword filtering
                        if keywords:
                            body_lower = body.lower()
                            has_keyword = any(kw.lower() in body_lower for kw in keywords)
                            if keywords_mode == "include" and not has_keyword:
                                continue
                            if keywords_mode == "exclude" and has_keyword:
                                continue

                        seen_ids.add(comment.id)
                        comments.append({
                            "id": comment.id,
                            "body": body,
                            "subreddit": subreddit_name,
                            "score": comment.score,
                            "created_utc": comment.created_utc,
                            "permalink": f"https://reddit.com{comment.permalink}",
                        })
            except Exception as e:
                # Log error but continue with other subreddits
                print(f"Error fetching r/{subreddit_name}: {e}", file=__import__('sys').stderr)
                continue

        return comments

    def _clean_text(self, text: str) -> str:
        """Clean HTML tags and special characters from text."""
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Remove markdown links but keep text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Keep only Chinese, English, numbers, and common punctuation
        text = re.sub(r"[^\u4e00-\u9fa5\u0800-\u9fa0a-zA-Z0-9\s.,!?;:'\"-]", "", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text
