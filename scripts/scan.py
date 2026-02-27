#!/usr/bin/env python3
"""RSS Feed Scanner - Fetches articles from configured sources."""

import json
import os
import sys
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

# Setup paths
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

HEADERS = {
    "User-Agent": "AI-Cyber-Monitor/1.0 (RSS Reader; +https://github.com)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def load_config():
    with open(CONFIG_DIR / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources():
    with open(CONFIG_DIR / "sources.json", "r", encoding="utf-8") as f:
        return json.load(f)["sources"]


def parse_date(date_str):
    """Parse a date string into a timezone-aware datetime."""
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def generate_article_id(url, title, date_str):
    """Generate a unique ID for an article."""
    raw = f"{url}|{title}|{date_str}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def fetch_rss(source, config):
    """Fetch articles from an RSS feed."""
    rss_url = source["rss_url"]
    timeout = config["scan"]["request_timeout"]
    max_articles = config["scan"]["max_articles_per_source"]
    max_age = timedelta(hours=config["scan"]["max_age_hours"])
    now = datetime.now(timezone.utc)

    log.info(f"  Fetching RSS: {source['name']} ({rss_url})")

    try:
        resp = requests.get(rss_url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning(f"  Failed to fetch {source['name']}: {e}")
        return []

    feed = feedparser.parse(resp.content)
    articles = []

    for entry in feed.entries[:max_articles]:
        published = None
        for date_field in ("published", "updated", "created"):
            if hasattr(entry, date_field) and getattr(entry, date_field):
                published = parse_date(getattr(entry, date_field))
                if published:
                    break

        # Skip articles older than max_age
        if published and (now - published) > max_age:
            continue

        # If no date found, include it (might be recent)
        url = entry.get("link", "")
        title = entry.get("title", "No Title")
        description = ""
        if hasattr(entry, "summary"):
            description = BeautifulSoup(entry.summary, "html.parser").get_text(strip=True)
        elif hasattr(entry, "description"):
            description = BeautifulSoup(entry.description, "html.parser").get_text(strip=True)

        article = {
            "id": generate_article_id(url, title, str(published)),
            "title_original": title,
            "url": url,
            "description": description[:1000],
            "source_name": source["name"],
            "source_url": source["url"],
            "category": source["category"],
            "published": published.isoformat() if published else now.isoformat(),
            "fetched_at": now.isoformat(),
        }
        articles.append(article)

    log.info(f"  Found {len(articles)} recent articles from {source['name']}")
    return articles


def scrape_site(source, config):
    """Basic scraping for sites without RSS (Anthropic, Meta AI)."""
    timeout = config["scan"]["request_timeout"]
    max_articles = config["scan"]["max_articles_per_source"]
    now = datetime.now(timezone.utc)

    log.info(f"  Scraping: {source['name']} ({source['url']})")

    try:
        resp = requests.get(source["url"], headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning(f"  Failed to scrape {source['name']}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = []

    # Look for article-like elements
    selectors = [
        "article a[href]",
        "a.post-link",
        ".blog-post a[href]",
        ".card a[href]",
        "h2 a[href]",
        "h3 a[href]",
    ]

    seen_urls = set()
    for selector in selectors:
        for link in soup.select(selector):
            href = link.get("href", "")
            if not href or href in seen_urls:
                continue

            # Make URL absolute
            if href.startswith("/"):
                href = source["url"].rstrip("/") + href

            # Skip non-article links
            if not href.startswith("http"):
                continue

            seen_urls.add(href)
            title = link.get_text(strip=True)
            if not title or len(title) < 10:
                # Try parent for title
                parent = link.find_parent(["h2", "h3", "div"])
                if parent:
                    title = parent.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            article = {
                "id": generate_article_id(href, title, now.isoformat()),
                "title_original": title[:200],
                "url": href,
                "description": "",
                "source_name": source["name"],
                "source_url": source["url"],
                "category": source["category"],
                "published": now.isoformat(),
                "fetched_at": now.isoformat(),
            }
            articles.append(article)

            if len(articles) >= max_articles:
                break
        if len(articles) >= max_articles:
            break

    log.info(f"  Found {len(articles)} articles from {source['name']} (scraping)")
    return articles


def scan_all_sources():
    """Main scan function - fetches from all enabled sources."""
    config = load_config()
    sources = load_sources()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_file = ARTICLES_DIR / f"{today}.json"

    # Load existing articles for today if file exists
    existing_articles = []
    if output_file.exists():
        with open(output_file, "r", encoding="utf-8") as f:
            existing_articles = json.load(f)
        log.info(f"Loaded {len(existing_articles)} existing articles for {today}")

    existing_urls = {a["url"] for a in existing_articles}

    all_articles = list(existing_articles)
    new_count = 0

    enabled_sources = [s for s in sources if s.get("enabled", True)]
    log.info(f"Scanning {len(enabled_sources)} enabled sources...")

    for source in enabled_sources:
        method = source.get("method", "rss")

        if method == "rss" and source.get("rss_url"):
            articles = fetch_rss(source, config)
        elif method == "scrape":
            articles = scrape_site(source, config)
        else:
            log.warning(f"  Skipping {source['name']}: no RSS URL and method is '{method}'")
            continue

        for article in articles:
            if article["url"] not in existing_urls:
                all_articles.append(article)
                existing_urls.add(article["url"])
                new_count += 1

    # Save results
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    log.info(f"Scan complete: {new_count} new articles, {len(all_articles)} total for {today}")
    log.info(f"Saved to {output_file}")

    return all_articles


if __name__ == "__main__":
    scan_all_sources()
