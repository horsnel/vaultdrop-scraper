"""
Blood Strike scraper for VaultDrop.

Scrapes Reddit RSS feeds for r/BloodStrike and r/BloodStrikeLeaks,
classifies posts into categories, and generates AI-style captions.
"""

import logging
from datetime import datetime, timezone

from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# Reddit RSS feed URLs for Blood Strike
BLOODSTRIKE_RSS_FEEDS = [
    "https://www.reddit.com/r/BloodStrike/new/.rss",
    "https://www.reddit.com/r/BloodStrikeLeaks/new/.rss",
]

# Category classification keywords
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "leak": [
        "leak", "leaked", "datamine", "datamined", "upcoming",
        "unreleased", "season", "update", "patch",
    ],
    "skin": [
        "skin", "bundle", "cosmetic", "outfit", "camo",
        "camouflage", "operator",
    ],
    "weapon": [
        "weapon", "gun", "ar", "smg", "sniper", "shotgun",
        "lmg", "pistol", "melee",
    ],
    "map": [
        "map", "location", "zone", "terrain",
    ],
    "event": [
        "event", "limited", "challenge", "reward", "seasonal",
        "holiday", "anniversary",
    ],
    "esports": [
        "esports", "tournament", "competitive", "pro",
        "championship", "qualifier",
    ],
    "rumor": [
        "rumor", "rumour", "speculation", "alleged", "supposedly",
        "possibly", "maybe", "hint",
    ],
}


class BloodStrikeScraper(BaseScraper):
    """Scrapes Blood Strike Reddit RSS feeds for leak / news content."""

    name = "bloodstrike"
    game = "bloodstrike"

    # ------------------------------------------------------------------ #
    #  Public entry-point
    # ------------------------------------------------------------------ #

    def scrape(self) -> list[dict]:
        """Run the Blood Strike scraper and return a list of leak items."""
        items: list[dict] = []
        for feed_url in BLOODSTRIKE_RSS_FEEDS:
            logger.info("Fetching Blood Strike RSS feed: %s", feed_url)
            entries = self._fetch_reddit_rss(feed_url)
            for entry in entries:
                item = self._entry_to_leak_item(entry)
                if item:
                    items.append(item)
        logger.info("Blood Strike scraper found %d items", len(items))
        return items

    # ------------------------------------------------------------------ #
    #  Reddit RSS → leak-item mapping
    # ------------------------------------------------------------------ #

    def _entry_to_leak_item(self, entry: dict) -> dict | None:
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

        return {
            "type": "leak",
            "title": title,
            "game": self.game,
            "category": category,
            "source_url": url,
            "source_name": self._extract_subreddit(url),
            "thumbnail_url": thumbnail_url,
            "media_url": media_url,
            "ai_caption": caption,
            "description": "",
            "severity": "normal",
            "is_verified": False,
            "published_at": published_ts,
            "raw_data": {
                "author": entry.get("author", ""),
                "published": published,
                "subreddit": self._extract_subreddit(url),
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
