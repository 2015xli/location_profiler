"""MCP (Model Context Protocol) server exposing a location-time graph

This implementation uses the **official MCP Python SDK** (`mcp` package) and the
`FastMCP` convenience class, replacing the previous pure-FastAPI approach.

Tools exposed:
  • list_resources(include_edges: bool = False) -> list[str]
      URIs of nodes (and optionally edges) in deterministic order.
  • read_resource(uri: str) -> dict
      Full JSON payload for one location/transition.
  • top_locations(days: int = 30, n: int = 3) -> list[str]
  • next_location(current_place: str, weekday: int | None = None,
                  hour: int | None = None, top_k: int = 3)
      Predict next likely destinations.
  • top_locations_weekday(weekday: int, n: int = 5)
      Most probable places on a given weekday.
  • top_routes_weekday(weekday: int, n: int = 5)
      Most common routes on a weekday.

Run with:
    pip install mcp networkx
    python mcp_location_server.py  # defaults to 0.0.0.0:8000 /mcp
"""
from __future__ import annotations

import argparse
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import networkx as nx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Graph loading helpers
# ---------------------------------------------------------------------------

GRAPH_PATH = Path(__file__).parent / "output_data" / "graph.pkl"

def _load_graph() -> nx.DiGraph:
    """Unpickle the graph on every tool call (cheap for small graphs)."""
    if not GRAPH_PATH.exists():
        raise FileNotFoundError("graph.pkl not found – generate it with location_profiler.py first")
    with GRAPH_PATH.open("rb") as f:
        return pickle.load(f)


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("LocationGraphServer", host="0.0.0.0", port=8000, path="/mcp")

# -------------------------- basic resource access ---------------------------


@mcp.tool()
def read_location_graph(include_edges: bool = False) -> List[str]:
    """List all resource URIs contained in the location-time graph.

Parameters
----------
include_edges : bool, optional (default=False)
    When *True*, transition edge URIs of the form ``"transition:<src>-><dst>"`` are
    included in addition to location node URIs (``"location:<place_id>"``).

Returns
-------
list[str]
    A lexicographically-sorted list of URI strings uniquely identifying
    every requested resource in the graph.

Examples
--------
>>> client.call_tool("read_location_graph", {"include_edges": True})
["location:loc_home", "transition:loc_home->loc_work", ...]
"""
    G = _load_graph()
    uris = [f"location:{n}" for n in sorted(G.nodes)]
    if include_edges:
        uris += [f"transition:{u}->{v}" for u, v in sorted(G.edges)]
    return uris


@mcp.tool()
def read_location_or_transition(uri: str) -> Dict:
    """Fetch the complete JSON representation for a graph resource.

Parameters
----------
uri : str
    Either a location URI (``"location:<place_id>"``) or a transition URI
    (``"transition:<src>-><dst>"``) exactly as returned by
    :pyfunc:`read_location_graph`.

Returns
-------
dict
    The resource metadata copied directly from the underlying NetworkX graph
    with any ``datetime`` values serialised to ISO-8601 strings.

Raises
------
ValueError
    If the supplied ``uri`` does not exist or has an unknown prefix.

Example
-------
>>> client.call_tool("read_location_or_transition", {"uri": "location:loc_home"})
{"type": "location", "id": "loc_home", "visits_30d": 42, ...}
"""
    G = _load_graph()
    if uri.startswith("location:"):
        place_id = uri.split(":", 1)[1]
        if place_id not in G:
            raise ValueError("Location not found")
        data = G.nodes[place_id].copy()
        # Convert non-serialisable objects
        if isinstance(data.get("last_visit_ts"), datetime):
            data["last_visit_ts"] = data["last_visit_ts"].isoformat()
        return {"type": "location", "id": place_id, **data}

    if uri.startswith("transition:"):
        src_dst = uri.split(":", 1)[1]
        try:
            src, dst = src_dst.split("->")
        except ValueError as e:
            raise ValueError("Invalid transition uri") from e
        if not G.has_edge(src, dst):
            raise ValueError("Transition not found")
        data = G[src][dst].copy()
        if isinstance(data.get("last_transition_ts"), datetime):
            data["last_transition_ts"] = data["last_transition_ts"].isoformat()
        return {"type": "transition", "id": src_dst, **data}

    raise ValueError("Unknown resource type")


# ---------------------------- analytic helpers -----------------------------


@mcp.tool()
def top_locations(days: int = 30, n: int = 3) -> List[str]:
    """Rank locations by visit count over a recent time window.

Parameters
----------
days : int, optional (default=30)
    Look-back horizon in days. Only visits whose ``last_visit_ts`` falls
    inside this window are considered.
n : int, optional (default=3)
    Number of locations to return.

Returns
-------
list[str]
    The *n* location IDs ordered by descending visit frequency.
"""
    G = _load_graph()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    def score(node_data):
        last = node_data.get("last_visit_ts")
        if last and isinstance(last, datetime):
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last >= cutoff:
                return node_data.get("visits_30d", 0)
        return 0

    ranked = sorted(((nid, score(d)) for nid, d in G.nodes(data=True)), key=lambda x: x[1], reverse=True)
    return [nid for nid, _ in ranked[:n]]


@mcp.tool()
def next_location(
    current_place: str,
    weekday: int | None = None,
    hour: int | None = None,
    top_k: int = 3,
) -> List[Tuple[str, float]]:
    """Predict the most likely next stops starting from a given place and time.

Parameters
----------
current_place : str
    Location ID representing the user’s current position.
weekday : int, optional
    Day of week in the range 0=Monday … 6=Sunday.  If omitted the server uses
    the current UTC weekday.
hour : int, optional
    Hour of day (24-hour clock).  If omitted the current UTC hour is used.
top_k : int, optional (default=3)
    Maximum number of suggested destination IDs to return.

Returns
-------
list[tuple[str, float]]
    Tuples of ``(place_id, score)`` ordered by descending likelihood.
"""
    G = _load_graph()
    if current_place not in G:
        raise ValueError("Unknown current_place")

    if weekday is None or hour is None:
        now = datetime.now(timezone.utc)
        weekday = now.weekday()
        hour = now.hour
    bucket = f"{weekday}_{hour}"

    candidates: List[Tuple[str, float]] = []
    for _, dst, data in G.out_edges(current_place, data=True):
        base = float(data.get("score", 0))
        bucket_bonus = data.get("time_buckets", {}).get(bucket, 0)
        score = base + 0.1 * bucket_bonus
        candidates.append((dst, score))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:top_k]


@mcp.tool()
def top_locations_weekday(weekday: int, n: int = 5) -> List[Tuple[str, int]]:
    """List the top *n* destination locations for a specific weekday.

Parameters
----------
weekday : int
    Day of week (0=Monday … 6=Sunday).
n : int, optional (default=5)
    Number of locations to return.

Returns
-------
list[tuple[str, int]]
    Tuples ``(place_id, transition_count)`` ranked by popularity.
"""
    G = _load_graph()
    prefix = f"{weekday}_"
    dest_counts: Dict[str, int] = {}
    for _, dst, data in G.edges(data=True):
        for bucket, cnt in data.get("time_buckets", {}).items():
            if bucket.startswith(prefix):
                dest_counts[dst] = dest_counts.get(dst, 0) + cnt
    ranked = sorted(dest_counts.items(), key=lambda x: x[1], reverse=True)[:n]
    return ranked


@mcp.tool()
def top_routes_weekday(weekday: int, n: int = 5) -> List[Tuple[str, int]]:
    """Return the most frequent transition edges for a specified weekday.

Parameters
----------
weekday : int
    Day of week (0=Monday … 6=Sunday).
n : int, optional (default=5)
    Number of routes to return.

Returns
-------
list[tuple[str, int]]
    Tuples ``("src->dst", count)`` sorted by descending count.
"""
    G = _load_graph()
    prefix = f"{weekday}_"
    route_counts: Dict[str, int] = {}
    for src, dst, data in G.edges(data=True):
        total = sum(cnt for bucket, cnt in data.get("time_buckets", {}).items() if bucket.startswith(prefix))
        if total > 0:
            route_counts[f"{src}->{dst}"] = total
    ranked = sorted(route_counts.items(), key=lambda x: x[1], reverse=True)[:n]
    return ranked


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------



def main() -> None:
    """CLI entry-point to run the FastMCP server with custom bind options."""
    parser = argparse.ArgumentParser(description="Run the Location Profile MCP server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--path", default="/mcp", help="Bind path (default: /mcp)")
    parser.add_argument("--log-level", default="info", help="Log level (default: info)")
    args = parser.parse_args()

    #mcp.run(transport="http", host=args.host, port=args.port, path=args.path, log_level=args.log_level)
    mcp.run(transport="streamable-http")

    print(f"MCP server running on http://{args.host}:{args.port}{args.path}")


if __name__ == "__main__":
    main()
