"""Deterministic city routing. Closed roads are removed before route search."""
from __future__ import annotations

import networkx as nx

NODES = {
    "Harbor": (0, 0), "Civic": (2, 1), "Market": (4, 0),
    "North": (1, 3), "Central": (3, 3), "East": (5, 3),
    "Hill": (0, 5), "Shelter": (3, 5), "Airport": (6, 5),
}
ROADS = [
    ("Harbor", "Civic", 2.2), ("Civic", "Market", 2.4),
    ("Harbor", "North", 3.1), ("Civic", "North", 2.1),
    ("Civic", "Central", 2.4), ("Market", "Central", 3.0),
    ("Market", "East", 3.1), ("North", "Central", 2.2),
    ("Central", "East", 2.3), ("North", "Hill", 2.2),
    ("North", "Shelter", 3.0), ("Central", "Shelter", 2.0),
    ("Central", "Airport", 4.0), ("East", "Airport", 2.4),
    ("Hill", "Shelter", 3.4), ("Shelter", "Airport", 3.0),
]


def graph_for(closures: set[tuple[str, str]] | None = None) -> nx.Graph:
    blocked = {frozenset(edge) for edge in (closures or set())}
    graph = nx.Graph()
    for name, (x, y) in NODES.items():
        graph.add_node(name, x=x, y=y)
    for a, b, distance in ROADS:
        if frozenset((a, b)) not in blocked:
            graph.add_edge(a, b, distance=distance)
    return graph


def candidate_routes(start: str, destination: str = "Shelter", closures: set[tuple[str, str]] | None = None) -> list[dict]:
    graph = graph_for(closures)
    if start not in graph or destination not in graph or not nx.has_path(graph, start, destination):
        return []
    paths = nx.shortest_simple_paths(graph, start, destination, weight="distance")
    results = []
    for path in list(__import__("itertools").islice(paths, 3)):
        distance = sum(graph[a][b]["distance"] for a, b in zip(path, path[1:]))
        results.append({"nodes": path, "distance_km": round(distance, 1), "cost": round(distance, 1)})
    return results
