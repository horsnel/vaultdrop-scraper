"""
Meme scraper for VaultDrop.

Scrapes Reddit RSS search feeds for meme-flaired posts across
gaming subreddits, filtering for image content.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import quote_plus

from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# Subreddits to search for memes
MEME_SUBREDDITS = [
    "CallOfDutyMobile",
    "PUBGMobile",
    "freefire",
    "BloodStrike",
    "mobilegaming",
    "gamingmemes",
]

# Image URL patterns for filtering
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")


class MemeScraper(BaseScraper):
    """Scrapes Reddit RSS search feeds for gaming meme images."""

    GAME = "multi"

    # ------------------------------------------------------------------ #
    #  Public entry-point
    # ------------------------------------------------------------------ #

    def scrape(self) -> list[dict]:
        """Run the meme scraper and return a list of meme items."""
        items: list[dict] = []
        seen_urls: set[str] = set()

        for subreddit in MEME_SUBREDDITS:
            # Search for meme-flaired posts sorted by hot
            rss_url = (
                f"https://www.reddit.com/r/{subreddit}/search/.rss"
                f"?q={quote_plus('flair:Meme')}&sort=hot&limit=15"
            )
            logger.info("Fetching meme RSS: %s", rss_url)
            entries = self._fetch_reddit_rss(rss_url)

            for entry in entries:
                url = entry.get("url", "").strip()
                if not url or url in seen_urls:
                    continue

                item = self._entry_to_meme_item(entry)
                if item:
                    seen_urls.add(url)
                    items.append(item)

        logger.info("Meme scraper found %d items", len(items))
        return items

    # ------------------------------------------------------------------ #
    #  RSS → meme-item mapping
    # ------------------------------------------------------------------ #

    def _entry_to_meme_item(self, entry: dict) -> dict | None:
        """Convert an RSS entry into a meme item, filtering for images."""
        title = entry.get("title", "").strip()
        url = entry.get("url", "").strip()
        if not title or not url:
            return None

        content_html = entry.get("content_html", "")
        media_url = self._extract_meme_image(content_html)

        # Use thumbnail as fallback
        thumbnail_url = entry.get("thumbnail_url", "")
        if not media_url and thumbnail_url:
            media_url = thumbnail_url

        # Only include items that have an image (memes should be visual)
        if not media_url:
            return None

        # Additional filter: ensure the media URL looks like an image
        if not self._is_image_url(media_url) and not self._is_reddit_media(media_url):
            return None

        game = self._detect_game(title + " " + content_html)
        published = entry.get("published", "")
        published_ts = self._parse_timestamp(published)

        return {
            "title": title,
            "game": game,
            "category": "meme",
            "source_url": url,
            "thumbnail_url": thumbnail_url,
            "media_url": media_url,
            "caption": f"😂 {title}",
            "published_at": published_ts,
            "raw_data": {
                "author": entry.get("author", ""),
                "published": published,
                "subreddit": self._extract_subreddit(url),
            },
        }

    # ------------------------------------------------------------------ #
    #  Image filtering helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_meme_image(content_html: str) -> str:
        """Extract the best image URL from content HTML for a meme post.

        Priority: i.redd.it > external-preview > generic img src.
        """
        return BaseScraper.extract_media_urls(content_html)

    @staticmethod
    def _is_image_url(url: str) -> bool:
        """Check if a URL points directly to an image file."""
        url_lower = url.lower().split("?")[0]  # strip query params
        return url_lower.endswith(IMAGE_EXTENSIONS)

    @staticmethod
    def _is_reddit_media(url: str) -> bool:
        """Check if a URL is a Reddit-hosted media URL (image or video)."""
        return any(
            domain in url
            for domain in ("i.redd.it", "v.redd.it", "external-preview.redd.it")
        )

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _detect_game(text: str) -> str:
        """Detect which game a meme is about from its text."""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ("codm", "call of duty mobile", "cod mobile")):
            return "codm"
        if any(kw in text_lower for kw in ("pubgm", "pubg mobile", "bgmi")):
            return "pubgm"
        if any(kw in text_lower for kw in ("free fire", "freefire", "free_fire")):
            return "freefire"
        if any(kw in text_lower for kw in ("blood strike", "bloodstrike")):
            return "bloodstrike"
        return "multi"

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
