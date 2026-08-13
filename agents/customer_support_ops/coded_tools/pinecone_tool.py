"""
Coded tool.

`args["query"]` is the natural language or vector search query.

Connection details are read from `sly_data["pinecone_connector"]`
(api_key, host, index_name, namespace) — supplied at runtime
via the Configure dialog, never through the LLM.

Supports both:
- Pinecone Cloud (API key + host)
- Self-hosted/Local Pinecone-compatible server (host)
"""

from __future__ import annotations

from typing import Any, Dict

try:
    from neuro_san.interfaces.coded_tool import CodedTool
except Exception:

    class CodedTool:  # type: ignore
        pass


def _search(cfg: Dict[str, Any], query: str, top_k: int) -> Any:
    from pinecone import Pinecone

    api_key = cfg.get("api_key") or ""
    host = cfg.get("host")
    namespace = cfg.get("namespace") or ""

    pc = Pinecone(api_key=api_key)

    index = pc.Index(host=host)

    result = index.search(
        namespace=namespace,
        query={
            "inputs": {"text": query},
            "top_k": top_k,
        },
        fields=["*"],
    )

    return result


class PineconeTool(CodedTool):
    async def async_invoke(
        self,
        args: Dict[str, Any],
        sly_data: Dict[str, Any],
    ) -> Any:

        query = (args.get("query") or "").strip()
        top_k = int(args.get("top_k") or 5)

        cfg = (sly_data or {}).get("pinecone") or {}

        if not cfg.get("host"):
            return {
                "error": (
                    "Pinecone not configured. "
                    "Set host (and API key if required) via Configure."
                )
            }

        if not query:
            return {"error": "Missing 'query' argument."}

        try:
            import asyncio

            return await asyncio.to_thread(
                _search,
                cfg,
                query,
                top_k,
            )

        except Exception as exc:
            return {
                "error": f"Pinecone search failed: {exc}",
                "query": query,
            }
