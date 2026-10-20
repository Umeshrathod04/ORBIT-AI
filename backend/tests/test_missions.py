import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.routing import ROADS, candidate_routes


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "test.db"))
    with TestClient(main.app) as test_client:
        yield test_client


def new_mission(client, severity=4):
    response = client.post("/api/missions", json={"incident_location": "Harbor", "severity": severity})
    assert response.status_code == 200
    return response.json()


def test_mission_creation_and_retrieval(client):
    mission = new_mission(client)
    retrieved = client.get(f"/api/missions/{mission['id']}").json()
    assert retrieved["id"] == mission["id"]
    assert retrieved["status"] == "ready"
    assert retrieved["events"][0]["kind"] == "mission.created"


def test_invalid_incident_payload(client):
    assert client.post("/api/missions", json={"incident_location": "Atlantis", "severity": 4}).status_code == 422
    assert client.post("/api/missions", json={"incident_location": "Harbor", "severity": 9}).status_code == 422


def test_valid_shortest_route(client):
    routes = candidate_routes("Harbor")
    assert routes
    assert routes[0]["nodes"][0] == "Harbor"
    assert routes[0]["nodes"][-1] == "Shelter"
    assert routes[0]["distance_km"] > 0


def test_route_recalculates_after_road_closure(client):
    mission = new_mission(client)
    before = client.post(f"/api/missions/{mission['id']}/run").json()["report"]["selected_route"]["nodes"]
    client.post("/api/simulation/road-closures", json={"mission_id": mission["id"], "road_from": "Harbor", "road_to": "North"})
    after_mission = client.post(f"/api/missions/{mission['id']}/run").json()
    after = after_mission["report"]["selected_route"]["nodes"]
    assert ["Harbor", "North"] not in list(zip(after, after[1:]))
    assert before != after


def test_no_route_is_reported_instead_of_invented():
    closures = {(a, b) for a, b, _ in ROADS}
    assert candidate_routes("Harbor", closures=closures) == []


def test_shelter_capacity_is_never_exceeded(client):
    mission = new_mission(client, severity=5)
    result = client.post(f"/api/missions/{mission['id']}/run").json()
    allocation = result["report"]["resource_proposal"]
    assert allocation["allocated_people"] <= allocation["capacity"]
    assert allocation["shortage"] == 50
    assert allocation["within_capacity"] is False


def test_deterministic_fallback_and_structured_assessment(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    mission = new_mission(client)
    result = client.post(f"/api/missions/{mission['id']}/run").json()
    assessment = result["report"]["assessment"]
    assert assessment["source"] == "Deterministic fallback"
    assert isinstance(assessment["assumptions"], list)
    assert 0 <= assessment["confidence"] <= 1


def test_malformed_gemini_json_uses_fallback(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "not-json"}]}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    mission = new_mission(client)
    result = client.post(f"/api/missions/{mission['id']}/run").json()
    assert result["report"]["assessment"]["source"] == "Deterministic fallback"


def test_approval_and_rejection_workflows(client):
    first = new_mission(client)
    client.post(f"/api/missions/{first['id']}/run")
    approved = client.post(f"/api/missions/{first['id']}/approve", json={"note": "Reviewed"}).json()
    assert approved["status"] == "approved"
    assert approved["decision"]["decision"] == "approved"
    second = new_mission(client)
    client.post(f"/api/missions/{second['id']}/run")
    rejected = client.post(f"/api/missions/{second['id']}/reject", json={"note": "Need more data"}).json()
    assert rejected["status"] == "rejected"
    assert rejected["decision"]["decision"] == "rejected"


def test_events_are_persisted_and_returned(client):
    mission = new_mission(client)
    client.post(f"/api/missions/{mission['id']}/run")
    events = client.get(f"/api/missions/{mission['id']}/events").json()["events"]
    kinds = {event["kind"] for event in events}
    assert "agent.started" in kinds
    assert "route.recalculated" in kinds
    assert "mission.awaiting_approval" in kinds


def test_health_explicitly_reports_simulation_mode(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = client.get("/api/health").json()
    assert response["mode"] == "deterministic-demo"
    assert response["simulation_only"] is True
