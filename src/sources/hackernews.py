"""Hacker News source.

Uses the official HN RSS on news.ycombinator.com (reliable worldwide, unlike
the hnrss.org search wrapper which is blocked from some networks). Fetch with
`requests`, parse with `feedparser`.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import List

import feedparser
import requests

from ..items import InfoItem
from .base import BaseSource

# Official HN RSS endpoints. hnrss.org (search wrapper) is blocked from some
# networks, so we use these official feeds which are Cloudflare-fronted.
_FEED_URLS = {
    "frontpage": "https://news.ycombinator.com/rss",   # top front-page stories
    "show": "https://news.ycombinator.com/showrss",    # Show HN projects
}
_HEADERS = {"User-Agent": "info-scraper/1.0 (daily digest)"}


def _parse_published(entry) -> datetime:
    for field_name in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, field_name, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    return datetime.now(timezone.utc)


class HackerNewsSource(BaseSource):
    name = "hackernews"
    display_name = "Hacker News"
    emoji = "🟧"

    def fetch(self, config: dict) -> List[InfoItem]:
        feeds: List[str] = config.get("feeds", [])
        max_items: int = int(config.get("max_items", 15))
        if not feeds:
            print("[warn] hackernews: no feeds configured", file=sys.stderr)
            return []

        items: List[InfoItem] = []
        for feed_name in feeds:
            url = _FEED_URLS.get(feed_name)
            if not url:
                print(f"[warn] hackernews: unknown feed '{feed_name}' "
                      f"(known: {list(_FEED_URLS)})", file=sys.stderr)
                continue
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=20)
                resp.raise_for_status()
                parsed = feedparser.parse(resp.text)
                if not parsed.entries:
                    print(f"[warn] hackernews feed={feed_name}: no entries",
                          file=sys.stderr)
                    continue
                # HN RSS is already newest-first; cap to max_items.
                for entry in parsed.entries[:max_items]:
                    link = getattr(entry, "link", "") or ""
                    if not link:
                        continue
                    items.append(InfoItem(
                        title=(getattr(entry, "title", "") or "").strip(),
                        url=link,
                        summary=(getattr(entry, "summary", "") or "").strip(),
                        published=_parse_published(entry),
                        source_name=self.name,
                        source_category=feed_name,
                    ))
                print(f"[info] hackernews feed={feed_name}: "
                      f"{len(parsed.entries[:max_items])} entries",
                      file=sys.stderr)
            except Exception as e:
                print(f"[warn] hackernews feed={feed_name} failed: {e}",
                      file=sys.stderr)
        return items
