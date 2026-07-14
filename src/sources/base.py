"""Base class for all scraper sources.

A source is a pluggable module: implement `fetch()` and set the class
attributes. The registry (src/sources/__init__.py) discovers subclasses
automatically. A source must never raise - return [] on failure so other
sources still run.
"""
from __future__ import annotations

from typing import Any, List

from ..items import InfoItem


class BaseSource:
    name: str = ""            # registry key, must match config.yml block name
    display_name: str = ""   # human-readable label, shown in digest headers
    emoji: str = ""          # emoji prefix in the WeChat push

    def fetch(self, config: dict) -> List[InfoItem]:
        """Fetch items for this source. `config` is its config.yml block.

        Subscription mode: return the latest items. Must be self-contained:
        log warnings to stderr and return [] on any failure (network, parse,
        empty). Never raise.
        """
        raise NotImplementedError

    def search(self, config: dict, query: str) -> List[InfoItem]:
        """Keyword search across this source's full content.

        Search mode (triggered via `python -m src.main --search QUERY`). The
        default returns [] - sources that expose keyword search override this.
        Same resilience rule as fetch(): never raise, return [] on failure.
        """
        return []
