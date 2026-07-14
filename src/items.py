"""Shared data types."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class InfoItem:
    """A single scraped item (a paper, a post, a job listing, ...)."""
    title: str
    url: str
    summary: str
    published: datetime
    source_name: str        # module key, e.g. "arxiv", "hackernews"
    source_category: str   # in-source group, e.g. "cs.AI", "who is hiring"
