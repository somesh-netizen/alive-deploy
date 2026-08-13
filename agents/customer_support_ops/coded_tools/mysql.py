"""MySQL coded tool — real read-only query execution.

Reads connection details from sly_data["mysql"] (host, port, database, username,
password) — never from the LLM stream. Runs a single read-only (SELECT) query and
returns the rows. Connection work is offloaded to a thread so it doesn't block the
async event loop.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

try:
    from neuro_san.interfaces.coded_tool import CodedTool
except Exception:
    class CodedTool:  # type: ignore
        pass


def _run_query(cfg: Dict[str, Any], sql: str) -> Any:
    import pymysql

    conn = pymysql.connect(
        host=cfg.get("host", "127.0.0.1"),
        port=int(cfg.get("port") or 3306),
        user=cfg.get("username"),
        password=cfg.get("password"),
        database=cfg.get("database"),
        connect_timeout=5,
        read_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        return {"rows": rows, "row_count": len(rows)}
    finally:
        conn.close()


class MySqlTool(CodedTool):
    async def async_invoke(
        self, args: Dict[str, Any], sly_data: Dict[str, Any]
    ) -> Any:
        sql = (args.get("sql") or "").strip()
        cfg = (sly_data or {}).get("mysql") or {}

        if not cfg.get("host") or not cfg.get("username"):
            return {
                "error": "MySQL tool not configured — provide connection details "
                "(host, database, username, password) via the Configure dialog."
            }
        if not sql.lower().lstrip("(").startswith("select"):
            return {"error": "Only read-only SELECT queries are allowed.", "sql": sql}

        try:
            return await asyncio.to_thread(_run_query, cfg, sql)
        except Exception as exc:  # surface DB errors to the agent
            return {"error": f"MySQL query failed: {exc}", "sql": sql}
