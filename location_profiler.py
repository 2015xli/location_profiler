import os
import json
import argparse
from datetime import datetime
import networkx as nx
import matplotlib.pyplot as plt
import pickle
import csv

class LocationGraphUpdater:
    def __init__(self, 
                 output_dir="output_data",
                 input_dir="input_data",
                 decay_rate=0.95,
                 visit_threshold=3,
                 inactive_days_threshold=60):
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, "dump_graph"), exist_ok=True)
        
        # Set paths relative to output directory
        self.graph_path = os.path.join(output_dir, "graph.pkl")
        self.meta_path = os.path.join(output_dir, "metadata.json")
        self.dump_graph_dir = os.path.join(output_dir, "dump_graph")
        self.data_dir = os.path.join(input_dir, "staypoints.csv")
        self.decay_rate = decay_rate
        self.visit_threshold = visit_threshold
        self.inactive_days_threshold = inactive_days_threshold
        
        # Load or initialize graph and metadata
        self._init_storage()
        self.load_graph()
        self.load_metadata()
    
    def _init_storage(self):
        if not os.path.exists(self.graph_path):            
            with open(self.graph_path, 'wb') as f:
                pickle.dump(nx.DiGraph(), f, pickle.HIGHEST_PROTOCOL)

        if not os.path.exists(self.meta_path):
            with open(self.meta_path, "w") as f:
                json.dump({"last_update": None}, f)
    
    def load_graph(self):
        # Load or init on empty/corrupt
        if not os.path.exists(self.graph_path) or os.path.getsize(self.graph_path) == 0:
            self.graph = nx.DiGraph()
            return
        try:
            with open(self.graph_path, 'rb') as f:
                self.graph = pickle.load(f)
        except (EOFError, pickle.UnpicklingError):
            self.graph = nx.DiGraph()
    
    def load_metadata(self):
        with open(self.meta_path, "r") as f:
            self.meta = json.load(f)
        last = self.meta.get("last_update")
        self.last_update = datetime.fromisoformat(last) if last else None
    
    def load_data(self):
        files = sorted(f for f in os.listdir(self.data_dir) if f.endswith("staypoints.csv"))
        new_files = []
        for fname in files:
            date_part = fname.split("_")[0]
            file_date = datetime.strptime(date_part, "%Y%m%d")
            if self.last_update is None or file_date > self.last_update:
                new_files.append((file_date, fname))
        
        daily_data = []
        for file_date, fname in new_files:
            path = os.path.join(self.data_dir, fname)
            with open(path, newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                day_staypoints = []
                for row in reader:
                    day_staypoints.append((
                        row["place_id"],
                        datetime.fromisoformat(row["start_iso"]),
                        datetime.fromisoformat(row["end_iso"])
                    ))
                daily_data.append((file_date, day_staypoints))
        
        return daily_data
    
    def update_graph(self, daily_data):
        # Update nodes and edges, mark active/inactive
        for file_date, staypoints in daily_data:
            for place_id, start, end in staypoints:
                if not self.graph.has_node(place_id):
                    self.graph.add_node(place_id,
                                        visits_30d=0.0,
                                        visits_365d=0.0,
                                        last_visit_ts=None,
                                        score=0.0,
                                        active=True)
                node = self.graph.nodes[place_id]
                
                # Decay stats
                node["visits_30d"] *= self.decay_rate
                node["visits_365d"] *= self.decay_rate
                # Update
                node["visits_30d"] += 1
                node["visits_365d"] += 1
                node["last_visit_ts"] = start
                node["active"] = True
                
                # Recompute score
                days_since = max(1, (file_date - node["last_visit_ts"]).days)
                recency = 1 / days_since
                freq_norm = node["visits_30d"] / 30
                node["score"] = 0.5 * freq_norm + 0.5 * recency
            
            for i in range(1, len(staypoints)):
                src, _, _ = staypoints[i-1]
                dst, ts, _ = staypoints[i]
                bucket = f"{ts.weekday()}_{ts.hour}"
                
                if not self.graph.has_edge(src, dst):
                    self.graph.add_edge(src, dst,
                                        transitions_30d=0.0,
                                        transitions_365d=0.0,
                                        last_transition_ts=None,
                                        time_buckets={},
                                        score=0.0,
                                        active=True)
                edge = self.graph[src][dst]
                
                # Decay
                edge["transitions_30d"] *= self.decay_rate
                edge["transitions_365d"] *= self.decay_rate
                # Update
                edge["transitions_30d"] += 1
                edge["transitions_365d"] += 1
                edge["last_transition_ts"] = ts
                edge["time_buckets"][bucket] = edge["time_buckets"].get(bucket, 0) + 1
                edge["active"] = True
                
                # Recompute score
                days_since = max(1, (file_date - edge["last_transition_ts"]).days)
                recency = 1 / days_since
                freq_norm = edge["transitions_30d"] / 30
                edge["score"] = 0.5 * freq_norm + 0.5 * recency
            
            self.last_update = file_date
        
        # Update metadata
        self.meta["last_update"] = self.last_update.isoformat()

    def prune_graph(self, prune=False):
        # Mark inactive nodes and edges
        for node, data in list(self.graph.nodes(data=True)):
            last = data.get("last_visit_ts")
            if last:
                days_since = (self.last_update - last).days
                if days_since > self.inactive_days_threshold and data["visits_30d"] < self.visit_threshold:
                    self.graph.nodes[node]["active"] = False
        for u,v,data in list(self.graph.edges(data=True)):
            last = data.get("last_transition_ts")
            if last:
                days_since = (self.last_update - last).days
                if days_since > self.inactive_days_threshold and data["transitions_30d"] < self.visit_threshold:
                    self.graph[u][v]["active"] = False

        # If prune flag, physically remove inactive
        if prune:
            print("Remove the inactive nodes and edges.")
            inactive_nodes = [n for n,d in self.graph.nodes(data=True) if not d.get('active')]
            self.graph.remove_nodes_from(inactive_nodes)
            inactive_edges = [(u,v) for u,v,d in self.graph.edges(data=True) if not d.get('active')]
            self.graph.remove_edges_from(inactive_edges)
    
    
    def persist_graph(self):
        with open(self.graph_path, 'wb') as f:
            pickle.dump(self.graph, f, pickle.HIGHEST_PROTOCOL)
        with open(self.meta_path, "w") as f:
            json.dump(self.meta, f)
    
    def show_graph(self):
        # Load date for file naming
        date_str = self.meta.get("last_update", datetime.now().isoformat())[:10].replace('-', '')
        fname = os.path.join(self.dump_graph_dir, f"location_graph_{date_str}.png")
        
        # Use current in-memory graph
        G = self.graph
        pos = nx.spring_layout(G, seed=42)
        plt.figure(figsize=(10,10))
        nx.draw_networkx_edges(G, pos, alpha=0.3)
        nx.draw_networkx_nodes(
            G, pos,
            nodelist=[n for n,d in G.nodes(data=True) if d.get('active')],
            node_size=[G.nodes[n]['score']*500 for n in G if G.nodes[n].get('active')],
            node_color=[G.nodes[n]['score'] for n in G if G.nodes[n].get('active')],
            cmap=plt.cm.plasma
        )
        nx.draw_networkx_edges(
            G, pos,
            edgelist=[(u,v) for u,v,d in G.edges(data=True) if d.get('active')],
            style='dashed', alpha=0.3
        )
        nx.draw_networkx_labels(G, pos, font_size=8)
        plt.axis('off')
        plt.title("Location-Time Graph")
        plt.tight_layout()
        plt.savefig(fname, dpi=300)
        print(f"Graph visualization saved to {fname}")

    def run(self, args):
        daily_data = self.load_data()
        if not daily_data:
            print("No new data to process.")
            if args.show:
                print("Show graph.")
                self.show_graph()
            return

        # Update 
        self.update_graph(daily_data)
        self.prune_graph(args.prune)
        self.persist_graph()
        print(f"Graph updated through {self.last_update.date()} with {len(daily_data)} new files.")

        if args.show:
            print("Show graph.")
            self.show_graph()

def parse_args():
    parser = argparse.ArgumentParser(description="Location Graph Updater")
    
    # Output and input configuration
    parser.add_argument('--output-dir', 
                      default="output_data",
                      help='Directory to store output files (default: output_data)')
    parser.add_argument('--input-dir', 
                      default="input_data",
                      help='Directory containing input CSV files (default: input_data)')
    
    # Graph behavior parameters
    parser.add_argument('--decay-rate', 
                      type=float, 
                      default=0.95,
                      help='Exponential decay rate for visit scores (default: 0.95)')
    parser.add_argument('--visit-threshold', 
                      type=int, 
                      default=3,
                      help='Minimum 30-day count for active nodes/edges (default: 3)')
    parser.add_argument('--inactive-days-threshold', 
                      type=int, 
                      default=60,
                      help='Days of inactivity before marking as inactive (default: 60)')
    
    # Action flags
    parser.add_argument('--show', 
                      action='store_true', 
                      help='Show (dump) the graph after updating')
    parser.add_argument('--prune', 
                      action='store_true', 
                      help='Physically remove inactive nodes/edges instead of just marking')
    
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    
    # Initialize updater with command line arguments
    updater = LocationGraphUpdater(
        output_dir=args.output_dir,
        input_dir=args.input_dir,
        decay_rate=args.decay_rate,
        visit_threshold=args.visit_threshold,
        inactive_days_threshold=args.inactive_days_threshold
    )
    
    updater.run(args)
