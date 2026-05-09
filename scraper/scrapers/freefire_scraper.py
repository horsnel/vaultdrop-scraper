"""
Free Fire scraper for VaultDrop.

Scrapes Reddit RSS feeds for r/freefire, r/FreeFireLeaks, and r/FreeFire_br,
classifies posts into categories, and generates AI-style captions.
Portuguese-language posts from r/FreeFire_br are tagged accordingly.
"""

import logging
from datetime import datetime, timezone

from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# Reddit RSS feed URLs for Free Fire
FREEFIRE_RSS_FEEDS = [
    "https://www.reddit.com/r/freefire/new/.rss",
    "https://www.reddit.com/r/FreeFireLeaks/new/.rss",
    "https://www.reddit.com/r/FreeFire_br/new/.rss",
]

# Portuguese-language subreddits (for tagging)
PORTUGUESE_SUBREDDITS = {"FreeFire_br"}

# Category classification keywords
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "leak": [
        "leak", "leaked", "datamine", "datamed", "upcoming",
        "unreleased", "season", "update", "patch", "elite pass",
        "vazou", "vazamento",  # Portuguese
    ],
    "skin": [
        "skin", "bundle", "cosmetic", "outfit", "camo",
        "character", "roupa", "visual",  # Portuguese
    ],
    "weapon": [
        "weapon", "gun", "ar", "smg", "sniper", "shotgun",
        "pistol", "melee", "arma",  # Portuguese
    ],
    "map": [
        "map", "location", "bermuda", "kalhari", "purgatory",
        "alpine", "mapa",  # Portuguese
    ],
    "event": [
        "event", "limited", "challenge", "reward", "seasonal",
        "holiday", "anniversary", "collab", "evento",  # Portuguese
    ],
    "esports": [
        "esports", "tournament", "competitive", "pro",
        "ffws", "ffes", "world series", "campeonato",  # Portuguese
    ],
    "rumor": [
        "rumor", "rumour", "speculation", "alleged", "supposedly",
        "possibly", "maybe", "hint", "boato",  # Portuguese
    ],
}


class FreeFireScraper(BaseScraper):
    """Scrapes Free Fire Reddit RSS feeds for leak / news content."""

    GAME = "freefire"

    # ------------------------------------------------------------------ #
    #  Public entry-point
    # ------------------------------------------------------------------ #

    def scrape(self) -> list[dict]:
        """Run the Free Fire scraper and return a list of leak items."""
        items: list[dict] = []
        for feed_url in FREEFIRE_RSS_FEEDS:
            logger.info("Fetching Free Fire RSS feed: %s", feed_url)
            entries = self._fetch_reddit_rss(feed_url)
            for entry in entries:
                item = self._entry_to_leak_item(entry, feed_url)
                if item:
                    items.append(item)
        logger.info("Free Fire scraper found %d items", len(items))
        return items

    # ------------------------------------------------------------------ #
    #  Reddit RSS → leak-item mapping
    # ------------------------------------------------------------------ #

    def _entry_to_leak_item(self, entry: dict, feed_url: str) -> dict | None:
        """Convert an RSS entry dict into a VaultDrop leak-item dict."""
        title = entry.get("title", "").strip()
        url = entry.get("url", "").strip()
        if not title or not url:
            return None

        content_html = entry.get("content_html", "")
        category = self._classify_category(title + " " + content_html)
        media_url = self.extract_media_urls(content_html)

        # Use thumbnail as fallback for media_url
        thumbnail_url = entry.get("thumbnail_url", "")
        if not media_url and thumbnail_url:
            media_url = thumbnail_url

        caption = self._generate_caption(title, category)

        # Parse published timestamp
        published = entry.get("published", "")
        published_ts = self._parse_timestamp(published)

        # Determine language tag from the feed URL / subreddit
        subreddit = self._extract_subreddit(url)
        language = "pt" if subreddit in PORTUGUESE_SUBREDDITS else "en"

        return {
            "title": title,
            "game": self.GAME,
            "category": category,
            "source_url": url,
            "thumbnail_url": thumbnail_url,
            "media_url": media_url,
            "caption": caption,
            "published_at": published_ts,
            "language": language,
            "raw_data": {
                "author": entry.get("author", ""),
                "published": published,
                "subreddit": subreddit,
            },
        }

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _classify_category(text: str) -> str:
        """Classify a post into a category based on keyword matching."""
        text_lower = text.lower()
        best_category = "general"
        best_count = 0
        for category, keywords in CATEGORY_KEYWORDS.items():
            count = sum(1 for kw in keywords if kw in text_lower)
            if count > best_count:
                best_count = count
                best_category = category
        return best_category

    @staticmethod
    def _generate_caption(title: str, category: str) -> str:
        """Generate a short caption for the leak item."""
        cat_emoji = {
            "leak": "🚨",
            "skin": "🎨",
            "weapon": "🔫",
            "map": "🗺️",
            "event": "🎉",
            "esports": "🏆",
            "rumor": "💭",
            "general": "📋",
        }
        emoji = cat_emoji.get(category, "📋")
        return f"{emoji} {title}"

    @staticmethod
    def _parse_timestamp(ts: str) -> str:
        """Parse an ISO-8601 timestamp; return it or empty string."""
        if not ts:
            return ""
        try:
            dt = datetime.fromisoformat(ts)
            return dt.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError):
            return ts

    @staticmethod
    def _extract_subreddit(url: str) -> str:
        """Extract the subreddit name from a Reddit URL."""
        import re

        m = re.search(r"/r/([^/]+)", url)
        return m.group(1) if m else ""
