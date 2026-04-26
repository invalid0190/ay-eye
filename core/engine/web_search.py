"""
Brave Search API integration for Ay-Eye.
Provides web search capabilities so the AI can look up information before responding.
"""
import os
import requests
from core.utils.logger import logger
from dotenv import load_dotenv

load_dotenv()

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class WebSearch:
    def __init__(self):
        self.api_key = os.getenv("BRAVE_API_KEY")
        self.enabled = bool(self.api_key)
        if self.enabled:
            logger.logger.info("WebSearch: Brave Search API enabled")
        else:
            logger.logger.warning("WebSearch: No BRAVE_API_KEY found, web search disabled")

    def search(self, query, count=5):
        """Search the web and return a condensed summary of results."""
        if not self.enabled:
            return None

        try:
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.api_key
            }
            params = {
                "q": query,
                "count": count,
                "text_decorations": False,
                "search_lang": "en"
            }

            response = requests.get(BRAVE_SEARCH_URL, headers=headers, params=params, timeout=8)
            response.raise_for_status()
            data = response.json()

            results = []
            web_results = data.get("web", {}).get("results", [])

            for r in web_results[:count]:
                title = r.get("title", "")
                description = r.get("description", "")
                url = r.get("url", "")
                results.append(f"- {title}: {description} ({url})")

            if results:
                summary = "\n".join(results)
                logger.log_event("WEB_SEARCH_COMPLETED", {"query": query, "results": len(results)})
                return summary

            return None

        except Exception as e:
            logger.logger.error(f"WebSearch error: {e}")
            return None

    def should_search(self, voice_text):
        """Determine if a voice command would benefit from a web search."""
        if not self.enabled or not voice_text:
            return False

        text_lower = voice_text.lower()

        # EXCLUSIONS: These are screen/vision questions — use the screenshot, NOT web search
        vision_phrases = [
            "on my screen", "on the screen", "on screen",
            "looking at", "look at", "see on",
            "do you see", "can you see", "what you see",
            "in front of me", "my desktop", "my monitor",
            "this window", "this app", "this page",
            "right now", "currently", "showing",
            "describe my", "describe the screen", "describe what",
            "read this", "read the", "read my",
            "click", "open", "close", "type", "scroll",
            "move", "switch", "minimize", "maximize",
            "write a", "write me", "compose", "draft",
        ]

        for phrase in vision_phrases:
            if phrase in text_lower:
                return False

        # Knowledge-seeking patterns (only if NOT a vision/action query)
        search_triggers = [
            "what is", "what are", "who is", "who are",
            "how to", "how do", "how does", "how can",
            "why is", "why do", "why does",
            "when did", "when was", "when is",
            "where is", "where are", "where do",
            "tell me about", "explain", "define",
            "search for", "look up", "find out",
            "latest", "news about", "current",
            "best way to", "tutorial", "guide",
            "meaning of", "difference between",
        ]

        for trigger in search_triggers:
            if trigger in text_lower:
                return True

        # Question mark at end (but not screen questions)
        if text_lower.strip().endswith("?"):
            return True

        return False


web_search = WebSearch()
