"""
Base scraper class for VaultDrop.

Provides shared HTTP fetching utilities and the Reddit RSS feed parser.
Reddit's JSON API requires OAuth2 credentials which are no longer
obtainable, so we use public RSS (.rss) feeds instead.
"""

import logging
import re
import time
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger(__name__)

# Atom and Media RSS namespaces
ATOM_NS = "{http://www.w3.org/2005/Atom}"
MEDIA_NS = "{http://search.yahoo.com/mrss/}"


class BaseScraper:
    """Base class for all VaultDrop scrapers."""

    # ------------------------------------------------------------------ #
    #  Generic HTTP helpers (non-Reddit)
    # ------------------------------------------------------------------ #

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )
        self._last_request_time: float = 0.0
        self._rate_limit_seconds: float = 2.0

    def _rate_limit(self):
        """Sleep if needed to respect rate-limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_seconds:
            time.sleep(self._rate_limit_seconds - elapsed)
        self._last_request_time = time.time()

    def _fetch(self, url: str, **kwargs) -> requests.Response | None:
        """GET *url* with rate-limiting. Returns Response or None on failure."""
        self._rate_limit()
        try:
            resp = self._session.get(url, timeout=30, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            return None

    def _fetch_json(self, url: str, **kwargs) -> dict | list | None:
        """GET *url* and return parsed JSON, or None on failure."""
        resp = self._fetch(url, **kwargs)
        if resp is None:
            return None
        try:
            return resp.json()
        except ValueError as exc:
            logger.warning("Invalid JSON from %s: %s", url, exc)
            return None

    # ------------------------------------------------------------------ #
    #  Reddit RSS feed parser
    # ------------------------------------------------------------------ #

    def _fetch_reddit_rss(self, rss_url: str) -> list[dict]:
        """Fetch and parse a Reddit Atom RSS feed.

        Parameters
        ----------
        rss_url :
            Full URL to a Reddit RSS feed, e.g.
            ``https://www.reddit.com/r/CallOfDutyMobile/new/.rss``

        Returns
        -------
        list[dict]
            A list of entry dicts, each containing:
            ``title``, ``author``, ``url``, ``thumbnail_url``,
            ``published``, ``content_html``.
            Returns an empty list on any failure (never raises).
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/atom+xml,application/xml,text/xml",
        }

        self._rate_limit()
        try:
            resp = self._session.get(rss_url, headers=headers, timeout=30)
            resp.raise_for_status()
            xml_text = resp.text
        except requests.RequestException as exc:
            logger.warning("Failed to fetch Reddit RSS %s: %s", rss_url, exc)
            return []

        return self._parse_reddit_rss_xml(xml_text)

    @staticmethod
    def _parse_reddit_rss_xml(xml_text: str) -> list[dict]:
        """Parse Reddit Atom XML into a list of entry dicts.

        This is a static helper so it can be tested without network access.
        """
        entries: list[dict] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.warning("Failed to parse Reddit RSS XML: %s", exc)
            return entries

        for entry_el in root.findall(f"{ATOM_NS}entry"):
            try:
                # title
                title_el = entry_el.find(f"{ATOM_NS}title")
                title = title_el.text if title_el is not None and title_el.text else ""

                # author
                author_el = entry_el.find(f"{ATOM_NS}author/{ATOM_NS}name")
                author = author_el.text if author_el is not None and author_el.text else ""

                # link
                link_el = entry_el.find(f"{ATOM_NS}link")
                url = link_el.get("href", "") if link_el is not None else ""

                # published
                published_el = entry_el.find(f"{ATOM_NS}published")
                published = (
                    published_el.text
                    if published_el is not None and published_el.text
                    else ""
                )

                # media:thumbnail
                thumb_el = entry_el.find(f"{MEDIA_NS}thumbnail")
                thumbnail_url = thumb_el.get("url", "") if thumb_el is not None else ""

                # content (HTML)
                content_el = entry_el.find(f"{ATOM_NS}content")
                content_html = (
                    content_el.text
                    if content_el is not None and content_el.text
                    else ""
                )

                entries.append(
                    {
                        "title": title,
                        "author": author,
                        "url": url,
                        "thumbnail_url": thumbnail_url,
                        "published": published,
                        "content_html": content_html,
                    }
                )
            except Exception as exc:
                logger.warning("Error parsing RSS entry, skipping: %s", exc)
                continue

        return entries

    # ------------------------------------------------------------------ #
    #  Media URL extraction helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def extract_media_urls(content_html: str) -> str:
        """Extract the first media (image or video) URL from RSS content HTML.

        Priority order:
        1. i.redd.it images
        2. v.redd.it videos
        3. external-preview.redd.it images
        4. generic img src (jpg/jpeg/png/gif/webp)
        5. gallery links
        """
        if not content_html:
            return ""

        # i.redd.it images
        ireddit = re.findall(r"(https?://i\.redd\.it/[^\s\"<>]+)", content_html)
        if ireddit:
            return ireddit[0]

        # v.redd.it videos
        video = re.findall(r'href="(https?://v\.redd\.it/[^"]*)"', content_html)
        if video:
            return video[0]

        # external-preview.redd.it images
        preview = re.findall(r"(https?://external-preview\.redd\.it/[^\s\"<>]+)", content_html)
        if preview:
            return preview[0]

        # generic img src
        img = re.findall(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|gif|webp)[^"]*)"', content_html)
        if img:
            return img[0]

        # gallery links
        gallery = re.findall(r'href="(https?://www\.reddit\.com/gallery/[^"]*)"', content_html)
        if gallery:
            return gallery[0]

        return ""
