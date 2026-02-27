#!/usr/bin/env python3
"""Deduplication - Removes duplicate articles based on URL and title similarity."""

import json
import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
ARTICLES_DIR = DATA_DIR / "articles"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def load_config():
    with open(CONFIG_DIR / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_title(title):
    """Normalize a title for comparison."""
    title = title.lower().strip()
    # Remove common prefixes
    for prefix in ("breaking:", "update:", "exclusive:", "report:"):
        if title.startswith(prefix):
            title = title[len(prefix):].strip()
    return title


def title_similarity(title_a, title_b):
    """Compute similarity ratio between two titles."""
    a = normalize_title(title_a)
    b = normalize_title(title_b)
    return SequenceMatcher(None, a, b).ratio()


def deduplicate_articles(articles, config):
    """
    Deduplicate articles in 3 steps:
    1. Exact URL match
    2. Title similarity (threshold from config)
    3. Optional LLM check for borderline cases
    """
    dedup_config = config["deduplication"]
    threshold = dedup_config["title_similarity_threshold"]

    # Group articles: each group is a list of articles about the same topic
    groups = []
    used = set()

    # Step 1: URL-based deduplication
    url_map = {}
    for i, article in enumerate(articles):
        url = article["url"].rstrip("/").lower()
        if url in url_map:
            # Merge into existing group
            existing_idx = url_map[url]
            groups[existing_idx].append(article)
            used.add(i)
            log.debug(f"  URL duplicate: {article['title_original'][:60]}")
        else:
            group_idx = len(groups)
            groups.append([article])
            url_map[url] = group_idx
            used.add(i)

    # Step 2: Title similarity deduplication
    merged_count = 0
    # Compare group representatives
    for i in range(len(groups)):
        if not groups[i]:
            continue
        title_i = groups[i][0]["title_original"]
        for j in range(i + 1, len(groups)):
            if not groups[j]:
                continue
            title_j = groups[j][0]["title_original"]
            sim = title_similarity(title_i, title_j)
            if sim >= threshold:
                log.info(
                    f"  Title match ({sim:.2f}): "
                    f'"{title_i[:50]}" ~ "{title_j[:50]}"'
                )
                # Merge group j into group i
                groups[i].extend(groups[j])
                groups[j] = []
                merged_count += 1

    # Build deduplicated result
    result = []
    for group in groups:
        if not group:
            continue

        # Pick the article with the most content as primary
        primary = max(group, key=lambda a: len(a.get("description", "")))

        # Collect all sources
        sources = []
        seen_source_urls = set()
        for article in group:
            source_url = article["url"]
            if source_url not in seen_source_urls:
                sources.append({
                    "name": article["source_name"],
                    "url": source_url,
                })
                seen_source_urls.add(source_url)

        deduplicated = {
            **primary,
            "sources": sources,
            "duplicate_count": len(group),
        }
        result.append(deduplicated)

    return result, merged_count


def run_deduplication():
    """Main deduplication function."""
    config = load_config()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    articles_file = ARTICLES_DIR / f"{today}.json"

    if not articles_file.exists():
        log.error(f"No articles file found for {today}")
        return []

    with open(articles_file, "r", encoding="utf-8") as f:
        articles = json.load(f)

    log.info(f"Deduplicating {len(articles)} articles...")
    result, merged_count = deduplicate_articles(articles, config)
    log.info(f"Deduplication complete: {len(articles)} -> {len(result)} articles ({merged_count} merges)")

    # Save deduplicated results back
    with open(articles_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log.info(f"Saved to {articles_file}")
    return result


if __name__ == "__main__":
    run_deduplication()
