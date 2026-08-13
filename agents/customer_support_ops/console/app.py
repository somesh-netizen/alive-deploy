"""Console for the exported ALIVE network bundle.

Serves the bundled Talk UI (identical React app: React-Flow graph, live trace,
Chat/Agents/Logs), the ALIVE-compatible API the UI calls, LLM-key config, and
manages the neuro-san runtime subprocess (streaming chat is proxied to it).
"""
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pyhocon import ConfigFactory
from pyhocon.config_tree import ConfigTree

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
STATIC = APP_DIR / "static"
DATA = Path(os.getenv("ALIVE_DATA_DIR", "/data"))
DATA.mkdir(parents=True, exist_ok=True)
ENV_FILE = DATA / ".env"
LLM_FILE = DATA / "llm.json"
DB_FILE = DATA / "sessions.db"
RUNTIME_PORT = 8099
NETWORK = os.getenv("ALIVE_NETWORK", "")
_LOG_TYPES = {"AGENT", "AI", "AGENT_TOOL_RESULT", "AGENT_PROGRESS"}

app = FastAPI()
_proc = {"p": None}


def load_env_file() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if v.strip():
                env[k.strip()] = v.strip()
    return env


def write_env_file(d: dict) -> None:
    ENV_FILE.write_text("\n".join(f"{k}={v}" for k, v in d.items() if v) + "\n")


def stop_runtime() -> None:
    p = _proc.get("p")
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(5)
        except Exception:
            p.kill()
    _proc["p"] = None


def start_runtime() -> None:
    stop_runtime()
    env = {**os.environ, **load_env_file()}
    env.update({
        "AGENT_MANIFEST_FILE": str(ROOT / "registries" / "manifest.hocon"),
        "AGENT_TOOL_PATH": str(ROOT / "coded_tools"),
        "AGENT_TOOLBOX_INFO_FILE": str(ROOT / "config" / "toolbox_info.hocon"),
        "PYTHONPATH": f"{ROOT}:{ROOT / 'coded_tools'}:" + env.get("PYTHONPATH", ""),
    })
    _proc["p"] = subprocess.Popen(
        [sys.executable, "-m", "neuro_san.service.main_loop.server_main_loop", "--http_port", str(RUNTIME_PORT)],
        cwd=str(ROOT), env=env,
    )


def apply_llm() -> None:
    """Write config/llm_config.hocon from the persisted provider+model choice."""
    if not LLM_FILE.exists():
        return
    try:
        llm = json.loads(LLM_FILE.read_text())
    except Exception:
        return
    if llm.get("class") and llm.get("model_name"):
        (ROOT / "config" / "llm_config.hocon").write_text(json.dumps({"llm_config": llm}, indent=4))


def _db() -> sqlite3.Connection:
    c = sqlite3.connect(DB_FILE)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, network TEXT, chat_context TEXT, title TEXT, updated REAL)")
        c.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT, role TEXT, text TEXT, ts REAL)")
        try:  # migrate older bundle DBs that predate the title column
            c.execute("ALTER TABLE sessions ADD COLUMN title TEXT")
        except Exception:
            pass


def _title_from(text: str) -> str:
    """A short chat name from the first user message (ChatGPT-style)."""
    t = " ".join((text or "").strip().split()[:6])
    return (t[:40] + "…") if len(t) > 40 else (t or "New chat")


def _save_message(session: str, role: str, text: str) -> None:
    now = time.time()
    with _db() as c:
        c.execute("INSERT INTO messages (session, role, text, ts) VALUES (?,?,?,?)", (session, role, text, now))
        # Ensure a session row exists and bump its recency.
        c.execute(
            "INSERT INTO sessions (id, network, updated) VALUES (?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET updated=excluded.updated",
            (session, NETWORK, now),
        )
        # Name the chat from its first user message (only if not named yet).
        if role == "user":
            c.execute(
                "UPDATE sessions SET title=? WHERE id=? AND (title IS NULL OR title='')",
                (_title_from(text), session),
            )


def _load_context(session: str):
    with _db() as c:
        row = c.execute("SELECT chat_context FROM sessions WHERE id=?", (session,)).fetchone()
    return json.loads(row["chat_context"]) if row and row["chat_context"] else None


def _save_context(session: str, ctx) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO sessions (id, network, chat_context, updated) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET chat_context=excluded.chat_context, updated=excluded.updated",
            (session, NETWORK, json.dumps(ctx) if ctx is not None else None, time.time()),
        )


@app.on_event("startup")
async def _startup():
    init_db()
    apply_llm()
    if ENV_FILE.exists():
        start_runtime()


@app.get("/api/sessions")
def list_sessions():
    with _db() as c:
        rows = c.execute(
            "SELECT s.id, COALESCE(NULLIF(s.title,''),'New chat') AS title, s.updated, "
            "(SELECT COUNT(*) FROM messages m WHERE m.session=s.id) AS n "
            "FROM sessions s ORDER BY s.updated DESC"
        ).fetchall()
    return {"sessions": [{"id": r["id"], "title": r["title"], "updated": r["updated"], "count": r["n"]} for r in rows]}


@app.get("/api/session/{sid}")
def get_session(sid: str):
    with _db() as c:
        rows = c.execute("SELECT role, text FROM messages WHERE session=? ORDER BY id", (sid,)).fetchall()
    return {"messages": [{"role": r["role"], "text": r["text"]} for r in rows]}


@app.delete("/api/session/{sid}")
def delete_session(sid: str):
    with _db() as c:
        c.execute("DELETE FROM messages WHERE session=?", (sid,))
        c.execute("DELETE FROM sessions WHERE id=?", (sid,))
    return {"deleted": sid}


def _decode_uescapes(s):
    # pyhocon leaves \uXXXX escapes literal (unlike JSON); decode them so text
    # renders correctly. chr(92) is a backslash — avoids escaping in this template.
    bs = chr(92)
    if bs + "u" not in s:
        return s
    import re as _re
    # Match a literal backslash followed by uXXXX. The regex needs an escaped
    # backslash (bs + bs); a single backslash would make re treat it as an
    # incomplete unicode escape and raise, breaking any network whose text
    # contains a backslash-u sequence.
    out = _re.sub(bs + bs + "u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    if any(chr(0xD800) <= c <= chr(0xDFFF) for c in out):
        try:
            out = out.encode("utf-16", "surrogatepass").decode("utf-16")
        except Exception:
            return s
    return out


def _plain(obj):
    if isinstance(obj, ConfigTree):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, str):
        return _decode_uescapes(obj)
    return obj


def _network_file() -> Path:
    return next(p for p in (ROOT / "registries").glob("*.hocon") if p.name != "manifest.hocon")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---- console config API ----
@app.get("/api/state")
async def state():
    running = False
    try:
        async with httpx.AsyncClient() as c:
            await c.get(f"http://localhost:{RUNTIME_PORT}/api/v1/list", timeout=2)
            running = True
    except Exception:
        running = False
    llm = {}
    if LLM_FILE.exists():
        try:
            llm = json.loads(LLM_FILE.read_text())
        except Exception:
            llm = {}
    return {"running": running, "configured": ENV_FILE.exists(), "network": NETWORK or _network_file().stem,
            "keys_set": sorted(load_env_file().keys()), "llm": llm}


class EnvBody(BaseModel):
    env: dict
    llm: dict | None = None


@app.post("/api/env")
async def set_env(body: EnvBody):
    cur = load_env_file()
    cur.update(body.env)
    write_env_file(cur)
    os.environ.update({k: v for k, v in cur.items() if v})
    if body.llm and body.llm.get("class") and body.llm.get("model_name"):
        LLM_FILE.write_text(json.dumps(body.llm))
        apply_llm()
    start_runtime()
    return {"ok": True}


# ---- ALIVE-compatible API used by the Talk UI ----
@app.get("/api/v1/tools")
def tools():
    path = ROOT / "config" / "tools_catalog.json"
    cfg = json.loads(path.read_text()).get("configurable", []) if path.exists() else []
    return {"tools": cfg}


class TestBody(BaseModel):
    tool_id: str
    config: dict


@app.post("/api/v1/tools/test")
def test_connection(body: TestBody):
    """Real connectivity probe for the 'Check connection' button (never persists)."""
    cfg = body.config or {}
    if body.tool_id == "mysql":
        try:
            import pymysql
            conn = pymysql.connect(
                host=cfg.get("host", "127.0.0.1"), port=int(cfg.get("port") or 3306),
                user=cfg.get("username"), password=cfg.get("password"),
                database=cfg.get("database"), connect_timeout=5,
            )
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            finally:
                conn.close()
            return {"ok": True, "detail": "Connected — MySQL responded."}
        except Exception as exc:
            return {"ok": False, "detail": str(exc)}
    return {"ok": True, "detail": "Saved (no live connection test for this tool yet)."}


@app.get("/api/v1/live/health")
async def health():
    s = await state()
    return {"reachable": s["running"], "base_url": f"http://localhost:{RUNTIME_PORT}"}


@app.get("/api/v1/live/networks")
async def live_networks():
    return {"agents": [{"agent_name": NETWORK or _network_file().stem, "description": "", "tags": []}]}


@app.get("/api/v1/networks/{name:path}")
def get_network(name: str):
    f = _network_file()
    conf = _plain(ConfigFactory.parse_string(f.read_text(), basedir=str(ROOT)))
    tools = []
    for i, t in enumerate(conf.get("tools", []) or []):
        func = t.get("function") or {}
        display = "coded_tool" if "class" in t else ("toolbox" if "toolbox" in t else ("front_man" if i == 0 else "llm_agent"))
        tools.append({
            "name": t.get("name"), "display_as": display,
            "instructions": t.get("instructions"), "description": func.get("description"),
            "class": t.get("class"), "toolbox": t.get("toolbox"),
            "tools": t.get("tools", []) or [], "function": func or None, "raw": t,
        })
    return {"name": f.stem, "metadata": conf.get("metadata", {}) or {},
            "llm_config": conf.get("llm_config", {}) or {}, "tools": tools}


@app.websocket("/api/v1/ws/chat/{session}/{agent:path}")
async def ws_chat(ws: WebSocket, session: str, agent: str):
    await ws.accept()
    try:
        while True:
            payload = json.loads(await ws.receive_text())
            user_text = payload.get("message", "")
            _save_message(session, "user", user_text)  # persist immediately
            req = {"user_message": {"type": "HUMAN", "text": user_text},
                   "chat_filter": {"chat_filter_type": "MAXIMAL"}}
            if payload.get("sly_data"):
                req["sly_data"] = payload["sly_data"]
            # Resume the conversation: inject the session's stored chat_context.
            ctx = payload.get("chat_context") or _load_context(session)
            if ctx:
                req["chat_context"] = ctx
            url = f"http://localhost:{RUNTIME_PORT}/api/v1/{agent}/streaming_chat"
            final_ai, new_ctx = "", None
            try:
                async with httpx.AsyncClient(timeout=None) as c:
                    async with c.stream("POST", url, json=req) as resp:
                        async for line in resp.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                frame = json.loads(line)
                            except Exception:
                                continue
                            r = frame.get("response") or {}
                            await ws.send_json({"type": "chunk", "response": r})
                            t = r.get("type")
                            otrace = [o.get("tool") for o in (r.get("origin") or []) if isinstance(o, dict)]
                            if t == "AI" and r.get("text") and len(otrace) <= 1:
                                final_ai = r["text"]  # the front-man's answer
                            if t in _LOG_TYPES:
                                await ws.send_json({"type": "log", "entry": {"timestamp": _now(), "agent": agent, "source": "NeuroSan", "message": json.dumps({"otrace": otrace})}})
                                st = r.get("structure") or {}
                                if t == "AGENT" and isinstance(st, dict) and "total_tokens" in st:
                                    await ws.send_json({"type": "log", "entry": {"timestamp": _now(), "agent": agent, "source": "NeuroSan", "message": json.dumps({"token_accounting": st})}})
                            if r.get("chat_context"):
                                new_ctx = r["chat_context"]
                                await ws.send_json({"type": "chat_context", "chat_context": new_ctx})
                # Persist the turn so the user never loses context.
                if final_ai:
                    _save_message(session, "assistant", final_ai)
                if new_ctx is not None:
                    _save_context(session, new_ctx)
                await ws.send_json({"type": "done"})
            except httpx.HTTPError as exc:
                await ws.send_json({"type": "error", "detail": str(exc)})
    except WebSocketDisconnect:
        return


# ---- static Talk UI (mounted last so /api/* wins) ----
if (STATIC / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC / "assets")), name="assets")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    # Serve any real static file shipped in the bundle (the Cognizant logos under
    # /cognizant, the favicon, etc.), else fall back to index.html for client-side
    # routing. Registered last, so the /api/* routes above always win. Without this
    # the logo/favicon 404'd (only /assets was mounted) and showed broken images.
    if full_path:
        candidate = (STATIC / full_path).resolve()
        if str(candidate).startswith(str(STATIC.resolve()) + os.sep) and candidate.is_file():
            return FileResponse(candidate)
    html = STATIC / "index.html"
    return HTMLResponse(html.read_text()) if html.exists() else HTMLResponse("<h1>UI not built</h1>")
