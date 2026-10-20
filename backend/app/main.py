from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .routing import NODES, ROADS, candidate_routes

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT.parent / ".env")
configured_db = Path(os.getenv("DATABASE_PATH", str(ROOT / "orbit.db")))
DB_PATH = str(configured_db if configured_db.is_absolute() else (ROOT / configured_db).resolve())
app = FastAPI(title="ORBIT AI Mission API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
listeners: dict[str, set[WebSocket]] = {}


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.on_event("startup")
def initialize() -> None:
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS missions (id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL, decision TEXT, report TEXT, created_at TEXT NOT NULL, events TEXT NOT NULL DEFAULT '[]', closures TEXT NOT NULL DEFAULT '[]')")


class MissionInput(BaseModel):
    incident_location: str = "Harbor"
    severity: int = Field(default=4, ge=1, le=5)


class ClosureInput(BaseModel):
    mission_id: str
    road_from: str
    road_to: str


class DecisionInput(BaseModel):
    note: str = Field(default="", max_length=500)


def get_mission(mission_id: str) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Mission not found")
    out = dict(row)
    for key in ("payload", "events", "closures", "report", "decision"):
        if out[key]:
            out[key] = json.loads(out[key])
    return out


async def emit(mission_id: str, kind: str, message: str, **extra) -> dict:
    event = {"id": str(uuid.uuid4()), "at": utcnow(), "kind": kind, "message": message, **extra}
    with db() as conn:
        row = conn.execute("SELECT events FROM missions WHERE id=?", (mission_id,)).fetchone()
        events = json.loads(row[0]) if row else []
        events.append(event)
        conn.execute("UPDATE missions SET events=? WHERE id=?", (json.dumps(events), mission_id))
    for socket in list(listeners.get(mission_id, set())):
        try:
            await socket.send_json(event)
        except Exception:
            listeners[mission_id].discard(socket)
    return event


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "gemini" if os.getenv("GEMINI_API_KEY") else "deterministic-demo", "simulation_only": True}


@app.post("/api/missions")
async def create_mission(body: MissionInput):
    if body.incident_location not in NODES:
        raise HTTPException(422, f"Unknown city location. Choose one of: {', '.join(NODES)}")
    mission_id = str(uuid.uuid4())
    payload = body.model_dump()
    with db() as conn:
        conn.execute("INSERT INTO missions(id,payload,status,created_at,events,closures) VALUES(?,?,?,?,?,?)", (mission_id, json.dumps(payload), "ready", utcnow(), "[]", "[]"))
    await emit(mission_id, "mission.created", "Simulated flood mission created.", stage="ready")
    return get_mission(mission_id)


async def gemini_assessment(payload: dict) -> dict | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    schema = {"type": "OBJECT", "properties": {"summary": {"type": "STRING"}, "assumptions": {"type": "ARRAY", "items": {"type": "STRING"}}, "confidence": {"type": "NUMBER"}}, "required": ["summary", "assumptions", "confidence"]}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{os.getenv('GEMINI_MODEL', 'gemini-3.6-flash')}:generateContent"
    prompt = ("Assess this simulated flood incident in one concise paragraph. Only use supplied facts; label uncertainty. " + json.dumps(payload))
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(url, headers={"x-goog-api-key": api_key}, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema}})
            response.raise_for_status()
        parsed = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"])
        if not isinstance(parsed.get("summary"), str) or not isinstance(parsed.get("assumptions"), list):
            return None
        return {"summary": parsed["summary"], "assumptions": parsed["assumptions"], "confidence": max(0, min(1, float(parsed.get("confidence", .72)))), "source": "Gemini"}
    except Exception:
        return None


@app.post("/api/missions/{mission_id}/run")
async def run_mission(mission_id: str):
    mission = get_mission(mission_id)
    if mission["status"] in ("approved", "rejected"):
        raise HTTPException(409, "This mission has already been reviewed")
    payload, closures = mission["payload"], {tuple(edge) for edge in mission["closures"]}
    await emit(mission_id, "agent.started", "Incident Assessment Agent started.", agent="assessment", status="running")
    assessment = await gemini_assessment(payload)
    if assessment is None:
        assessment = {"summary": f"Flooding is simulated near {payload['incident_location']}. Severity {payload['severity']}/5 indicates elevated access risk; field conditions are not verified.", "assumptions": ["Flood boundary is a scenario input, not a sensor reading.", "Shelter and road data are simulated."], "confidence": 0.78, "source": "Deterministic fallback"}
    await emit(mission_id, "agent.completed", "Incident assessment validated.", agent="assessment", status="completed")
    await emit(mission_id, "agent.started", "Route Planning Agent is evaluating open roads.", agent="routing", status="running")
    routes = candidate_routes(payload["incident_location"], closures=closures)
    await emit(mission_id, "route.recalculated", f"{len(routes)} valid candidate routes found.", routes=routes)
    await emit(mission_id, "agent.completed", "Route planning completed with deterministic network search.", agent="routing", status="completed")
    await emit(mission_id, "agent.started", "Resource Allocation Agent is checking shelter limits.", agent="resources", status="running")
    demand = payload["severity"] * 34
    allocation = {"shelter": "Shelter", "requested_people": demand, "allocated_people": min(demand, 120), "capacity": 120, "shortage": max(0, demand-120), "within_capacity": demand <= 120}
    await emit(mission_id, "agent.completed", "Shelter capacity constraints checked.", agent="resources", status="completed")
    report = {"incident": payload, "assessment": assessment, "routes": routes, "selected_route": routes[0] if routes else None, "resource_proposal": allocation, "unresolved_uncertainties": assessment["assumptions"], "simulation_only": True, "awaiting_human_approval": True}
    with db() as conn:
        conn.execute("UPDATE missions SET status='awaiting_approval', report=? WHERE id=?", (json.dumps(report), mission_id))
    await emit(mission_id, "mission.awaiting_approval", "Plan is ready for human review. No emergency services are contacted.", stage="approval")
    return get_mission(mission_id)


@app.get("/api/missions/{mission_id}")
def read_mission(mission_id: str):
    return get_mission(mission_id)


@app.get("/api/missions/{mission_id}/events")
def read_events(mission_id: str):
    return {"events": get_mission(mission_id)["events"]}


@app.post("/api/simulation/road-closures")
async def close_road(body: ClosureInput):
    mission = get_mission(body.mission_id)
    valid_roads = {frozenset((a,b)) for a,b,_ in ROADS}
    if frozenset((body.road_from, body.road_to)) not in valid_roads:
        raise HTTPException(422, "Road does not exist in the simulated network")
    closures = {tuple(edge) for edge in mission["closures"]}
    closures.add((body.road_from, body.road_to))
    with db() as conn:
        conn.execute("UPDATE missions SET closures=?, status='ready' WHERE id=?", (json.dumps([list(e) for e in sorted(closures)]), body.mission_id))
    await emit(body.mission_id, "road.closed", f"Simulated road closure: {body.road_from} → {body.road_to}.", road=[body.road_from, body.road_to])
    return {"mission_id": body.mission_id, "closures": [list(edge) for edge in sorted(closures)], "status": "ready_to_recalculate"}


@app.post("/api/missions/{mission_id}/approve")
async def approve(mission_id: str, body: DecisionInput):
    mission = get_mission(mission_id)
    if not mission["report"]:
        raise HTTPException(409, "Run the mission before review")
    with db() as conn:
        conn.execute("UPDATE missions SET status='approved', decision=? WHERE id=?", (json.dumps({"decision":"approved","note":body.note,"at":utcnow()}), mission_id))
    await emit(mission_id, "mission.approved", "Simulation plan approved by human reviewer.", note=body.note)
    return get_mission(mission_id)


@app.post("/api/missions/{mission_id}/reject")
async def reject(mission_id: str, body: DecisionInput):
    mission = get_mission(mission_id)
    if not mission["report"]:
        raise HTTPException(409, "Run the mission before review")
    with db() as conn:
        conn.execute("UPDATE missions SET status='rejected', decision=? WHERE id=?", (json.dumps({"decision":"rejected","note":body.note,"at":utcnow()}), mission_id))
    await emit(mission_id, "mission.rejected", "Simulation plan rejected by human reviewer.", note=body.note)
    return get_mission(mission_id)


@app.websocket("/ws/missions/{mission_id}")
async def mission_socket(socket: WebSocket, mission_id: str):
    try:
        mission = get_mission(mission_id)
    except HTTPException:
        await socket.close(code=1008)
        return
    await socket.accept()
    listeners.setdefault(mission_id, set()).add(socket)
    try:
        for event in mission["events"]:
            await socket.send_json(event)
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        listeners.get(mission_id, set()).discard(socket)
