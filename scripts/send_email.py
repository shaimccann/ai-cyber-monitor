#!/usr/bin/env python3
"""Email Report - Sends daily summary via Gmail SMTP."""

import json
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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


def build_email_html(articles, config):
    """Build LTR English HTML email content with logo."""
    dashboard_url = config["email"].get("dashboard_url", "")
    max_articles = config["email"]["max_articles"]

    # Sort by date descending and limit
    sorted_articles = sorted(
        articles,
        key=lambda a: a.get("published", ""),
        reverse=True,
    )[:max_articles]

    ai_articles = [a for a in sorted_articles if a.get("category") == "ai"]
    cyber_articles = [a for a in sorted_articles if a.get("category") == "cyber"]

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def article_row(article):
        title = article.get("title_he", article.get("title_original", ""))
        # Use description as summary if summary_he is same as title
        summary = article.get("summary_he", "")
        if not summary or summary == title:
            summary = article.get("description", "")
        # Truncate summary to ~160 chars
        if len(summary) > 160:
            summary = summary[:160].rsplit(" ", 1)[0] + "..."
        url = article.get("url", "#")
        source = article.get("source_name", "")
        cat = article.get("category", "ai")
        badge_color = "#8b5cf6" if cat == "ai" else "#059669"
        badge_text = "🤖 AI" if cat == "ai" else "🔒 Cyber"

        return f"""
        <tr>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0; text-align: left;">
                <span style="display: inline-block; background: {badge_color}20; color: {badge_color};
                             padding: 2px 8px; border-radius: 12px; font-size: 12px; margin-bottom: 4px;">
                    {badge_text}
                </span>
                <div style="font-size: 15px; font-weight: 600; margin: 4px 0;">
                    <a href="{url}" style="color: #1a1a2e; text-decoration: none;">{title}</a>
                </div>
                <div style="font-size: 13px; color: #555; line-height: 1.5;">{summary}</div>
                <div style="font-size: 12px; color: #888; margin-top: 4px;">{source}</div>
            </td>
        </tr>"""

    ai_rows = "".join(article_row(a) for a in ai_articles) if ai_articles else ""
    cyber_rows = "".join(article_row(a) for a in cyber_articles) if cyber_articles else ""

    dashboard_link = ""
    if dashboard_url:
        dashboard_link = f"""
        <div style="text-align: center; margin: 24px 0;">
            <a href="{dashboard_url}" style="display: inline-block; background: #2563eb; color: #fff;
                     padding: 12px 24px; border-radius: 8px; text-decoration: none; font-size: 14px;">
                View all updates on Dashboard
            </a>
        </div>"""

    # Logo URL on GitHub Pages
    logo_url = dashboard_url.rstrip("/") + "/logo.svg" if dashboard_url else ""
    logo_html = ""
    if logo_url:
        logo_html = f"""
            <img src="{logo_url}" alt="Shai·eld" width="240" height="72"
                 style="display: block; margin: 0; opacity: 0.9;">"""

    html = f"""<!DOCTYPE html>
<html lang="en" dir="ltr">
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; direction: ltr; background: #f5f7fa; margin: 0; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background: #fff; border-radius: 12px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden;">

        <!-- Header -->
        <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #fff;
                     padding: 24px;">
            <table style="width: 100%; border: none; border-collapse: collapse;">
                <tr>
                    <td style="text-align: left; vertical-align: middle; border: none; padding: 0;">
                        <h1 style="margin: 0; font-size: 22px; color: #fff;">AI & Cyber Daily Monitor</h1>
                        <p style="margin: 4px 0 0; opacity: 0.8; font-size: 14px; color: #fff;">Daily digest — {today_str}</p>
                    </td>
                    <td style="text-align: right; vertical-align: middle; border: none; padding: 0; width: 170px;">
                        {logo_html}
                    </td>
                </tr>
            </table>
        </div>

        {dashboard_link}

        <!-- Stats -->
        <div style="padding: 16px 24px; background: #f8f9fa; text-align: center; font-size: 14px; color: #555;">
            {len(sorted_articles)} articles | {len(ai_articles)} AI | {len(cyber_articles)} Cyber
        </div>

        <!-- AI Section -->
        {"" if not ai_articles else f'''
        <div style="padding: 16px 24px 8px;">
            <h2 style="font-size: 18px; color: #8b5cf6; margin: 0;">🤖 AI</h2>
        </div>
        <table style="width: 100%; border-collapse: collapse;">{ai_rows}</table>
        '''}

        <!-- Cyber Section -->
        {"" if not cyber_articles else f'''
        <div style="padding: 16px 24px 8px;">
            <h2 style="font-size: 18px; color: #059669; margin: 0;">🔒 Cyber</h2>
        </div>
        <table style="width: 100%; border-collapse: collapse;">{cyber_rows}</table>
        '''}

        <!-- Footer -->
        <div style="padding: 16px 24px; text-align: center; font-size: 12px; color: #888;
                     border-top: 1px solid #e2e8f0;">
            Automated by AI & Cyber Daily Monitor
        </div>
    </div>
</body>
</html>"""

    return html


def load_recipients():
    """Load additional recipients from config/recipients.json."""
    recipients_file = CONFIG_DIR / "recipients.json"
    if not recipients_file.exists():
        return []
    try:
        with open(recipients_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [
            r["email"]
            for r in data.get("recipients", [])
            if r.get("enabled", True) and r.get("email")
        ]
    except Exception as e:
        log.warning(f"Could not load recipients.json: {e}")
        return []


def send_email():
    """Send daily email report."""
    config = load_config()

    if not config["email"].get("enabled", True):
        log.info("Email sending is disabled in config")
        return

    email_address = os.environ.get("EMAIL_ADDRESS", "")
    email_password = os.environ.get("EMAIL_PASSWORD", "")

    if not email_address or not email_password:
        log.error("EMAIL_ADDRESS or EMAIL_PASSWORD not set in environment")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    articles_file = ARTICLES_DIR / f"{today}.json"

    if not articles_file.exists():
        log.error(f"No articles file for {today}")
        return

    with open(articles_file, "r", encoding="utf-8") as f:
        articles = json.load(f)

    if not articles:
        log.info("No articles to send")
        return

    # Build recipient list: primary + additional from recipients.json
    all_recipients = [email_address]
    extra = load_recipients()
    for addr in extra:
        if addr not in all_recipients:
            all_recipients.append(addr)

    log.info(f"Sending to {len(all_recipients)} recipients: {', '.join(all_recipients)}")

    # Build email
    subject_prefix = config["email"]["subject_prefix"]
    subject = f"{subject_prefix} — {today}"

    html_content = build_email_html(articles, config)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_address
    msg["To"] = ", ".join(all_recipients)

    msg.attach(MIMEText(html_content, "html", "utf-8"))

    # Send via Gmail SMTP
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email_address, email_password)
            server.sendmail(email_address, all_recipients, msg.as_string())
        log.info(f"Email sent successfully to {len(all_recipients)} recipients")
    except Exception as e:
        log.error(f"Failed to send email: {e}")


if __name__ == "__main__":
    send_email()
