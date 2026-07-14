"""Daily information scraper entry point.

Discovers all source modules, fetches each enabled one, merges results into a
single Markdown digest saved to digests/YYYY-MM-DD.md, and optionally pushes a
summary to WeChat (PushPlus / Server酱 / 企业微信 / 钉钉).

Run locally:
    pip install -r requirements.txt
    python -m src.main
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from html import unescape
from pathlib import Path
import re

from .config import Config
from .items import InfoItem
from .notifiers import notify
from .sources import discover_sources

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(text: str) -> str:
    text = _TAG_RE.sub("", text)
    text = unescape(text)
    return _WS_RE.sub(" ", text).strip()


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yml"
DIGESTS_DIR = REPO_ROOT / "digests"


def _today(tz_offset: int) -> date:
    tz = timezone(timedelta(hours=tz_offset))
    return datetime.now(tz).date()


def _group_by_source(items: list[InfoItem]):
    """items -> {source_name: {source_category: [items]}}."""
    grouped: dict[str, dict[str, list[InfoItem]]] = defaultdict(
        lambda: defaultdict(list))
    for it in items:
        grouped[it.source_name][it.source_category].append(it)
    return grouped


def generate_markdown(items: list[InfoItem], today: date,
                      source_meta: dict) -> str:
    """Render the full Markdown digest, grouped by source then category."""
    lines = [
        f"# 每日信息摘要 - {today.isoformat()}",
        "",
        f"> 共收录 {len(items)} 条，按数据源分类，时间倒序。",
        "",
    ]
    grouped = _group_by_source(items)
    for source_name in sorted(grouped.keys()):
        meta = source_meta.get(source_name, {})
        emoji = meta.get("emoji", "")
        display = meta.get("display_name", source_name)
        cat_map = grouped[source_name]
        # flatten all items of this source for a count
        src_count = sum(len(v) for v in cat_map.values())
        lines.append(f"## {emoji} {display} ({src_count})")
        lines.append("")
        for category in sorted(cat_map.keys()):
            cat_items = cat_map[category]
            lines.append(f"### {category} ({len(cat_items)})")
            lines.append("")
            for it in cat_items:
                title = it.title or "(no title)"
                lines.append(f"- **[{title}]({it.url})**")
                lines.append(f"  - {it.published.strftime('%Y-%m-%d %H:%M UTC')}")
                summary = _strip_html(it.summary)
                if summary:
                    if len(summary) > 200:
                        summary = summary[:197] + "..."
                    lines.append(f"  - {summary}")
                lines.append("")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate_webhook_message(items: list[InfoItem], today: date,
                             max_items: int, source_meta: dict) -> str:
    """Compact message for WeChat push (kept short for size limits)."""
    lines = [f"## 每日信息摘要 {today.isoformat()}", ""]
    grouped = _group_by_source(items)
    pushed = 0
    for source_name in sorted(grouped.keys()):
        if pushed >= max_items:
            break
        meta = source_meta.get(source_name, {})
        emoji = meta.get("emoji", "")
        display = meta.get("display_name", source_name)
        # flatten this source's items newest-first
        src_items = []
        for cat_items in grouped[source_name].values():
            src_items.extend(cat_items)
        src_items.sort(key=lambda x: x.published, reverse=True)
        lines.append(f"{emoji} {display}")
        for it in src_items:
            if pushed >= max_items:
                break
            title = it.title or "(no title)"
            lines.append(f"- [{title}]({it.url})")
            pushed += 1
        lines.append("")
    if len(items) > pushed:
        lines.append(f"- ...及另外 {len(items) - pushed} 条")
        lines.append("")
    lines.append(f"> 完整列表见仓库 `digests/{today.isoformat()}.md`")
    return "\n".join(lines)


def main() -> int:
    config = Config.from_file(CONFIG_PATH)
    registry = discover_sources()
    print(f"[info] registered sources: {list(registry)}", file=sys.stderr)

    all_items: list[InfoItem] = []
    source_meta: dict = {}
    for source_name, SourceClass in registry.items():
        if not config.is_enabled(source_name):
            print(f"[info] source '{source_name}' disabled, skipping",
                  file=sys.stderr)
            continue
        if source_name not in config.sources:
            print(f"[info] source '{source_name}' has no config block, "
                  f"skipping", file=sys.stderr)
            continue
        source = SourceClass()
        source_meta[source_name] = {
            "display_name": getattr(source, "display_name", source_name),
            "emoji": getattr(source, "emoji", ""),
        }
        print(f"[info] fetching source '{source_name}'...", file=sys.stderr)
        items = source.fetch(config.sources[source_name])
        # cap PER source_category (e.g. each arxiv category, each HN feed),
        # not per source total - so adding categories never starves the others.
        cap = config.max_items_per_source
        by_cat: dict[str, list[InfoItem]] = defaultdict(list)
        for it in items:
            by_cat[it.source_category].append(it)
        items = [it for cat_items in by_cat.values() for it in cat_items[:cap]]
        print(f"[info] source '{source_name}': {len(items)} items "
              f"(cap {cap}/category, {len(by_cat)} categories)",
              file=sys.stderr)
        all_items.extend(items)

    if not all_items:
        print("[error] no items collected from any source", file=sys.stderr)
        return 1

    # dedup by URL across sources
    seen: set[str] = set()
    unique: list[InfoItem] = []
    for it in all_items:
        if it.url in seen:
            continue
        seen.add(it.url)
        unique.append(it)

    today = _today(config.timezone_offset)
    markdown = generate_markdown(unique, today, source_meta)

    DIGESTS_DIR.mkdir(exist_ok=True)
    output_path = DIGESTS_DIR / f"{today.isoformat()}.md"
    output_path.write_text(markdown, encoding="utf-8")
    print(f"[info] digest written to {output_path} "
          f"({len(unique)} items)", file=sys.stderr)

    webhook_url = os.environ.get("WEBHOOK_URL", "").strip()
    if webhook_url:
        msg = generate_webhook_message(unique, today, config.max_push_items,
                                       source_meta)
        notify(webhook_url, msg, f"每日信息摘要 {today.isoformat()}")
    else:
        print("[info] WEBHOOK_URL not set, skipping notification",
              file=sys.stderr)

    print(f"::notice::Daily info digest generated: "
          f"{today.isoformat()} ({len(unique)} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
