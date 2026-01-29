import json
import re
import os

def load_cache(filepath):
    print(f"Loading transaction cache from {filepath}...")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # The structure is {"transactions": { "txid": {...}, ... }}
            return data.get('transactions', {})
    except Exception as e:
        print(f"Error loading cache: {e}")
        return {}

def get_edge_amounts(transactions):
    print("Calculating edge amounts from transactions...")
    # Map (from_addr, to_addr) -> amount_sompi
    edge_amounts = {}
    
    count = 0
    for tx in transactions.values():
        count += 1
        senders = set()
        if tx.get('inputs'):
            for inp in tx['inputs']:
                # The field for address in inputs might be 'previous_outpoint_address' 
                # or just 'address'. If None, look up the previous transaction.
                addr = inp.get('previous_outpoint_address') or inp.get('address')
                
                if not addr and 'previous_outpoint_hash' in inp:
                    # Fallback: Resolve via previous transaction
                    prev_hash = inp['previous_outpoint_hash']
                    # Index might be int or string digit
                    prev_idx = inp.get('previous_outpoint_index')
                    
                    if prev_hash in transactions and prev_idx is not None:
                        try:
                            prev_idx = int(prev_idx)
                            prev_tx = transactions[prev_hash]
                            if prev_tx.get('outputs') and len(prev_tx['outputs']) > prev_idx:
                                addr = prev_tx['outputs'][prev_idx].get('script_public_key_address')
                        except (ValueError, IndexError):
                            pass

                if addr:
                    senders.add(addr)
        
        # Collect outputs
        outputs = []
        if tx.get('outputs'):
            for out in tx['outputs']:
                # The field for address in outputs might be 'script_public_key_address'
                addr = out.get('script_public_key_address') or out.get('address')
                amt = out.get('amount')
                if addr and amt is not None:
                    # amount is string or int in JSON? Usually string in Kaspa JSONs to avoid overflow, or int.
                    # We cast to int safely.
                    try:
                        outputs.append((addr, int(amt)))
                    except:
                        pass
        
        # Attribute flow: Assume All Senders -> All Outputs
        # Aggregation logic: Sum up the amounts destined for each receiver
        # This simplifies the flow model but works for "Volume transferred to X"
        for s in senders:
            for r, amt in outputs:
                pair = (s, r)
                if pair not in edge_amounts:
                    edge_amounts[pair] = 0
                edge_amounts[pair] += amt
                
        if count % 1000 == 0:
            print(f"Processed {count} transactions...")
            
    return edge_amounts

def format_amount(sompi):
    # 1 KAS = 100,000,000 sompi
    if sompi == 0:
        return "0 KAS"
        
    kas = sompi / 100000000.0
    
    if kas >= 1000000:
        return f"{kas/1000000:.2f}M KAS"
    elif kas >= 1000:
        return f"{kas/1000:.2f}k KAS"
    else:
        return f"{kas:.2f} KAS"

def main(filename):
    print(f"Processing Graph HTML: {filename}")
    
    # 1. Load Transaction Cache
    # Assumes valid cache file in current directory or absolute path
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transaction_cache.txt")
    if not os.path.exists(cache_path):
        print(f"Cache file not found at {cache_path}")
        # Try current working directory
        cache_path = "transaction_cache.txt"
    
    transactions = load_cache(cache_path)
    if not transactions:
        print("No transactions loaded. Cannot calculate amounts.")
        # Proceeding anyway? We might want to just proceed with 0 amounts to not break the tool 
        # but the user asked us to use the cache.
    
    edge_map = get_edge_amounts(transactions)
    print(f"Calculated amounts for {len(edge_map)} edges.")

    # 2. Read HTML Content
    with open(filename, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # 3. Find and Parse 'edges' variable in HTML
    # We look for: edges = new vis.DataSet([...]);
    # Using specific regex keying on the variable name "edges"
    pattern = r'(edges\s*=\s*new\s+vis\.DataSet\(\s*)(\[.*?\])(\s*\);)'
    match = re.search(pattern, html_content, re.DOTALL)
    
    if not match:
        print("ERROR: Could not find 'edges = new vis.DataSet([...])' in HTML.")
        return

    json_str = match.group(2)
    try:
        edges_data = json.loads(json_str)
        print(f"Found {len(edges_data)} edges in HTML.")
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse edges JSON from HTML: {e}")
        return
        
    # 4. Enrich edges with Amounts and IDs
    for i, edge in enumerate(edges_data):
        # Assign ID for VisJS update mechanism
        edge['id'] = i 
        
        s = edge.get('from')
        r = edge.get('to')
        
        # Fetch amount from our calculated map
        amount_sompi = edge_map.get((s, r), 0)
        formatted_amount = format_amount(amount_sompi)
        
        # Store metadata for toggling
        edge['label_tx'] = edge.get('label', '')
        edge['label_amount'] = formatted_amount
        
        # Note: We do NOT change 'label' here, so it starts with Transaction Count (default)
        
    # 5. Inject new Edges JSON back into HTML
    new_edges_json = json.dumps(edges_data)
    # Reconstruct the string: prefix + new_json + suffix
    new_edges_declaration = match.group(1) + new_edges_json + match.group(3)
    
    # Replace in content
    # We only replace the MATCHED part
    new_html_content = html_content[:match.start()] + new_edges_declaration + html_content[match.end():]
    
    # 6. Inject JS Logic (Toggle + Popup)
    # Toggle Button HTML + Script
    injection_html = """
    <!-- Custom Controls Injected by UIKaspaGraph.py -->
    
    <!-- Top Right Controls: Toggle + Layer Buttons -->
    <div id="rightControls" style="position: fixed; top: 20px; right: 20px; z-index: 9999; display: flex; flex-direction: column; align-items: flex-end; gap: 10px;">
        <button id="toggleBtn" onclick="toggleEdgeLabels()" 
                style="padding: 12px 24px; font-size: 16px; font-weight: bold; background-color: #2196F3; color: white; border: none; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.3); transition: background-color 0.3s; width: 100%;">
            Afficher Montants
        </button>
        
        <div id="layerButtons" style="display: flex; flex-direction: column; gap: 8px; align-items: flex-end; width: 100%;">
            <button onclick="filterLayers(1)" style="padding: 10px 15px; font-size: 14px; background-color: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer; box-shadow: 0 2px 4px rgba(0,0,0,0.2); width: 100%; text-align: center;">Afficher Cercles 0 à 1</button>
            <button onclick="filterLayers(2)" style="padding: 10px 15px; font-size: 14px; background-color: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer; box-shadow: 0 2px 4px rgba(0,0,0,0.2); width: 100%; text-align: center;">Afficher Cercles 0 à 2</button>
            <button onclick="filterLayers(3)" style="padding: 10px 15px; font-size: 14px; background-color: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer; box-shadow: 0 2px 4px rgba(0,0,0,0.2); width: 100%; text-align: center;">Afficher Cercles 0 à 3</button>
            <button onclick="filterLayers(100)" style="padding: 10px 15px; font-size: 14px; background-color: #607D8B; color: white; border: none; border-radius: 5px; cursor: pointer; box-shadow: 0 2px 4px rgba(0,0,0,0.2); width: 100%; text-align: center;">Tous</button>
        </div>
    </div>

    <!-- Top Left Legend -->
    <div id="legendContainer" style="position: fixed; top: 20px; left: 20px; z-index: 9999; background-color: rgba(30, 30, 30, 0.95); padding: 20px; border-radius: 12px; color: white; font-family: 'Segoe UI', Arial, sans-serif; font-size: 16px; box-shadow: 0 4px 8px rgba(0,0,0,0.4); min-width: 200px;">
        <h4 style="margin: 0 0 15px 0; border-bottom: 2px solid #555; padding-bottom: 8px; font-size: 18px; text-align: center; text-transform: uppercase; letter-spacing: 1px;">Légende</h4>
        
        <div style="display: flex; align-items: center; margin-bottom: 10px;">
            <span style="width: 24px; height: 24px; background-color: #0000FF; display: inline-block; margin-right: 12px; border-radius: 4px; border: 1px solid #fff; box-shadow: 0 0 5px #0000FF;"></span>
            <span>Cible (Target)</span>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 10px;">
            <span style="width: 24px; height: 24px; background-color: #FFA500; display: inline-block; margin-right: 12px; border-radius: 4px; border: 1px solid #fff; box-shadow: 0 0 5px #FFA500;"></span>
            <span>Cercle 1</span>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 10px;">
            <span style="width: 24px; height: 24px; background-color: #FFFF00; display: inline-block; margin-right: 12px; border-radius: 4px; border: 1px solid #fff; box-shadow: 0 0 5px #FFFF00;"></span>
            <span>Cercle 2</span>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <span style="width: 24px; height: 24px; background-color: #800080; display: inline-block; margin-right: 12px; border-radius: 4px; border: 1px solid #fff; box-shadow: 0 0 5px #800080;"></span>
            <span>Cercle 3</span>
        </div>
    </div>

    <script type="text/javascript">
        var showingAmount = false;
        
        function toggleEdgeLabels() {
            showingAmount = !showingAmount;
            var btn = document.getElementById('toggleBtn');
            var updateArray = [];
            
            // Get all edges from the DataSet
            var allEdges = edges.get(); 
            
            allEdges.forEach(function(edge) {
                // Use the pre-calculated labels we added
                if (showingAmount) {
                     updateArray.push({id: edge.id, label: edge.label_amount});
                } else {
                     updateArray.push({id: edge.id, label: edge.label_tx});
                }
            });
            
            // Bulk update for performance
            edges.update(updateArray);
            
            // Update Button State
            if (showingAmount) {
                btn.innerText = "Afficher Transactions";
                btn.style.backgroundColor = "#FF9800"; 
            } else {
                btn.innerText = "Afficher Montants";
                btn.style.backgroundColor = "#2196F3"; 
            }
        }
        
        function filterLayers(maxLayer) {
            // Mapping colors to layers based on user requirements
            var colorToLayer = {
                '#0000FF': 0, // Blue = Target
                '#FFA500': 1, // Orange = C1
                '#FFFF00': 2, // Yellow = C2
                '#800080': 3, // Purple = C3
                '#00FF00': 4, // Green
                '#00FFFF': 5  // Cyan
            };

            var allNodes = nodes.get();
            var updateNodeArray = [];
            
            allNodes.forEach(function(node) {
                var c = (node.color && node.color.background) ? node.color.background.toUpperCase() : 
                        (node.color ? String(node.color).toUpperCase() : "");
                
                // Handle case where color is object or string
                // Sometimes VisJS nodes.color is a string, sometimes object {background: ..., border: ...}
                // In the HTML generated by pyvis/vis, it's often a string at init, but let's be safe.
                
                var layer = 100; // Default: show for 'Tous' or unknown
                
                // Exact match from map
                if (colorToLayer.hasOwnProperty(c)) {
                    layer = colorToLayer[c];
                }
                
                if (layer <= maxLayer) {
                     updateNodeArray.push({id: node.id, hidden: false});
                } else {
                     updateNodeArray.push({id: node.id, hidden: true});
                }
            });
            
            nodes.update(updateNodeArray);
            
            // Also update edges? 
            // VisJS usually hides edges connected to hidden nodes automatically if physics is enabled or not.
            // But explicitly hiding edges might be cleaner if Vis doesn't do it fully.
            // Actually, VisJS documentation says edges connected to hidden nodes are hidden.
            // Let's trust VisJS first.
        }
    
        // Network Click Event for Popup (Original Logic Preserved)
        if (typeof network !== 'undefined') {
            network.on("click", function(params) {
                if (params.nodes.length > 0) {
                    var nodeId = params.nodes[0];
                    var address = nodeId;
                    
                    // Remove existing popup
                    var existingPopup = document.getElementById('addressPopup');
                    if (existingPopup) {
                        existingPopup.remove();
                    }
                    
                    // Create Popup
                    var popup = document.createElement('div');
                    popup.id = 'addressPopup';
                    popup.style.position = 'fixed';
                    popup.style.top = '50%';
                    popup.style.left = '50%';
                    popup.style.transform = 'translate(-50%, -50%)';
                    popup.style.backgroundColor = '#333';
                    popup.style.padding = '20px';
                    popup.style.borderRadius = '10px';
                    popup.style.zIndex = '10000';
                    popup.style.boxShadow = '0 4px 6px rgba(0,0,0,0.3)';
                    popup.style.color = 'white';
                    popup.style.fontFamily = 'Arial, sans-serif';
                    popup.style.minWidth = '300px';
                    popup.style.textAlign = 'center';
                    
                    popup.innerHTML = `
                        <h3 style="margin-top: 0; word-break: break-all; color: #fff;">Adresse details</h3>
                        <p style="font-size: 12px; word-break: break-all; background: #222; padding: 10px; border-radius: 5px; color: #ddd;">${address}</p>
                        <button onclick="window.open('https://explorer.kaspa.org/addresses/${address}', '_blank')" 
                                style="width: 100%; padding: 10px; margin: 5px 0; cursor: pointer; background-color: #4CAF50; color: white; border: none; border-radius: 5px; font-size: 14px;">
                            Voir sur Kaspa Explorer
                        </button>
                        <button onclick="navigator.clipboard.writeText('${address}').then(() => { alert('Adresse copiée !'); });" 
                                style="width: 100%; padding: 10px; margin: 5px 0; cursor: pointer; background-color: #2196F3; color: white; border: none; border-radius: 5px; font-size: 14px;">
                            Copier l'adresse
                        </button>
                        <button onclick="document.getElementById('addressPopup').remove()" 
                                style="width: 100%; padding: 10px; margin: 5px 0; cursor: pointer; background-color: #f44336; color: white; border: none; border-radius: 5px; font-size: 14px;">
                            Fermer
                        </button>
                    `;
                    
                    document.body.appendChild(popup);
                }
            });
        }
    </script>
    """
    
    # Inject before </body>
    if '</body>' in new_html_content:
        new_html_content = new_html_content.replace('</body>', injection_html + '\n</body>')
    else:
        # Fallback if no body tag found
        new_html_content += injection_html

    # 7. Write Output
    output_filename = filename.replace(".html", "")
    if output_filename.endswith("TESTMODIF"):
        final_output = output_filename + ".html"
    else:
        final_output = output_filename + "TESTMODIF.html"
        
    with open(final_output, 'w', encoding='utf-8') as f:
        f.write(new_html_content)
        
    print(f"Success! Saved modified interface to: {final_output}")

if __name__ == "__main__":
    # Default input file as requested
    file_input = "NewAPIGraph_cercle4.html"
    main(file_input)