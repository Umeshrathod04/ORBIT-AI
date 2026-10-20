# ORBIT AI — Autonomous Emergency Response Command Center

ORBIT AI is a local, hackathon-ready **simulation** for flood-response planning. It combines an interactive 3D digital twin with a FastAPI mission service, a deterministic NetworkX road router, SQLite event persistence, optional Gemini assessment, and explicit human review controls.

> **Training and simulation only.** The demo does not connect to emergency services, verify real-world conditions, or provide certified evacuation guidance. No dispatch occurs.

## What works

- Start a simulated flood mission and choose incident severity.
- Follow assessment, route-planning, and resource-allocation events in the UI.
- Inspect an interactive 3D city with an incident marker, flood area, road network, shelter, and selected route.
- Simulate a road closure and recalculate valid paths using NetworkX; closed links are excluded from routing.
- Check shelter capacity with deterministic constraints. Allocations never exceed capacity.
- Approve or reject a proposed simulation plan and inspect the persisted mission audit trail.
- Run without an AI key using a clearly labeled deterministic assessment. Optionally configure Gemini for structured incident summaries; routing and allocation remain deterministic.

## Run locally

Requirements: Python 3.10+ and Node.js 20+.

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item ..\.env.example ..\.env
uvicorn app.main:app --reload --port 8000
```

The API reads environment variables from the root `.env` file. To enable Gemini, set `GEMINI_API_KEY` there before starting the backend. With no key configured the deterministic demo remains fully usable. The optional model call uses Gemini structured JSON output and validates the result before it enters the mission report. The model never computes routes or changes the city. The `OPENAI_API_KEY` stored in `.env.local` from the earlier key setup is not used by this Gemini-first project.

### Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`). The Vite development server proxies API and WebSocket requests to `127.0.0.1:8000`.

### Automated tests and production build

```powershell
cd backend
pytest
cd ..\frontend
npm run build
```

## Demo flow

1. Start a mission. The simulated flood incident appears at Harbor and the event timeline records the coordinator workflow.
2. Follow assessment, route search, and shelter allocation. The preferred route is calculated from the road graph.
3. Select **Simulate road closure**. Harbor → North closes; the backend records the closure and calculates a new route.
4. Open the audit trail to inspect the assessment source, route, resource proposal, and uncertainties.
5. Approve or reject the proposal. This records a simulation review decision only.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/missions` | Create a simulated mission |
| `GET` | `/api/missions/{mission_id}` | Retrieve mission state |
| `POST` | `/api/missions/{mission_id}/run` | Run assessment, route, and resource agents |
| `GET` | `/api/missions/{mission_id}/events` | Read persisted event history |
| `POST` | `/api/missions/{mission_id}/approve` | Record human approval |
| `POST` | `/api/missions/{mission_id}/reject` | Record human rejection |
| `POST` | `/api/simulation/road-closures` | Close a simulated road and trigger a later reroute |
| `GET` | `/api/health` | Service and mode status |
| `WS` | `/ws/missions/{mission_id}` | Replay persisted events and stream new events |

SQLite defaults to `backend/orbit.db`. Set `DATABASE_PATH` to change it. There is no authentication layer in this demonstration; do not expose the service to an untrusted network.

## Architecture notes

- Frontend: React, Vite, TypeScript, React Three Fiber, Drei, Framer Motion, Lucide, and Recharts.
- Backend: FastAPI, Pydantic, NetworkX, SQLite, HTTPX, and a backend-only optional Gemini REST call.
- Deterministic code owns route validity, road closures, candidate path cost, capacity limits, persistence, and review state.
- WebSocket messages are also stored in SQLite, so reconnecting clients can replay events.
- All incident data, map locations, shelter counts, capacity, route distances, and network metrics shown here are sample simulation data.

## Three-minute demo script

**0:00–0:30 — Situation.** “ORBIT AI is a simulated response command center. This Harbor flood is generated sample data. Nothing here is connected to emergency dispatch.” Point out the incident, modeled flood area, city network, and shelter marker in the digital twin.

**0:30–1:10 — Agent workflow.** Start a mission and describe the assessment, route planner, and resource allocator. The assessment is either a validated Gemini summary or a labeled deterministic fallback. The route planner always queries the deterministic graph; the model cannot invent a route.

**1:10–1:50 — Constraint change.** Trigger the Central-to-Shelter road closure. Show the closure event and updated route. Explain that closed links are removed before NetworkX searches and that the service reports no route when one cannot be found.

**1:50–2:30 — Resource and review.** Show the shelter allocation against its 120-person capacity. Increase severity before starting a new mission to demonstrate a visible shortage rather than over-allocation. Approve or reject the plan to record the human decision.

**2:30–3:00 — Audit.** Open the report and review incident inputs, source/confidence, candidate route, resource proposal, event timestamps, and unresolved assumptions. Close with the simulation-only boundary and the work needed before any real-world deployment: verified feeds, identity/access controls, operational validation, and formal safety review.
