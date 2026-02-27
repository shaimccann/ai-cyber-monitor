#!/usr/bin/env python3
"""RSS Discovery - Automatically find RSS feed URLs for a given website."""

import logging
import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "AI-Cyber-Monitor/1.0 (RSS Discovery; +https://github.com)",
}

# Common RSS paths to try
COMMON_RSS_PATHS = [
    "/feed",
    "/rss",
    "/feed.xml",
    "/rss.xml",
    "/atom.xml",
    "/blog/feed",
    "/blog/rss",
    "/blog/feed.xml",
    "/news/rss.xml",
    "/news/feed",
    "/feeds/posts/default",
    "/index.rss",
    "/feed/",
    "/rss/",
]


def check_url(url, timeout=10):
    """Check if a URL returns a valid RSS/Atom feed."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            return None
        content_type = resp.headers.get("content-type", "").lower()
        text = resp.text[:500].lower()

        # Check if it looks like a feed
        is_feed = (
            "xml" in content_type
            or "rss" in content_type
            or "atom" in content_type
            or "<rss" in text
            or "<feed" in text
            or "<rdf" in text
        )
        if is_feed:
            return url
    except requests.RequestException:
        pass
    return None


def discover_from_html(base_url, timeout=10):
    """Parse HTML page to find RSS/Atom link tags."""
    try:
        resp = requests.get(base_url, headers=HEADERS, timeout=timeout)
        if resp.status_code != 200:
            return []
    except requests.RequestException:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    feeds = []

    for link in soup.find_all("link", rel="alternate"):
        link_type = (link.get("type") or "").lower()
        if "rss" in link_type or "atom" in link_type or "xml" in link_type:
            href = link.get("href", "")
            if href:
                full_url = urljoin(base_url, href)
                feeds.append(full_url)

    return feeds


def discover_rss(site_url):
    """
    Try to discover RSS feed URL for a website.
    Returns: list of (url, method) tuples.
    """
    site_url = site_url.rstrip("/")
    results = []

    # Step 1: Check HTML <link> tags
    log.info(f"Checking HTML link tags for {site_url}...")
    html_feeds = discover_from_html(site_url)
    for feed_url in html_feeds:
        if check_url(feed_url):
            results.append((feed_url, "html_link"))
            log.info(f"  Found via HTML: {feed_url}")

    # Step 2: Try common paths
    log.info(f"Trying common RSS paths for {site_url}...")
    for path in COMMON_RSS_PATHS:
        url = site_url + path
        if any(r[0] == url for r in results):
            continue
        found = check_url(url)
        if found:
            results.append((found, "common_path"))
            log.info(f"  Found via path: {found}")

    # Summary
    if results:
        log.info(f"\nFound {len(results)} RSS feed(s) for {site_url}:")
        for url, method in results:
            log.info(f"  [{method}] {url}")
    else:
        log.info(f"\nNo RSS feed found for {site_url}")
        log.info("  Suggestion: use method 'scrape' for this source")

    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python discover_rss.py <website_url>")
        print("Example: python discover_rss.py https://openai.com")
        sys.exit(1)

    url = sys.argv[1]
    discover_rss(url)
