#!/usr/bin/env python3
"""Summarization - Translates and summarizes articles to Hebrew using LLM."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from llm_provider import get_provider, load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ARTICLES_DIR = DATA_DIR / "articles"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def summarize_articles():
    """Summarize all articles for today that haven't been summarized yet."""
    config = load_config()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    articles_file = ARTICLES_DIR / f"{today}.json"

    if not articles_file.exists():
        log.error(f"No articles file found for {today}")
        return []

    with open(articles_file, "r", encoding="utf-8") as f:
        articles = json.load(f)

    # Filter articles that haven't been summarized yet
    to_summarize = [a for a in articles if "summary_he" not in a]

    if not to_summarize:
        log.info("All articles already summarized")
        return articles

    log.info(f"Summarizing {len(to_summarize)} articles...")

    provider = get_provider(config)
    success_count = 0
    fail_count = 0

    for i, article in enumerate(to_summarize):
        title = article.get("title_original", "")
        content = article.get("description", "")
        category = article.get("category", "ai")

        # Use title + description as input
        full_text = f"{title}\n\n{content}" if content else title

        log.info(f"  [{i+1}/{len(to_summarize)}] {title[:60]}...")

        result = provider.summarize(title, full_text, category)

        # Update article with Hebrew content
        article["title_he"] = result.get("title_he", title)
        article["summary_he"] = result.get("summary", title)
        article["details_he"] = result.get("details", content[:500])
        article["category"] = result.get("category", category)

        if result.get("summary") and result["summary"] != title[:100]:
            success_count += 1
        else:
            fail_count += 1

    # Save enriched articles
    with open(articles_file, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    log.info(
        f"Summarization complete: {success_count} success, {fail_count} fallback, "
        f"{len(articles)} total articles"
    )
    return articles


if __name__ == "__main__":
    summarize_articles()
