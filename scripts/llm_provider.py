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

SUMMARIZE_PROMPT = """You are a cybersecurity and AI news analyst. Based on the title and any available content, produce an analysis.

Category hint: [{category}].

RULES:
1. The "summary" MUST be different from the title — rephrase and add context.
2. The "details" MUST be much longer than the summary with structured sections.
3. If the article content is short, use your expert knowledge to expand on the topic — explain the significance, potential impact, and relevant background.
4. NEVER just repeat the title or content verbatim.

Provide your response in this JSON format ONLY:
{{
  "summary": "A 2-3 sentence overview in English. Rephrase the key facts — what happened, who is involved, and why it matters. Must NOT be identical to the title.",
  "details": "A comprehensive structured analysis in English using your cybersecurity/AI expertise. Use labeled sections with this format — each header on its own line followed by a colon:\\n\\nFor CYBER articles use relevant sections from:\\nThe Vulnerability: [CVE IDs, severity, affected products, nature of the flaw]\\nActive Exploitation: [threat actors, scope, what was compromised]\\nAttacker Techniques: [TTPs, tools, malware, attack vectors]\\nImpact: [affected organizations, data exposed, financial/operational damage]\\nOfficial Response: [patches, advisories, government statements]\\nRecommendations: [specific protection steps for organizations]\\n\\nFor AI articles use relevant sections from:\\nKey Innovation: [what is new, how it differs from prior work]\\nTechnical Details: [architecture, methodology, benchmarks]\\nIndustry Impact: [market implications, competitive landscape]\\nExpert Reactions: [analyst opinions, community response]\\nPractical Implications: [what this means for developers/businesses/users]\\n\\nInclude 2-4 relevant sections. Each section should be 2-4 sentences. If article content is limited, use your domain expertise to provide informed analysis.",
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


def _parse_llm_json(text):
    """Extract and parse JSON from LLM response."""
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    return json.loads(text)


class GeminiProvider:
    """Google Gemini API provider using google-genai SDK."""

    def __init__(self, config):
        from google import genai

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        self.client = genai.Client(api_key=api_key)
        self.model_name = config["llm"]["gemini"]["model"]
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
        """Summarize an article with retry on failure."""
        for attempt in range(2):
            self._rate_limit()
            prompt = SUMMARIZE_PROMPT.format(
                title=title, content=content[:6000], category=category
            )
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )
                result = _parse_llm_json(response.text)
                # Validate: summary should not be identical to title
                if result.get("summary", "").strip() == title.strip():
                    log.warning("Gemini returned title as summary, retrying...")
                    continue
                return result
            except (json.JSONDecodeError, Exception) as e:
                log.warning(f"Gemini summarization attempt {attempt+1} failed: {e}")
                continue

        # Final fallback: use description as summary, not title
        log.warning(f"Gemini failed after retries for: {title[:60]}")
        desc = content[:300] if content else title
        return {
            "summary": desc,
            "details": "",
            "category": category,
            "title_he": title,
        }

    def check_duplicate(self, title_a, title_b):
        """Ask LLM if two titles refer to the same story."""
        self._rate_limit()
        prompt = DEDUP_PROMPT.format(title_a=title_a, title_b=title_b)
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
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
        for attempt in range(2):
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
                text = message.content[0].text
                result = _parse_llm_json(text)
                if result.get("summary", "").strip() == title.strip():
                    log.warning("Claude returned title as summary, retrying...")
                    continue
                return result
            except (json.JSONDecodeError, Exception) as e:
                log.warning(f"Claude summarization attempt {attempt+1} failed: {e}")
                continue

        log.warning(f"Claude failed after retries for: {title[:60]}")
        desc = content[:300] if content else title
        return {
            "summary": desc,
            "details": "",
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
