# Location Profiler

An agent that answers questions based on your location history profile using MCP tools. It can also predict your next destination or help to plan your trip.

It is built on top of a location-time graph, which is a dynamic graph that tracks your location history and transition statistics.

The location-time graph is built with a lightweight Python utility that turns daily stay-point CSV logs into a dynamic **location–time graph**, where nodes represent places you visit, edges represent transitions between places, and both are automatically decayed over time so that the graph always reflects your *recent* behaviour. 
Optionally, the graph can be visualised or pruned to physically remove inactive nodes/edges.

---

## Features

* 🗺 **Graph-based model** – Uses NetworkX directed graphs to track visit and transition statistics.
* ⏱ **Time-decay scoring** – Recent and frequent visits are scored higher than old, rare ones.
* 🧹 **Automatic pruning** – Mark or remove inactive nodes/edges with `--prune`.
* 📈 **Visualisation** – Dump a PNG showing active locations sized/coloured by score via `--show`.
* 🧪 **Test data generator** – Quickly create example CSV logs with `generate_test_data.py`.

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/2015xli/location_profiler.git
cd location_profiler

# 2. (Optional) create & activate a virtual environment
python -m venv .venv && source .venv/bin/activate

# 3. Install dependencies (Python ≥3.9)
pip install networkx matplotlib fastmcp fastapi uvicorn google-adk litellm[deepseek]
```

---

## Directory layout

```
location_profiler/
├── input_data/             # CSV stay-point logs (input examples)
│   └── 20250723_staypoints.csv
├── output_data/            # Generated output files
│   └── graph.pkl           # Pickled NetworkX graph (auto-created)
├── experiments/            # Experimental scripts and agents
│   ├── api_location_agent.py    # Example LLM agent querying MCP
│   ├── fastapi_location_server.py  # Legacy FastAPI server
│   ├── generate_test_data.py      # Test data generator (moved)
│   └── test_mcp.py                # MCP server test script
├── dump_graph/             # PNGs created when using --show
├── location_profiler.py    # Main CLI (graph updater / visualiser)
├── mcp_location_server.py  # FastMCP server (preferred API)
├── adk_location_agent/     # Google ADK agent implementation
|   ├── agent.py
|   └── run_agent.py
|   └── __init__.py
└── metadata.json           # Tracks last processing date
```

### Stay-point CSV format

Each input file must be named `YYYYMMDD_staypoints.csv` and contain the following header:

| column     | example value                 |
|------------|------------------------------|
| place_id   | `loc_home`                   |
| start_iso  | `2025-07-23T07:00:00`        |
| end_iso    | `2025-07-23T08:00:00`        |

You can generate three days of sample data like so:

```bash
python generate_test_data.py
```

---

## Usage

### Update the graph (default)

```bash
python location_profiler.py
```

The script will:
1. Load the existing graph (`graph.pkl`) and metadata (`metadata.json`).
2. Read **new** CSV files in `input_data/` (those newer than the last update).
3. Update visit/transition statistics with exponential decay.
4. Persist the graph and metadata.

You will see a message such as:

```
Graph updated through 2025-07-25 with 2 new files.
```

### Visualise the graph

```bash
python location_profiler.py --show
```

A PNG will be written to `dump_graph/location_graph_<yyyymmdd>.png` with:
* Node size & colour ∝ score (recent + frequent visits)
* Dashed edges for active transitions

### Prune inactive items

```bash
python location_profiler.py --prune
```

Inactive nodes/edges (no activity for `inactive_days_threshold` days **and** low 30-day count) are *deleted* instead of merely flagged.

You may combine flags:

```bash
python location_profiler.py --prune --show
```

---

### Run the MCP server

```bash
python mcp_location_server.py --host 0.0.0.0 --port 8000
```

The server exposes an MCP endpoint (default `http://0.0.0.0:8000/mcp`) that can be queried via the `fastmcp` Python client or any HTTP tool.

---

### Ask questions via the LLM agent

Use the Google ADK agent to ask questions about your location profile and predict your next destination.

```bash
export DEEPSEEK_API_KEY="<your-key>"
adk run adk_location_agent
```

The agent selects the appropriate MCP tool, fetches JSON data, and asks an LLM (DeepSeek via LiteLLM) to craft a natural-language answer.

For practice purpose, it also includes an async agent implementation that can be run with:
```bash
export DEEPSEEK_API_KEY="<your-key>"
python adk_location_agent/run_agent.py --query "Where should I go next?"
```

---

## Configuration

Adjust behaviour via the `LocationGraphUpdater` constructor in `location_profiler.py`:

* `decay_rate` – Exponential decay applied per run (default `0.95`).
* `visit_threshold` – Minimum 30-day count before a node/edge is considered active.
* `inactive_days_threshold` – Days of inactivity before something is marked inactive.
* `graph_path`, `meta_path`, `data_dir` – Storage locations.

---

## Extending

* Integrate with external location APIs (e.g. Google Location History) by writing exporters to the required CSV format.

