"""Legacy FastAPI server exposing the location-time graph.

This file contains the original FastAPI implementation that predates the new
`mcp_location_server.py` server. It is kept here for reference or for
scenarios where a plain REST/JSON API is preferred.

Run from the project root with:
    pip install fastapi uvicorn networkx
    python -m experiments.fastapi_location_server --host 0.0.0.0 --port 8000

Note: This is a legacy implementation. For new projects, consider using
`mcp_location_server.py` which provides better performance and features.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import networkx as nx
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
import pickle

# Path to the graph file in the output_data directory
GRAPH_PATH = Path(__file__).parent.parent / "output_data" / "graph.pkl"
PAGE_SIZE_DEFAULT = 50

app = FastAPI(title="Location Profile FastAPI Server", version="0.1.0-legacy")


class MCPResource(BaseModel):
    uri: str
    name: str
    type: str  # "location" | "transition"
    score: float | None = None
    meta: Dict[str, str] | None = None


class GraphCache:
    """File-timestamp cache so we only unpickle when graph.pkl changes."""

    def __init__(self, graph_path: Path):
        self.graph_path = graph_path
        self._mod_ts: float | None = None
        self._graph: nx.DiGraph | None = None

    def get_graph(self) -> nx.DiGraph:
        try:
            curr_ts = self.graph_path.stat().st_mtime
        except FileNotFoundError as e:
            raise HTTPException(status_code=500, detail="graph.pkl not found – run location_profiler.py first") from e

        if self._graph is None or self._mod_ts != curr_ts:
            with self.graph_path.open("rb") as f:
                self._graph = pickle.load(f)
            self._mod_ts = curr_ts
        return self._graph  # type: ignore[return-value]


graph_cache = GraphCache(GRAPH_PATH)

def get_graph() -> nx.DiGraph:  # FastAPI dependency
    return graph_cache.get_graph()

# ---------------------------------------------------------------------------
# Core resource endpoints
# ---------------------------------------------------------------------------


@app.get("/resources", response_model=Dict[str, object])
def list_resources(
    cursor: str | None = Query(None, description="Opaque pagination cursor from previous call"),
    page_size: int = Query(PAGE_SIZE_DEFAULT, le=500, ge=1),
    include_edges: bool = Query(False),
    G: nx.DiGraph = Depends(get_graph),
):
    try:
        offset = int(cursor) if cursor else 0
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid cursor")

    node_uris = [f"location:{n}" for n in sorted(G.nodes)]
    edge_uris: List[str] = [f"transition:{u}->{v}" for u, v in sorted(G.edges)] if include_edges else []
    all_uris = node_uris + edge_uris
    slice_uris = all_uris[offset : offset + page_size]

    def _build(uri: str) -> MCPResource:
        if uri.startswith("location:"):
            place_id = uri.split(":", 1)[1]
            data = G.nodes[place_id]
            return MCPResource(
                uri=uri,
                name=place_id,
                type="location",
                score=data.get("score"),
                meta={
                    "visits_30d": str(data.get("visits_30d")),
                    "last_visit_ts": str(data.get("last_visit_ts")),
                    "active": str(data.get("active")),
                },
            )
        src_dst = uri.split(":", 1)[1]
        src, dst = src_dst.split("->")
        data = G[src][dst]
        return MCPResource(
            uri=uri,
            name=src_dst,
            type="transition",
            score=data.get("score"),
            meta={
                "transitions_30d": str(data.get("transitions_30d")),
                "last_transition_ts": str(data.get("last_transition_ts")),
                "active": str(data.get("active")),
            },
        )

    resources = [_build(u).dict() for u in slice_uris]
    next_cursor = str(offset + page_size) if offset + page_size < len(all_uris) else None
    return {"resources": resources, "next_cursor": next_cursor}


@app.get("/resources/{resource_uri:path}", response_model=MCPResource)
def read_resource(resource_uri: str, G: nx.DiGraph = Depends(get_graph)):
    if resource_uri.startswith("location:"):
        place_id = resource_uri.split(":", 1)[1]
        if place_id not in G:
            raise HTTPException(status_code=404, detail="Location not found")
        data = G.nodes[place_id]
        return MCPResource(uri=resource_uri, name=place_id, type="location", score=data.get("score"), meta=data)

    if resource_uri.startswith("transition:"):
        try:
            src, dst = resource_uri.split(":", 1)[1].split("->")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid transition uri")
        if not G.has_edge(src, dst):
            raise HTTPException(status_code=404, detail="Transition not found")
        data = G[src][dst]
        return MCPResource(uri=resource_uri, name=f"{src}->{dst}", type="transition", score=data.get("score"), meta=data)

    raise HTTPException(status_code=400, detail="Unknown resource type")

# ---------------------------------------------------------------------------
# Helper analytic endpoints
# ---------------------------------------------------------------------------


@app.get("/query/top_locations_weekday", response_model=List[Tuple[str, int]])
def query_top_locations_weekday(weekday: int = Query(..., ge=0, le=6), n: int = Query(5), G: nx.DiGraph = Depends(get_graph)):
    dest_counts: Dict[str, int] = {}
    prefix = f"{weekday}_"
    for _, dst, data in G.edges(data=True):
        for bucket, cnt in data.get("time_buckets", {}).items():
            if bucket.startswith(prefix):
                dest_counts[dst] = dest_counts.get(dst, 0) + cnt
    ranked = sorted(dest_counts.items(), key=lambda x: x[1], reverse=True)[:n]
    return ranked


@app.get("/query/top_routes_weekday", response_model=List[Tuple[str, int]])
def query_top_routes_weekday(weekday: int = Query(..., ge=0, le=6), n: int = Query(5), G: nx.DiGraph = Depends(get_graph)):
    prefix = f"{weekday}_"
    route_counts: Dict[str, int] = {}
    for src, dst, data in G.edges(data=True):
        total = sum(cnt for bucket, cnt in data.get("time_buckets", {}).items() if bucket.startswith(prefix))
        if total:
            route_counts[f"{src}->{dst}"] = total
    ranked = sorted(route_counts.items(), key=lambda x: x[1], reverse=True)[:n]
    return ranked


@app.get("/query/top_locations", response_model=List[str])
def query_top_locations(days: int = Query(30), n: int = Query(3), G: nx.DiGraph = Depends(get_graph)):
    now = datetime.now(datetime.timezone.utc)
    cutoff = now - timedelta(days=days)
    def score(node_data):
        last = node_data.get("last_visit_ts")
        if last and last >= cutoff:
            return node_data.get("visits_30d", 0)
        return 0
    ranked = sorted(((nid, score(d)) for nid, d in G.nodes(data=True)), key=lambda x: x[1], reverse=True)
    return [nid for nid, _ in ranked[:n]]


@app.get("/query/next_location", response_model=List[Tuple[str, float]])
def query_next_location(current_place: str = Query(...), weekday: int | None = Query(None, ge=0, le=6), hour: int | None = Query(None, ge=0, le=23), top_k: int = Query(3), G: nx.DiGraph = Depends(get_graph)):
    if current_place not in G:
        raise HTTPException(status_code=404, detail="Unknown current_place")
    if weekday is None or hour is None:
        now = datetime.now(datetime.timezone.utc)
        weekday, hour = now.weekday(), now.hour
    bucket = f"{weekday}_{hour}"
    candidates: List[Tuple[str, float]] = []
    for _, dst, data in G.out_edges(current_place, data=True):
        base = data.get("score", 0.0)
        bucket_bonus = data.get("time_buckets", {}).get(bucket, 0)
        candidates.append((dst, base + 0.1 * bucket_bonus))
    ranked = sorted(candidates, key=lambda x: x[1], reverse=True)[:top_k]
    return ranked

# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Legacy FastAPI server for location profile data")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--graph", type=Path, default=GRAPH_PATH, 
                      help=f"Path to graph.pkl (default: {GRAPH_PATH})")
    args = parser.parse_args()

    # Update the graph path if specified
    global GRAPH_PATH
    if args.graph != GRAPH_PATH:
        GRAPH_PATH = args.graph
        graph_cache.graph_path = GRAPH_PATH

    import uvicorn
    uvicorn.run("experiments.fastapi_location_server:app", 
               host=args.host, 
               port=args.port, 
               reload=args.reload, log_level="info")


if __name__ == "__main__":
    main()
