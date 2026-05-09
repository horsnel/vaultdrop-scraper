"""
Advance Server Tracker scraper for VaultDrop.

Uses Reddit RSS search feeds to discover advance-server / test-server
registration openings for mobile games (CODM, PUBGM, Free Fire, Blood Strike).
Also checks official registration pages directly (non-Reddit, kept as-is).
"""

import logging
from datetime import datetime, timezone
from urllib.parse import quote_plus

from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# Subreddits to search for advance-server mentions
SEARCH_SUBREDDITS = [
    "CallOfDutyMobile",
    "PUBGMobile",
    "freefire",
    "BloodStrike",
    "GamingLeaksAndRumours",
]

# Search queries (URL-encoded later)
SEARCH_QUERIES = [
    "advance server",
    "test server",
    "beta registration",
    "pts registration",
    "codm OR pubgm OR free fire OR blood strike advance server",
]


class AdvanceServerTracker(BaseScraper):
    """Tracks advance / test server registration openings via Reddit RSS search."""

    name = "advance_server_tracker"
    game = "multi"  # covers multiple games

    # ------------------------------------------------------------------ #
    #  Public entry-point
    # ------------------------------------------------------------------ #

    def scrape(self) -> list[dict]:
        """Run the advance-server tracker and return a list of items."""
        items: list[dict] = []

        # Reddit RSS search
        reddit_items = self._scrape_reddit_search()
        items.extend(reddit_items)

        # Direct registration page checks (non-Reddit, unchanged)
        reg_items = self._check_registration_pages()
        items.extend(reg_items)

        logger.info("Advance Server tracker found %d items", len(items))
        return items

    # ------------------------------------------------------------------ #
    #  Reddit RSS search
    # ------------------------------------------------------------------ #

    def _scrape_reddit_search(self) -> list[dict]:
        """Search Reddit via RSS for advance-server / test-server posts."""
        items: list[dict] = []
        seen_urls: set[str] = set()

        for subreddit in SEARCH_SUBREDDITS:
            for query in SEARCH_QUERIES:
                rss_url = (
                    f"https://www.reddit.com/r/{subreddit}/search/.rss"
                    f"?q={quote_plus(query)}&sort=new&limit=15"
                )
                logger.info("Searching RSS: %s", rss_url)
                entries = self._fetch_reddit_rss(rss_url)

                for entry in entries:
                    url = entry.get("url", "").strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)

                    item = self._entry_to_tracker_item(entry)
                    if item:
                        items.append(item)

        return items

    def _entry_to_tracker_item(self, entry: dict) -> dict | None:
        """Convert an RSS search entry into a tracker item."""
        title = entry.get("title", "").strip()
        url = entry.get("url", "").strip()
        if not title or not url:
            return None

        content_html = entry.get("content_html", "")
        game = self._detect_game(title + " " + content_html)
        media_url = self.extract_media_urls(content_html)

        thumbnail_url = entry.get("thumbnail_url", "")
        if not media_url and thumbnail_url:
            media_url = thumbnail_url

        published = entry.get("published", "")
        published_ts = self._parse_timestamp(published)

        return {
            "type": "advance_server",
            "title": title,
            "game": game,
            "category": "advance_server",
            "source_url": url,
            "source_name": self._extract_subreddit(url),
            "thumbnail_url": thumbnail_url,
            "media_url": media_url,
            "ai_caption": f"🔓 {title}",
            "published_at": published_ts,
            "raw_data": {
                "author": entry.get("author", ""),
                "published": published,
                "subreddit": self._extract_subreddit(url),
            },
        }

    # ------------------------------------------------------------------ #
    #  Direct registration page checks
    # ------------------------------------------------------------------ #

    # Registration page targets (matching targets.yaml)
    REGISTRATION_URLS = {
        "freefire": "https://ff.garena.com/advance-server/",
        "pubgm": "https://www.pubgmobile.com/en-US/beta/",
    }

    def _check_registration_pages(self) -> list[dict]:
        """Check known advance-server registration pages for status changes."""
        items: list[dict] = []
        for game_key, url in self.REGISTRATION_URLS.items():
            try:
                resp = self._fetch(url)
                if not resp:
                    continue
                is_open = any(kw in resp.text.lower() for kw in (
                    "register now", "sign up", "download now", "registration open",
                    "join now", "apply now", "accepting applications",
                ))
                status = "open" if is_open else "closed"
                items.append({
                    "type": "advance_server",
                    "game": game_key,
                    "server_name": f"{game_key.upper()} Advance Server",
                    "status": status,
                    "registration_url": url,
                    "source_url": url,
                    "source_name": "Official",
                    "title": f"{game_key.upper()} Advance Server registration is {status}",
                    "category": "test_server",
                    "notes": f"Registration page checked at {datetime.now(timezone.utc).isoformat()}",
                    "thumbnail_url": "",
                    "media_url": "",
                    "ai_caption": f"🔓 {game_key.upper()} Advance Server registration is {status}",
                    "severity": "high",
                    "is_verified": False,
                    "raw_data": {"source": "registration_page", "is_open": is_open},
                })
            except Exception as exc:
                logger.debug(f"Registration check failed for {game_key}: {exc}")
        return items

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _detect_game(text: str) -> str:
        """Detect which game a post is about from its text."""
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
