"""Tavily web-search coded tool.

Reads the API key from sly_data["tavily"]["api_key"] (never from the LLM stream).
Safe stub for now; real search execution arrives incrementally.
"""

from __future__ import annotations

from typing import Any, Dict

try:
    from neuro_san.interfaces.coded_tool import CodedTool
except Exception:
    class CodedTool:  # type: ignore
        pass


class TavilySearch(CodedTool):
    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        query = args.get("query", "")
        cfg = (sly_data or {}).get("tavily")
        if not cfg or not cfg.get("api_key"):
            return {
                "error": "Web Search (Tavily) not configured — provide "
                "sly_data['tavily']['api_key'].",
                "query": query,
            }
        return {
            "note": "Tavily execution not yet implemented in the ALIVE runtime.",
            "query": query,
        }
