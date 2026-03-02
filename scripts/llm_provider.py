#!/usr/bin/env python3
"""LLM Provider Abstraction - Unified interface for Groq, Gemini, and Claude."""

import json
import logging
import os
import time
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

log = logging.getLogger(__name__)

SUMMARIZE_PROMPT = """Summarize this {category} news article. Write the summary and details in the SAME LANGUAGE as the article. Respond with ONLY valid JSON, no markdown.

{{
  "summary": "2-3 sentences in the article's language. Rephrase the key facts differently from the title.",
  "details": "3-5 sentences in the article's language expanding on impact and context.",
  "category": "ai or cyber"
}}

Title: {title}
Content: {content}"""

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

    def test_connection(self):
        """Quick test to verify Gemini API works. Returns (ok, error_message)."""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents="Reply with exactly: OK",
            )
            msg = f"model={self.model_name}, response={response.text[:50]}"
            log.info(f"Gemini API test OK: {msg}")
            return True, msg
        except Exception as e:
            msg = f"model={self.model_name}, error={type(e).__name__}: {e}"
            log.error(f"Gemini API test FAILED: {msg}")
            return False, msg

    def summarize(self, title, content, category):
        """Summarize an article with retry on failure."""
        last_error = None
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
                raw_text = response.text
                log.info(f"Gemini raw response ({len(raw_text)} chars): {raw_text[:150]}...")
                result = _parse_llm_json(raw_text)
                # Validate: summary should not be identical to title
                if result.get("summary", "").strip() == title.strip():
                    log.warning("Gemini returned title as summary, retrying...")
                    continue
                return result
            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {e}"
                log.warning(f"Gemini attempt {attempt+1} JSON parse failed: {e}")
                if 'raw_text' in locals():
                    log.warning(f"Raw text was: {raw_text[:300]}")
                continue
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                log.error(f"Gemini attempt {attempt+1} API error: {type(e).__name__}: {e}")
                continue

        # Final fallback
        log.warning(f"Gemini failed after retries for: {title[:60]} | Last error: {last_error}")
        return {
            "summary": "",
            "details": "",
            "category": category,
            "_error": last_error or "unknown",
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


class GroqProvider:
    """Groq API provider using OpenAI-compatible endpoint."""

    def __init__(self, config):
        from openai import OpenAI

        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable not set")

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        self.model = config["llm"]["groq"]["model"]
        self.max_rpm = config["llm"]["groq"]["max_rpm"]
        self._last_call = 0

    def _rate_limit(self):
        """Enforce minimum 3s between calls to stay under free tier limits."""
        min_interval = max(3.0, 60.0 / self.max_rpm)
        elapsed = time.time() - self._last_call
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_call = time.time()

    def _is_rate_limit_error(self, e):
        """Check if an exception is a 429 rate limit error."""
        return "429" in str(e) or "rate" in str(e).lower()

    def test_connection(self):
        """Quick test to verify Groq API works. Returns (ok, error_message)."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                max_tokens=10,
            )
            text = response.choices[0].message.content
            msg = f"model={self.model}, response={text[:50]}"
            log.info(f"Groq API test OK: {msg}")
            return True, msg
        except Exception as e:
            msg = f"model={self.model}, error={type(e).__name__}: {e}"
            log.error(f"Groq API test FAILED: {msg}")
            return False, msg

    def summarize(self, title, content, category):
        """Summarize an article with retry and exponential backoff on 429."""
        last_error = None
        for attempt in range(3):
            self._rate_limit()
            prompt = SUMMARIZE_PROMPT.format(
                title=title, content=content[:2000], category=category
            )
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500,
                    temperature=0.3,
                )
                raw_text = response.choices[0].message.content
                log.info(f"Groq raw response ({len(raw_text)} chars): {raw_text[:150]}...")
                result = _parse_llm_json(raw_text)
                if result.get("summary", "").strip() == title.strip():
                    log.warning("Groq returned title as summary, retrying...")
                    continue
                return result
            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {e}"
                log.warning(f"Groq attempt {attempt+1} JSON parse failed: {e}")
                if 'raw_text' in locals():
                    log.warning(f"Raw text was: {raw_text[:300]}")
                continue
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                if self._is_rate_limit_error(e):
                    wait = 10 * (2 ** attempt)
                    log.warning(f"Groq 429 rate limit on attempt {attempt+1}, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    log.error(f"Groq attempt {attempt+1} API error: {type(e).__name__}: {e}")
                continue

        log.warning(f"Groq failed after retries for: {title[:60]} | Last error: {last_error}")
        return {
            "summary": "",
            "details": "",
            "category": category,
            "_error": last_error or "unknown",
        }

    def check_duplicate(self, title_a, title_b):
        """Ask LLM if two titles refer to the same story."""
        self._rate_limit()
        prompt = DEDUP_PROMPT.format(title_a=title_a, title_b=title_b)
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
            )
            return "same" in response.choices[0].message.content.strip().lower()
        except Exception as e:
            log.warning(f"Groq dedup check failed: {e}")
            return False


def get_provider(config=None):
    """Factory function - returns the configured LLM provider."""
    if config is None:
        config = load_config()

    provider_name = os.environ.get("LLM_PROVIDER", config["llm"]["provider"])

    if provider_name == "groq":
        return GroqProvider(config)
    elif provider_name == "gemini":
        return GeminiProvider(config)
    elif provider_name == "claude":
        return ClaudeProvider(config)
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}")
