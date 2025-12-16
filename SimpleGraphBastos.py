import requests
from pyvis.network import Network
import argparse
import math
import os

# Configuration
DEFAULT_ADDRESS = "kaspa:qqssy8x2stwk6x7trmw56m8rwfkwul70rpqxrvv789mxqz73pdny2sprry82x"
DEFAULT_API_KEY = "kdp_722ad9825ff1144878629812d69609b0e3084323ec6d4299ffd4cbd4b23a0f2b"
DEFAULT_NB_CERCLES = 2

global API_KEY
API_KEY = DEFAULT_API_KEY

class SimpleGraph:
    def __init__(self):
        self._nodes = set()
        self._edges = []
        self._predecessors = {}

    def add_node(self, node):
        self._nodes.add(node)
        if node not in self._predecessors:
            self._predecessors[node] = set()

    def add_edge(self, u, v, weight=1):
        self.add_node(u)
        self.add_node(v)
        self._edges.append((u, v, weight))
        self._predecessors[v].add(u)

    @property
    def nodes(self):
        return list(self._nodes)
    
    @property
    def edges(self):
        return self._edges

    def predecessors(self, node):
        return list(self._predecessors.get(node, []))

    def __contains__(self, node):
        return node in self._nodes

def make_graph(G, address, addresses=None):
    url = f"https://api.kas.fyi/v1/addresses/{address}/transactions?accepted_only=true"
    headers = {"x-api-key": API_KEY}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Request Failed for {address}: {e}")
        return G, []
    except ValueError:
        print(f"Invalid JSON response for {address}")
        return G, []

    if "transactions" not in data:
        print(f"Key 'transactions' not found in response for {address}. Response: {data}")
        return G, []

    transac={}
    for transactions in data["transactions"]:
        if "inputs" not in transactions or "outputs" not in transactions:
            continue
            
        for input in transactions["inputs"]:
            if "previousOutput" not in input: 
                continue
            incomeAddress=input["previousOutput"]["scriptPublicKeyAddress"]
            if incomeAddress not in transac:
                transac[incomeAddress]={}
            for output in transactions["outputs"]:
                outcomeAddress=output["scriptPublicKeyAddress"]
                if outcomeAddress not in transac[incomeAddress]:
                    transac[incomeAddress][outcomeAddress]=1
                else:
                    transac[incomeAddress][outcomeAddress]+=1
    if addresses is None:
        addresses=[]
    found_addresses = [] 
    for income in transac:
        if income not in addresses:
            addresses.append(income)
            found_addresses.append(income)
        for outcome in transac[income]:
            G.add_edge(income[:15],outcome[:15],weight=transac[income][outcome])
            if outcome not in addresses:
                addresses.append(outcome)
                found_addresses.append(outcome)

    return G, found_addresses


COLOR=[
        "blue",
        "red",
        "orange",
        "yellow",
        "black"
    ]

def main():
    parser = argparse.ArgumentParser(description="Kaspa Transaction Graph")
    parser.add_argument("--address", type=str, default=DEFAULT_ADDRESS, help="Address Kaspa")
    parser.add_argument("--APIkey", type=str, default=DEFAULT_API_KEY, help="API key")
    parser.add_argument("--nbCercles", type=int, default=DEFAULT_NB_CERCLES, help="Nombre de cercles")
    args = parser.parse_args()

    start_addr = args.address
    nb_cercles = args.nbCercles
    global API_KEY
    API_KEY = args.APIkey

    # Warn if using placeholder key
    if API_KEY == "APIKey":
        print("WARNING: Using placeholder 'APIKey'. API calls will likely fail. Please provide a valid key via --APIkey or edit the DEFAULT_API_KEY constant.")
    
    print(f"Starting analysis for {start_addr}")
    print(f"Targeting {nb_cercles} circles.")

    G = SimpleGraph()
    
    # Initialization
    start_node_short = start_addr[:15]
    G.add_node(start_node_short)
    
    # BFS State
    current_check_addrs = [start_addr]
    visited_addrs = {start_addr}
    
    # Store nodes available at each step [step0_nodes, step1_nodes, ...]
    layers_nodes = [set([start_node_short])]
    
    for i in range(nb_cercles):
        print(f"Fetching Circle {i+1}...")
        next_check_addrs = []
        
        # We process all addresses in the current layer
        for addr in current_check_addrs:
            G, found = make_graph(G, addr)
            
            for f in found:
                if f not in visited_addrs:
                    visited_addrs.add(f)
                    next_check_addrs.append(f)
        
        layers_nodes.append(set(G.nodes))
        
        current_check_addrs = next_check_addrs
        if not current_check_addrs:
            print("No more connections found.")
            break
            
    print(f"Graph construction complete. Nodes: {len(G.nodes)}, Edges: {len(G.edges)}")
    
    # Visualization
    print("Computing layout...")
    
    fixed_nodes = set()
    fixed_pos = {}
    
    # 1. Fix Center (Circle 0)
    if start_node_short in G:
        fixed_nodes.add(start_node_short)
        fixed_pos[start_node_short] = (0, 0)
        
    # 2. Fix Concentric Circles (Layers 1+)
    MIN_R_FIRST = 200.0
    MIN_DR = 100.0
    SPACING_ARC = 50.0
    
    current_radius = 0.0
    
    for lvl in range(1, len(layers_nodes)):
        layer_nodes = list(layers_nodes[lvl] - layers_nodes[lvl-1])
        N_nodes = len(layer_nodes)
        
        if N_nodes == 0:
            continue
            
        if lvl == 1:
            target_min_r = MIN_R_FIRST
        else:
            target_min_r = current_radius + MIN_DR
            
        required_circumference = N_nodes * SPACING_ARC
        required_r_spacing = required_circumference / (2 * math.pi)
        
        R = max(target_min_r, required_r_spacing)
        current_radius = R

        # Sort nodes to untangle edges (place near parents)
        node_angles = []
        for node in layer_nodes:
            parents = G.predecessors(node)
            valid_parents = [p for p in parents if p in fixed_pos]
            
            if valid_parents:
                p_angles = []
                for p in valid_parents:
                    px, py = fixed_pos[p]
                    p_angles.append(math.atan2(py, px))
                avg_angle = sum(p_angles) / len(p_angles)
            else:
                avg_angle = 0
            
            node_angles.append((node, avg_angle))
        
        node_angles.sort(key=lambda x: x[1])
        sorted_layer_nodes = [x[0] for x in node_angles]
        
        angle_step = 2 * math.pi / N_nodes
        
        for i, node in enumerate(sorted_layer_nodes):
            angle = i * angle_step
            fixed_nodes.add(node)
            fixed_pos[node] = (math.cos(angle) * R, math.sin(angle) * R)

    print("Generating PyVis Network...")
    net = Network(height="900px", width="100%", bgcolor="#222222", font_color="white", select_menu=True)
    
    # Enable Physics for better node distribution, but starting from our calculated positions
    net.barnes_hut(gravity=-10000, central_gravity=0.3, spring_length=200, spring_strength=0.01, damping=0.09, overlap=0)
    
    # Add nodes
    for node in G.nodes:
        # Determine color
        color_idx = 0
        for lvl, nodes in enumerate(layers_nodes):
            if node in nodes:
                color_idx = lvl
                break
        c = COLOR[color_idx % len(COLOR)]
        
        # Position
        opts = {'color': c}
        if node in fixed_pos:
            opts['x'] = fixed_pos[node][0]
            opts['y'] = fixed_pos[node][1]
            # We allow physics to refine the layout
            opts['physics'] = True 
        else:
             pass
             
        net.add_node(node, label=node, title=node, **opts)

    # Add edges
    for u, v, w in G.edges:
        # Added label=str(w) to display transaction count on the arrow
        net.add_edge(u, v, value=w, title=f"Weight: {w}", label=str(w), arrowStrikethrough=False)

    output_file = "kaspa_graph.html"
    net.save_graph(output_file)
    print(f"Visualization saved to {os.path.abspath(output_file)}")

if __name__=="__main__":
    main()