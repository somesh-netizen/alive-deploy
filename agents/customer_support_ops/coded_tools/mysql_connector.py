"""
Coded tool.

`args["sql"]` is the query the agent wants to run.

Connection details are read from `sly_data["mysql_connector"]`
(host, port, database, username, password) — supplied at runtime
via the Configure dialog, never through the LLM.
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

        return {
            "rows": rows,
            "row_count": len(rows),
        }

    finally:
        conn.close()


class MySqlConnector(CodedTool):
    async def async_invoke(
        self,
        args: Dict[str, Any],
        sly_data: Dict[str, Any],
    ) -> Any:
        sql = (args.get("sql") or "").strip()
        cfg = (sly_data or {}).get("mysql_connector") or {}

        if not cfg.get("host") or not cfg.get("username"):
            return {
                "error": (
                    "MySQL not configured - set host, database, "
                    "username, password via the Configure dialog."
                )
            }

        if not sql.lower().lstrip("(").startswith("select"):
            return {
                "error": "Only read-only SELECT queries are allowed.",
                "sql": sql,
            }

        try:
            return await asyncio.to_thread(_run_query, cfg, sql)
        except Exception as exc:
            return {
                "error": f"MySQL query failed: {exc}",
                "sql": sql,
            }
