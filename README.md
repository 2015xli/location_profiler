# Agent of Location Profiler

The repo is a simple tutorial to demonstrate how to combine the power of knowledge graph, MCP tools and LLM agents.

It is an agent that answers questions based on your location history profile It can also predict your next destination or help to plan your trip. 

The repo basically has three parts: 

**A location profiler**, which is to build a location-time graph, a dynamic graph that tracks your location history and transition statistics.

**A MCP server**, which is to provide a FastMCP server (preferred API) on top of the location-time graph that can be queried via the MCP HTTP client or any HTTP tool.

**An LLM agent**, which is to answer questions based on the location-time graph via the MCP server interface.

The location profiler turns daily stay-point CSV logs into a dynamic **location–time graph**, where nodes represent places you visit, edges represent transitions between places, and both are automatically decayed over time so that the graph always reflects your *recent* behaviour. Optionally, the graph can be visualised or pruned to physically remove inactive nodes/edges.

The MCP server provides various tools to query the location-time graph, such as listing resources, reading resources, top locations, next location, top locations weekday, top routes weekday, etc., all based on the location-time graph built by the location profiler.

The LLM agent uses Google ADK to answer questions based on the MCP server interface. It has an agent implementation that can be accessed with adk web or adk run. An agent runner implementation is also provided to run and manage interactive session with the agent and lifecycle.

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/2015xli/location_profiler.git
cd location_profiler

# 2. (Optional) create & activate a virtual environment
python -m venv .venv && source .venv/bin/activate

# 3. Install dependencies (Only tried with Python 3.13, so suggest to use Python>=3.13)
pip install google-adk litellm networkx matplotlib fastmcp fastapi uvicorn 
```

---

## Directory layout

```
location_profiler/
├── location_profiler.py    # Location graph builder / updater / visualiser
├── mcp_location_server.py  # FastMCP server (preferred API)
├── adk_location_agent/     # Google ADK agent implementation
│   ├── agent.py
│   └── run_agent.py
│   └── __init__.py
├── input_data/             # CSV stay-point logs (input examples)
│   └── 20250723_staypoints.csv
├── output_data/            # Generated output files
│   ├── graph.pkl           # Pickled NetworkX graph (auto-created)
│   └── metadata.json       # Tracks last processing date
├── dump_graph/             # PNGs created when using --show
└── experiments/            # Experimental scripts and agents
    ├── api_location_agent.py    # Example LLM agent querying MCP
    ├── fastapi_location_server.py  # Legacy FastAPI server
    ├── generate_test_data.py      # Test data generator (moved)
    └── test_mcp.py                # MCP server test script
```

---
## Usage

### 1. Build the location-time graph

(You can skip this step if you only want to try the MCP server and LLM agent, since the repo include a pre-built graph.)

#### Features

- 🗺 **Graph-based model** – Uses NetworkX directed graphs to track visit and transition statistics.
- ⏱ **Time-decay scoring** – Recent and frequent visits are scored higher than old, rare ones.
- 🧹 **Automatic pruning** – Mark or remove inactive nodes/edges with `--prune`.
- 📈 **Visualisation** – Dump a PNG showing active locations sized/coloured by score via `--show`.
- 🧪 **Test data generator** – Quickly create example CSV logs with `generate_test_data.py`.

**Prepare the input data for location profiler**

Each input file must be named `YYYYMMDD_staypoints.csv` under input_data/and contain the following header:

| column     | example value                 |
|------------|------------------------------|
| place_id   | `loc_home`                   |
| start_iso  | `2025-07-23T07:00:00`        |
| end_iso    | `2025-07-23T08:00:00`        |

You can generate three days of sample data like so:

```bash
python experiments/generate_test_data.py
```

** Build/Update the graph**

```bash
python location_profiler.py
```

The script will:
1. Load the existing graph (`graph.pkl`) and metadata (`metadata.json`). If the graph doesn't exist, it will be created.
2. Read **new** CSV files in `input_data/` (those newer than the last update).
3. Update visit/transition statistics with exponential decay.
4. Persist the graph and metadata.

You will see a message such as:

```
Graph updated through 2025-07-25 with 2 new files.
```

** Visualise the graph**

```bash
python location_profiler.py --show
```

A PNG will be written to `dump_graph/location_graph_<yyyymmdd>.png` with:
* Node size & colour ∝ score (recent + frequent visits)
* Dashed edges for active transitions

** Prune inactive items**

```bash
python location_profiler.py --prune
```

Inactive nodes/edges (no activity for `inactive_days_threshold` days **and** low 30-day count) are *deleted* instead of merely flagged.

You may combine flags:

```bash
python location_profiler.py --prune --show
```

---

### 2. Run the MCP server

```bash
python mcp_location_server.py --host 0.0.0.0 --port 8000
```

The server exposes an MCP endpoint (default `http://0.0.0.0:8000/mcp`) that can be queried via the `fastmcp` Python client or any HTTP tool.

---

### 3. Ask questions via the LLM agent

Use the Google ADK agent to ask questions about your location profile and predict your next destination.
The code use deepseek API with LiteLLM. You can choose your LLM API provider and set the API key environment variable accordingly, e.g. The code uses `DEEPSEEK_API_KEY` by default. After that, you can run the agent with:

```bash
adk run adk_location_agent
```
or, if you want to run it in web mode,
```bash
adk web 
```

The agent selects the appropriate MCP tool, fetches JSON data, and asks an LLM (DeepSeek via LiteLLM) to craft a natural-language answer.

For practice purpose, it also includes an agent runner implementation so that you don't need to rely on Google ADK to run the agent. You can run it with:

```bash
python adk_location_agent/run_agent.py
```
or

```bash
python adk_location_agent/run_agent.py --query "Where should I go next from gym?"
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

