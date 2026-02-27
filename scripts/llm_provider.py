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

Provide your response in this JSON format ONLY:
{{
  "summary": "A 2-3 sentence summary in English. Cover the key facts: what happened, who is affected, and why it matters.",
  "details": "A structured detailed analysis in English using labeled sections. Use this EXACT format with section labels followed by colons:\\n\\nThe Vulnerability: [description of the vulnerability, CVE, severity score, affected products]\\n\\nActive Exploitation: [who is exploiting it, how long, what they achieved]\\n\\nAttacker Techniques: [specific TTPs, tools, methods used]\\n\\nOfficial Response: [vendor patches, CISA directives, government advisories]\\n\\nRecommendations: [what organizations should do to protect themselves]\\n\\nFor AI articles use these sections instead:\\n\\nKey Innovation: [what is new]\\n\\nTechnical Details: [how it works]\\n\\nIndustry Impact: [who is affected, market implications]\\n\\nExpert Reactions: [what analysts and experts say]\\n\\nPractical Implications: [what this means for users/organizations]\\n\\nOnly include sections that are relevant based on the article content. Each section should be 2-4 sentences.",
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
            title=title, content=content[:3000], category=category
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
            title=title, content=content[:3000], category=category
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
