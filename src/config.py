"""Configuration loading from config.yml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass
class Config:
    sources: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    max_items_per_source: int = 15
    max_push_items: int = 20
    timezone_offset: int = 8

    @classmethod
    def from_file(cls, path: str | Path) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(
            sources=data.get("sources", {}) or {},
            max_items_per_source=data.get("max_items_per_source", 15),
            max_push_items=data.get("max_push_items", 20),
            timezone_offset=data.get("timezone_offset", 8),
        )

    def is_enabled(self, source_name: str) -> bool:
        block = self.sources.get(source_name, {})
        return bool(block.get("enabled", False))
