"""arXiv paper source.

Uses the official arXiv API (Atom XML). We fetch with `requests` (its certifi
bundle works on Windows) and parse the body with `feedparser`, because
feedparser's own HTTPS fetch fails SSL verification on this platform.

API: http://export.arxiv.org/api/query
Docs: https://info.arxiv.org/help/api/index.html
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import List

import feedparser
import requests

from ..items import InfoItem
from .base import BaseSource

# arXiv asks for ~3s between requests; we only fire one batched query per
# category, and run once a day, so this is well within limits.
_API_URL = "http://export.arxiv.org/api/query"
_HEADERS = {"User-Agent": "info-scraper/1.0 (daily digest; mailto:none)"}
# Search returns more results than subscription (full keyword search, not just
# the latest N per category). Capped to stay well under API rate limits.
_SEARCH_MAX = 100


def _parse_published(entry) -> datetime:
    """arXiv publishes <published> as RFC3339; feedparser exposes parsed."""
    for field_name in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, field_name, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    return datetime.now(timezone.utc)


def _entry_to_item(entry, source_name: str, category: str) -> InfoItem | None:
    """Convert one arXiv Atom entry to an InfoItem, or None if unusable."""
    url = getattr(entry, "link", "") or ""
    if not url:
        return None
    # arXiv abstracts carry LaTeX/math; keep raw - rendering is the consumer's
    # job.
    return InfoItem(
        title=(getattr(entry, "title", "") or "").strip().replace("\n", " "),
        url=url,
        summary=(getattr(entry, "summary", "") or "").strip(),
        published=_parse_published(entry),
        source_name=source_name,
        source_category=category,
    )


class ArxivSource(BaseSource):
    name = "arxiv"
    display_name = "arXiv 论文"
    emoji = "📚"

    def _query(self, search_query: str, max_results: int,
               sort_by: str, category: str) -> List[InfoItem]:
        """Run one arXiv API query and return parsed items. Never raises."""
        try:
            params = {
                "search_query": search_query,
                "start": 0,
                "max_results": max_results,
                "sortBy": sort_by,
                "sortOrder": "descending",
            }
            resp = requests.get(_API_URL, params=params,
                                headers=_HEADERS, timeout=30)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.text)
            if not parsed.entries:
                return []
            items: List[InfoItem] = []
            for entry in parsed.entries[:max_results]:
                item = _entry_to_item(entry, self.name, category)
                if item is not None:
                    items.append(item)
            return items
        except Exception as e:
            print(f"[warn] arxiv query failed ({search_query}): {e}",
                  file=sys.stderr)
            return []

    def fetch(self, config: dict) -> List[InfoItem]:
        """Subscription mode: latest papers per configured category."""
        categories: List[str] = config.get("categories", [])
        max_results: int = int(config.get("max_results", 15))
        if not categories:
            print("[warn] arxiv: no categories configured", file=sys.stderr)
            return []

        items: List[InfoItem] = []
        for category in categories:
            found = self._query(
                search_query=f"cat:{category}",
                max_results=max_results,
                sort_by="submittedDate",
                category=category,
            )
            print(f"[info] arxiv cat={category}: {len(found)} entries",
                  file=sys.stderr)
            items.extend(found)
        return items

    def search(self, config: dict, query: str) -> List[InfoItem]:
        """Search mode: full-text keyword search across all arXiv.

        Searches ALL arXiv (not just configured categories) so the user finds
        papers regardless of their category. Sorted by relevance so keyword
        matches surface first.
        """
        query = (query or "").strip()
        if not query:
            return []
        # arXiv `all:` searches title+abstract+comments across every category.
        found = self._query(
            search_query=f"all:{query}",
            max_results=_SEARCH_MAX,
            sort_by="relevance",
            category=f"search: {query}",
        )
        print(f"[info] arxiv search '{query}': {len(found)} entries",
              file=sys.stderr)
        return found
