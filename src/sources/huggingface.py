"""HuggingFace datasets source.

Uses the public Hub API (JSON). HuggingFace hosts the largest collection of
open ML datasets, so this complements arXiv (papers) for the "research"
project: search/list datasets by popularity or keyword.

API: https://huggingface.co/api/datasets
Docs: https://huggingface.co/docs/hub/api

Note on subscription vs search:
  - Subscription (fetch): list trending datasets by `likes` desc. Sorting by
    `lastModified` instead surfaces low-quality personal test datasets, so
    popularity is the better "what's worth knowing about" signal.
  - Search (search): `search=<query>` keyword match, sorted by `downloads`
    desc so the most-used datasets surface first.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import List

import requests

from ..items import InfoItem
from .base import BaseSource

_API_URL = "https://huggingface.co/api/datasets"
_HEADERS = {"User-Agent": "info-scraper/1.0 (daily digest)"}
# Sort fields: 'likes' for popular datasets, 'downloads' for most-used.
# (lastModified is too noisy - dominated by personal test datasets.)
_SUBSCRIPTION_SORT = "likes"
_SEARCH_SORT = "downloads"


def _parse_dt(s: str) -> datetime:
    """Parse HF's RFC3339 lastModified (e.g. 2023-08-01T10:26:36.000Z)."""
    if not s:
        return datetime.now(timezone.utc)
    try:
        # 'Z' suffix -> '+00:00' for fromisoformat
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


class HuggingFaceSource(BaseSource):
    name = "huggingface"
    display_name = "HuggingFace 数据集"
    emoji = "🤗"

    def _list(self, params: dict, category: str) -> List[InfoItem]:
        """One API call; return parsed InfoItems. Never raises."""
        try:
            resp = requests.get(_API_URL, params=params,
                                headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[warn] huggingface query failed ({params}): {e}",
                  file=sys.stderr)
            return []

        if not isinstance(data, list):
            print(f"[warn] huggingface: unexpected response type "
                  f"{type(data).__name__}", file=sys.stderr)
            return []

        items: List[InfoItem] = []
        for d in data:
            ds_id = d.get("id") or ""
            if not ds_id:
                continue
            url = f"https://huggingface.co/datasets/{ds_id}"
            # Build a short summary from the stats we have.
            downloads = d.get("downloads", 0) or 0
            likes = d.get("likes", 0) or 0
            # HF descriptions are often full of stray blank lines/tabs from
            # markdown cards; collapse to a single line.
            desc = " ".join((d.get("description") or "").split())
            summary = f"downloads {downloads:,} | likes {likes}"
            if desc:
                summary += f" | {desc[:140]}"
            items.append(InfoItem(
                title=ds_id,
                url=url,
                summary=summary,
                published=_parse_dt(d.get("lastModified", "")),
                source_name=self.name,
                source_category=category,
            ))
        return items

    def fetch(self, config: dict) -> List[InfoItem]:
        """Subscription: trending datasets by popularity (likes desc)."""
        max_items: int = int(config.get("max_results", 15))
        found = self._list(
            params={
                "sort": _SUBSCRIPTION_SORT,
                "direction": "-1",
                "limit": max_items,
            },
            category="trending",
        )
        print(f"[info] huggingface trending: {len(found)} entries",
              file=sys.stderr)
        return found

    def search(self, config: dict, query: str) -> List[InfoItem]:
        """Search: keyword match, sorted by downloads desc."""
        query = (query or "").strip()
        if not query:
            return []
        max_items: int = int(config.get("max_search_results", 30))
        found = self._list(
            params={
                "search": query,
                "sort": _SEARCH_SORT,
                "direction": "-1",
                "limit": max_items,
            },
            category=f"search: {query}",
        )
        print(f"[info] huggingface search '{query}': {len(found)} entries",
              file=sys.stderr)
        return found
