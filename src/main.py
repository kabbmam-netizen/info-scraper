"""Information scraper entry point.

Two modes:
  - Subscription (default): `python -m src.main`
    Fetch latest items from each enabled source, archive to
    digests/YYYY-MM-DD.md, push a summary to WeChat.
  - Search: `python -m src.main --search QUERY`
    Full-text keyword search across sources (arXiv, ...), archive to
    digests/search-{QUERY}-{YYYY-MM-DD}.md, push the top results to WeChat.

GitHub Actions: the workflow_dispatch `search` input maps to --search, so a
manual run with a keyword triggers search mode.
"""
from __future__ import annotations

import argparse
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
# keep alphanumerics, CJK, underscore, hyphen; replace the rest with '_'
_SAFE_FN_RE = re.compile(r"[^a-zA-Z0-9一-鿿_-]")


def _strip_html(text: str) -> str:
    text = _TAG_RE.sub("", text)
    text = unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _safe_filename_part(query: str) -> str:
    """Make a query safe for use in a digest filename."""
    return _SAFE_FN_RE.sub("_", query).strip("_")[:30] or "query"


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
                      source_meta: dict, search_query: str = "") -> str:
    """Render the full Markdown digest, grouped by source then category."""
    if search_query:
        title = f"# 搜索「{search_query}」- {today.isoformat()}"
        intro = f"> 共找到 {len(items)} 条结果，按数据源分类。"
    else:
        title = f"# 每日信息摘要 - {today.isoformat()}"
        intro = f"> 共收录 {len(items)} 条，按数据源分类，时间倒序。"
    lines = [title, "", intro, ""]
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
                             max_items: int, source_meta: dict,
                             search_query: str = "") -> str:
    """Compact message for WeChat push (kept short for size limits)."""
    if search_query:
        lines = [f"## 搜索「{search_query}」结果（{len(items)} 条）", ""]
    else:
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
        # search mode preserves source ordering (relevance); subscription
        # mode sorts newest-first.
        if not search_query:
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
    if search_query:
        fn = f"search-{_safe_filename_part(search_query)}-{today.isoformat()}.md"
        lines.append(f"> 完整列表见仓库 `digests/{fn}`")
    else:
        lines.append(f"> 完整列表见仓库 `digests/{today.isoformat()}.md`")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Information scraper")
    parser.add_argument("--search", type=str, default="",
                        help="keyword search (empty = subscription mode)")
    args = parser.parse_args()
    search_query = (args.search or "").strip()

    config = Config.from_file(CONFIG_PATH)
    registry = discover_sources()
    mode = "search" if search_query else "subscription"
    print(f"[info] mode: {mode}"
          + (f" | query='{search_query}'" if search_query else ""),
          file=sys.stderr)
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
        src_config = config.sources[source_name]
        if search_query:
            print(f"[info] searching source '{source_name}' "
                  f"for '{search_query}'...", file=sys.stderr)
            items = source.search(src_config, search_query)
        else:
            print(f"[info] fetching source '{source_name}'...", file=sys.stderr)
            items = source.fetch(src_config)
            # cap PER source_category (e.g. each arxiv category, each HN feed),
            # not per source total - so adding categories never starves others.
            cap = config.max_items_per_source
            by_cat: dict[str, list[InfoItem]] = defaultdict(list)
            for it in items:
                by_cat[it.source_category].append(it)
            items = [it for cat_items in by_cat.values()
                     for it in cat_items[:cap]]
        print(f"[info] source '{source_name}': {len(items)} items",
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
    markdown = generate_markdown(unique, today, source_meta, search_query)

    DIGESTS_DIR.mkdir(exist_ok=True)
    if search_query:
        out_name = f"search-{_safe_filename_part(search_query)}-" \
                   f"{today.isoformat()}.md"
        push_title = f"搜索「{search_query}」结果（{len(unique)} 条）"
    else:
        out_name = f"{today.isoformat()}.md"
        push_title = f"每日信息摘要 {today.isoformat()}"
    output_path = DIGESTS_DIR / out_name
    output_path.write_text(markdown, encoding="utf-8")
    print(f"[info] digest written to {output_path} "
          f"({len(unique)} items)", file=sys.stderr)

    webhook_url = os.environ.get("WEBHOOK_URL", "").strip()
    if webhook_url:
        msg = generate_webhook_message(unique, today, config.max_push_items,
                                       source_meta, search_query)
        notify(webhook_url, msg, push_title)
    else:
        print("[info] WEBHOOK_URL not set, skipping notification",
              file=sys.stderr)

    print(f"::notice::Digest generated: {out_name} ({len(unique)} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
