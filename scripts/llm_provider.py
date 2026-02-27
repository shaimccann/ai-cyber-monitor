#!/usr/bin/env python3
"""LLM Provider Abstraction - Unified interface for Gemini and Claude."""

import json
import logging
import os
import time
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

log = logging.getLogger(__name__)

SUMMARIZE_PROMPT = """You are a cybersecurity and AI news analyst. Analyze the following article thoroughly.
Category: [{category}].

IMPORTANT: The "summary" and "details" fields MUST contain DIFFERENT content. The summary is a brief overview. The details is a comprehensive structured analysis with much more information.

Provide your response in this JSON format ONLY:
{{
  "summary": "A concise 2-3 sentence overview in English. State what happened, who is involved, and why it matters. Do NOT repeat the title.",
  "details": "A comprehensive structured analysis in English. This must be MUCH longer and more detailed than the summary. Use labeled sections with this EXACT format — each section header on its own line followed by a colon:\\n\\nFor CYBER articles, use relevant sections from:\\n\\nThe Vulnerability: [CVE IDs, severity scores, affected products and versions, nature of the flaw]\\n\\nActive Exploitation: [threat actors involved, duration, scope of attacks, what was compromised]\\n\\nAttacker Techniques: [specific TTPs, tools, malware families, attack vectors]\\n\\nImpact: [number of affected organizations, data exposed, financial damage]\\n\\nOfficial Response: [vendor patches, CISA advisories, government statements, timelines]\\n\\nRecommendations: [specific steps organizations should take to protect themselves]\\n\\nFor AI articles, use relevant sections from:\\n\\nKey Innovation: [what is genuinely new, how it differs from prior work]\\n\\nTechnical Details: [architecture, methodology, benchmarks, performance metrics]\\n\\nIndustry Impact: [market implications, competitive landscape, affected sectors]\\n\\nExpert Reactions: [analyst opinions, community response, concerns raised]\\n\\nPractical Implications: [what this means for developers, businesses, end users]\\n\\nOnly include sections relevant to the article. Each section should be 2-4 sentences with specific facts from the article.",
  "category": "ai" or "cyber",
  "title_he": "Keep the original English title as-is"
}}

Title: {title}
Content:
{content}

Respond with valid JSON only, no markdown code blocks."""

DEDUP_PROMPT = """בדוק אם שתי הכותרות הבאות מדברות על אותו נושא:
כותרת 1: {title_a}
כותרת 2: {title_b}

ענה רק: "same" או "different"
"""


def load_config():
    with open(CONFIG_DIR / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class GeminiProvider:
    """Google Gemini API provider."""

    def __init__(self, config):
        import google.generativeai as genai

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        genai.configure(api_key=api_key)
        model_name = config["llm"]["gemini"]["model"]
        self.model = genai.GenerativeModel(model_name)
        self.max_rpm = config["llm"]["gemini"]["max_rpm"]
        self._last_call = 0

    def _rate_limit(self):
        """Enforce rate limiting."""
        min_interval = 60.0 / self.max_rpm
        elapsed = time.time() - self._last_call
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_call = time.time()

    def summarize(self, title, content, category):
        """Summarize and translate an article to Hebrew."""
        self._rate_limit()
        prompt = SUMMARIZE_PROMPT.format(
            title=title, content=content[:6000], category=category
        )
        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            # Extract JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            return json.loads(text)
        except (json.JSONDecodeError, Exception) as e:
            log.warning(f"Gemini summarization failed: {e}")
            return {
                "summary": title[:100],
                "details": content[:500],
                "category": category,
                "title_he": title,
            }

    def check_duplicate(self, title_a, title_b):
        """Ask LLM if two titles refer to the same story."""
        self._rate_limit()
        prompt = DEDUP_PROMPT.format(title_a=title_a, title_b=title_b)
        try:
            response = self.model.generate_content(prompt)
            return "same" in response.text.strip().lower()
        except Exception as e:
            log.warning(f"Gemini dedup check failed: {e}")
            return False


class ClaudeProvider:
    """Anthropic Claude API provider (future use)."""

    def __init__(self, config):
        try:
            import anthropic
        except ImportError:
            raise ImportError("Install anthropic package: pip install anthropic")

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = config["llm"]["claude"]["model"]
        self.max_rpm = config["llm"]["claude"]["max_rpm"]
        self._last_call = 0

    def _rate_limit(self):
        min_interval = 60.0 / self.max_rpm
        elapsed = time.time() - self._last_call
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_call = time.time()

    def summarize(self, title, content, category):
        self._rate_limit()
        prompt = SUMMARIZE_PROMPT.format(
            title=title, content=content[:6000], category=category
        )
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = message.content[0].text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            return json.loads(text)
        except (json.JSONDecodeError, Exception) as e:
            log.warning(f"Claude summarization failed: {e}")
            return {
                "summary": title[:100],
                "details": content[:500],
                "category": category,
                "title_he": title,
            }

    def check_duplicate(self, title_a, title_b):
        self._rate_limit()
        prompt = DEDUP_PROMPT.format(title_a=title_a, title_b=title_b)
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}],
            )
            return "same" in message.content[0].text.strip().lower()
        except Exception as e:
            log.warning(f"Claude dedup check failed: {e}")
            return False


def get_provider(config=None):
    """Factory function - returns the configured LLM provider."""
    if config is None:
        config = load_config()

    provider_name = os.environ.get("LLM_PROVIDER", config["llm"]["provider"])

    if provider_name == "gemini":
        return GeminiProvider(config)
    elif provider_name == "claude":
        return ClaudeProvider(config)
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}")
