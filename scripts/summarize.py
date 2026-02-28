#!/usr/bin/env python3
"""Summarization - Fetches full article content and summarizes using LLM."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

from llm_provider import get_provider, load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ARTICLES_DIR = DATA_DIR / "articles"

LOG_DIR = DATA_DIR / "logs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Also log to a file for debugging (gets committed to repo)
LOG_DIR.mkdir(parents=True, exist_ok=True)
_file_handler = logging.FileHandler(LOG_DIR / "summarize_debug.log", mode="w", encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger().addHandler(_file_handler)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_article_content(url, timeout=15):
    """Fetch full article text from a URL using requests + BeautifulSoup."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.debug(f"  Could not fetch {url}: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove noise elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header",
                              "aside", "form", "iframe", "noscript"]):
        tag.decompose()

    # Try to find the main article content
    article_text = ""

    # Strategy 1: <article> tag
    article_tag = soup.find("article")
    if article_tag:
        article_text = article_tag.get_text(separator="\n", strip=True)

    # Strategy 2: Common content containers
    if len(article_text) < 200:
        for selector in [
            "[class*='article-body']", "[class*='post-content']",
            "[class*='entry-content']", "[class*='story-body']",
            "[class*='article-content']", "[class*='content-body']",
            "main", "[role='main']",
        ]:
            el = soup.select_one(selector)
            if el:
                candidate = el.get_text(separator="\n", strip=True)
                if len(candidate) > len(article_text):
                    article_text = candidate

    # Strategy 3: Collect all <p> tags as fallback
    if len(article_text) < 200:
        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")
                      if len(p.get_text(strip=True)) > 40]
        if paragraphs:
            article_text = "\n".join(paragraphs)

    return article_text[:8000]


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

    # Test API connection before processing all articles
    if hasattr(provider, 'test_connection'):
        if not provider.test_connection():
            log.error("LLM API connection test failed! Check API key and model name.")

    success_count = 0
    fail_count = 0

    for i, article in enumerate(to_summarize):
        title = article.get("title_original", "")
        description = article.get("description", "")
        url = article.get("url", "")
        category = article.get("category", "ai")

        log.info(f"  [{i+1}/{len(to_summarize)}] {title[:60]}...")

        # Fetch full article content from URL
        full_content = ""
        if url:
            log.info(f"    Fetching full article from {url[:80]}...")
            full_content = fetch_article_content(url)
            if full_content:
                log.info(f"    Got {len(full_content)} chars of article text")
            else:
                log.info(f"    Could not fetch, using RSS description")

        # Build the best possible content for the LLM
        if full_content and len(full_content) > len(description or ""):
            content = full_content
        else:
            content = description or ""

        result = provider.summarize(title, content, category)

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
