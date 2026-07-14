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


class ArxivSource(BaseSource):
    name = "arxiv"
    display_name = "arXiv 论文"
    emoji = "📚"

    def fetch(self, config: dict) -> List[InfoItem]:
        categories: List[str] = config.get("categories", [])
        max_results: int = int(config.get("max_results", 15))
        if not categories:
            print("[warn] arxiv: no categories configured", file=sys.stderr)
            return []

        items: List[InfoItem] = []
        for category in categories:
            try:
                query = f"cat:{category}"
                params = {
                    "search_query": query,
                    "start": 0,
                    "max_results": max_results,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
                resp = requests.get(_API_URL, params=params,
                                    headers=_HEADERS, timeout=30)
                resp.raise_for_status()
                parsed = feedparser.parse(resp.text)
                if not parsed.entries:
                    print(f"[warn] arxiv cat={category}: no entries",
                          file=sys.stderr)
                    continue
                for entry in parsed.entries[:max_results]:
                    url = getattr(entry, "link", "") or ""
                    if not url:
                        continue
                    # arXiv abstracts carry LaTeX/math; keep raw - rendering is
                    # the consumer's job.
                    items.append(InfoItem(
                        title=(getattr(entry, "title", "") or "").strip()
                              .replace("\n", " "),
                        url=url,
                        summary=(getattr(entry, "summary", "") or "").strip(),
                        published=_parse_published(entry),
                        source_name=self.name,
                        source_category=category,
                    ))
                print(f"[info] arxiv cat={category}: "
                      f"{len(parsed.entries[:max_results])} entries",
                      file=sys.stderr)
            except Exception as e:
                print(f"[warn] arxiv cat={category} failed: {e}",
                      file=sys.stderr)
        return items
