"""StudFinder web app. Run:  python app.py   then open http://localhost:8000"""

from __future__ import annotations

import os
import threading
import uuid
import webbrowser

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from studfinder import agents
from studfinder.config import MAX_CHAT_CHARS, MAX_DESCRIPTION_CHARS, ROOT, SESSION_TOKEN_BUDGET, client
from studfinder.export import bricklink_xml
from studfinder.state import Session

app = FastAPI(title="StudFinder")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
SESSIONS: dict[str, Session] = {}


def get_session(sid: str) -> Session:
    if not sid or len(sid) > 64:
        raise HTTPException(400, "Missing session id.")
    if sid not in SESSIONS:
        if len(SESSIONS) > 500:  # keep memory bounded
            SESSIONS.pop(next(iter(SESSIONS)))
        SESSIONS[sid] = Session(id=sid)
    return SESSIONS[sid]


def state(s: Session) -> dict:
    data = s.to_json()
    data["budget"] = {"session_limit": SESSION_TOKEN_BUDGET, "used": s.session_tokens()}
    xml, skipped = bricklink_xml(s)
    data["export_skipped"] = skipped
    return data


def run_in_background(s: Session, fn, text: str) -> None:
    def work():
        try:
            fn(s, text)
        except agents.BudgetExceeded as e:
            s.error = str(e)
        except Exception as e:  # show the problem in the UI instead of hanging
            s.error = f"Something went wrong: {type(e).__name__}: {str(e)[:200]}"
        finally:
            s.running = ""
            s.lock.release()

    if not s.lock.acquire(blocking=False):
        raise HTTPException(409, "Still working on the last request.")
    s.running = "starting"
    threading.Thread(target=work, daemon=True).start()


class FindIn(BaseModel):
    session_id: str
    description: str


class ChatIn(BaseModel):
    session_id: str
    message: str


class EditIn(BaseModel):
    session_id: str
    item_id: int
    action: str  # "qty" | "remove" | "swap"
    qty: int = 0


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/state")
def get_state(session_id: str):
    return state(get_session(session_id))


@app.post("/api/find")
def find(body: FindIn):
    s = get_session(body.session_id)
    if not body.description.strip():
        raise HTTPException(400, "Describe your build first.")
    if len(body.description) > MAX_DESCRIPTION_CHARS:
        raise HTTPException(400, f"Keep the description under {MAX_DESCRIPTION_CHARS} characters.")
    run_in_background(s, agents.find_parts, body.description)
    return state(s)


@app.post("/api/chat")
def chat(body: ChatIn):
    s = get_session(body.session_id)
    if not body.message.strip():
        raise HTTPException(400, "Type a message first.")
    if len(body.message) > MAX_CHAT_CHARS:
        raise HTTPException(400, f"Keep messages under {MAX_CHAT_CHARS} characters.")
    run_in_background(s, agents.refine, body.message)
    return state(s)


@app.post("/api/edit")
def edit(body: EditIn):
    s = get_session(body.session_id)
    if s.running:
        raise HTTPException(409, "Wait for the agents to finish.")
    it = s.items.get(body.item_id)
    if not it:
        raise HTTPException(404, "No such item.")
    if body.action == "qty":
        res = s.set_qty(it.id, body.qty)
    elif body.action == "remove":
        res = s.remove(it.id)
    elif body.action == "swap" and it.suggestion:
        res = s.replace(it.id, it.suggestion["part_num"], it.suggestion["color"])
    else:
        raise HTTPException(400, "Unknown edit.")
    if "error" in res:
        raise HTTPException(400, res["error"])
    return state(s)


@app.post("/api/reset")
def reset(body: ChatIn):
    SESSIONS.pop(body.session_id, None)
    return state(get_session(body.session_id))


@app.get("/api/export.xml")
def export(session_id: str):
    xml, _ = bricklink_xml(get_session(session_id))
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": 'attachment; filename="studfinder-wanted-list.xml"'})


@app.get("/api/health")
def health():
    try:
        client()
        return {"ok": True}
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Run StudFinder")
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    ap.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = ap.parse_args()
    port = args.port
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    print(f"\n  StudFinder running at http://localhost:{port}  (Ctrl+C to stop)\n")
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False, log_level="warning")
