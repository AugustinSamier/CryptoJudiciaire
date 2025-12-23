import requests
from pyvis.network import Network
import argparse
import os
import math
import json

def make_graph(G, address, limit, allAddresses, transac, addresses=None):
    url = f"https://api.kas.fyi/v1/addresses/{address}/"
    headers = {"x-api-key": API_KEY}

    responseTag = requests.get(url + "tag", headers=headers)
    dataTag = responseTag.json()

    if "tag" in dataTag:
        print("Exchange platform", dataTag)
        return G, None, transac

    responseTransac = requests.get(url + f"transactions?limit={limit}", headers=headers)
    data = responseTransac.json()

    try:
        for transactions in data["transactions"]:
            tx_id = transactions.get("transactionId", "unknown")
            timestamp = transactions.get("blockTime", 0)
            
            for input in transactions["inputs"]:
                incomeAddress = input["previousOutput"]["scriptPublicKeyAddress"]
                amount = int(input["previousOutput"].get("amount", 0)) / 100000000  # Conversion en KAS
                
                if incomeAddress not in transac:
                    transac[incomeAddress] = {}
                    
                for output in transactions["outputs"]:
                    outcomeAddress = output["scriptPublicKeyAddress"]
                    out_amount = int(output.get("amount", 0)) / 100000000
                    
                    if outcomeAddress not in transac[incomeAddress]:
                        transac[incomeAddress][outcomeAddress] = {
                            'count': 0,
                            'total_amount': 0,
                            'amounts': [],
                            'timestamps': []
                        }
                    
                    transac[incomeAddress][outcomeAddress]['count'] += 1
                    transac[incomeAddress][outcomeAddress]['total_amount'] += out_amount
                    transac[incomeAddress][outcomeAddress]['amounts'].append(out_amount)
                    transac[incomeAddress][outcomeAddress]['timestamps'].append(timestamp)
        
        if addresses is None:
            addresses = []
        
        for income in transac:
            if income not in addresses and income not in allAddresses:
                addresses.append(income)
            for outcome in transac[income]:
                if outcome not in addresses and outcome not in allAddresses:
                    addresses.append(outcome)
                    
    except Exception as e:
        print(f"ERREUR : {address} - {e}")
    
    return G, addresses, transac


COLOR_SCHEMES = {
    'circles': ["#0000FF", "#FF0000", "#FFA500", "#FFFF00", "#800080", "#00FF00", "#00FFFF", "#FF00FF"],
    'risk': ["#00FF00", "#7FFF00", "#FFFF00", "#FFA500", "#FF4500", "#FF0000", "#8B0000", "#4B0000"],
    'heat': ["#0000FF", "#0080FF", "#00FFFF", "#00FF00", "#FFFF00", "#FF8000", "#FF0000", "#800000"]
}


def calculate_risk_score(addr_short, transac, node_layer, predecessors, successors):
    """Calcule un score de risque basé sur plusieurs métriques"""
    score = 0
    
    # 1. Degree (nombre de connexions)
    in_degree = len(predecessors.get(addr_short, []))
    out_degree = len(successors.get(addr_short, []))
    
    if out_degree > 20:  # Fan-out suspect
        score += 3
    elif out_degree > 10:
        score += 2
    elif out_degree > 5:
        score += 1
    
    if in_degree > 20:  # Fan-in suspect
        score += 3
    elif in_degree > 10:
        score += 2
    
    # 2. Structuring (multiples petites transactions)
    for outcome in successors.get(addr_short, []):
        # Trouver l'adresse complète
        for full_addr in transac:
            if full_addr[:15] == addr_short:
                for full_outcome in transac[full_addr]:
                    if full_outcome[:15] == outcome:
                        tx_count = transac[full_addr][full_outcome]['count']
                        if tx_count > 10:
                            score += 2
                        elif tx_count > 5:
                            score += 1
    
    # 3. Layering (position dans la chaîne)
    layer = node_layer.get(addr_short, 0)
    if 2 <= layer <= 4:  # Couches intermédiaires = layering potentiel
        score += 1
    
    # 4. Centralité (hub)
    total_connections = in_degree + out_degree
    if total_connections > 30:
        score += 2
    
    return min(score, 7)  # Score max = 7


def main(args):
    outcome = args.address
    nb_cercles = args.nbCercles

    # Créer le graphe PyVis avec des paramètres optimisés
    net = Network(height="900px", width="100%", bgcolor="#222222", 
                  font_color="white", select_menu=True, filter_menu=True)
    
    # Configuration de la physique optimisée
    net.barnes_hut(gravity=-10000, central_gravity=0.3, spring_length=200, 
                   spring_strength=0.01, damping=0.09, overlap=0)
    
    # Initialisation
    allAddresses = set([outcome])
    node_layer = {}
    node_layer[outcome] = 0
    
    current_level = [outcome]
    transac = {}
    
    print(f"Adresse initiale: {outcome}")
    
    for cercle in range(nb_cercles):
        print(f"\n=== Cercle {cercle} - {len(current_level)} adresses à traiter ===")
        next_level = []
        
        for addr in current_level:
            print(f"  Traitement: {addr[:15]}...")
            _, outcomes, transac = make_graph(None, addr, limit=args.limit, 
                                             allAddresses=list(allAddresses), 
                                             transac=transac)
            
            if outcomes is not None:
                for outcome_addr in outcomes:
                    outcome_short = outcome_addr[:15]
                    
                    if outcome_addr not in allAddresses:
                        allAddresses.add(outcome_addr)
                        node_layer[outcome_short] = cercle + 1
                        next_level.append(outcome_addr)
        
        print(f"  Total adresses découvertes: {len(allAddresses)}")
        current_level = next_level
        
        if not current_level and cercle < nb_cercles - 1:
            print("  Aucune nouvelle adresse, arrêt anticipé")
            break
    
    # Construire les dictionnaires de connexions
    predecessors = {}
    successors = {}
    
    for income in transac:
        income_short = income[:15]
        if income_short not in successors:
            successors[income_short] = []
            
        for outcome in transac[income]:
            outcome_short = outcome[:15]
            
            if outcome_short not in successors[income_short]:
                successors[income_short].append(outcome_short)
            
            if outcome_short not in predecessors:
                predecessors[outcome_short] = []
            if income_short not in predecessors[outcome_short]:
                predecessors[outcome_short].append(income_short)
    
    # Calculer les scores de risque
    risk_scores = {}
    for addr in allAddresses:
        addr_short = addr[:15]
        risk_scores[addr_short] = calculate_risk_score(
            addr_short, transac, node_layer, predecessors, successors
        )
    
    # Calculer les positions
    print("\n=== Computing layout ===")
    fixed_pos = {}
    
    MIN_R_FIRST = 200.0
    MIN_DR = 150.0
    SPACING_ARC = 60.0
    
    start_node_short = outcome[:15]
    fixed_pos[start_node_short] = (0, 0)
    
    layers_nodes = {}
    for addr in allAddresses:
        node_short = addr[:15]
        layer = node_layer.get(node_short, 0)
        if layer not in layers_nodes:
            layers_nodes[layer] = []
        layers_nodes[layer].append(node_short)
    
    current_radius = 0.0
    
    for lvl in sorted(layers_nodes.keys()):
        if lvl == 0:
            continue
            
        layer_nodes = layers_nodes[lvl]
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
        
        node_angles = []
        for node in layer_nodes:
            parents = predecessors.get(node, [])
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
            fixed_pos[node] = (math.cos(angle) * R, math.sin(angle) * R)
    
    # Préparer les données pour les filtres
    graph_data = {
        'nodes': {},
        'edges': []
    }
    
    print("\n=== Génération du graphe visuel ===")
    added_nodes = set()
    
    for income in transac:
        income_short = income[:15]
        if income_short not in added_nodes:
            layer = node_layer.get(income_short, 0)
            risk = risk_scores.get(income_short, 0)
            in_deg = len(predecessors.get(income_short, []))
            out_deg = len(successors.get(income_short, []))
            
            graph_data['nodes'][income_short] = {
                'full_address': income,
                'layer': layer,
                'risk_score': risk,
                'in_degree': in_deg,
                'out_degree': out_deg,
                'pos': fixed_pos.get(income_short, (0, 0))
            }
            
            # Couleur par défaut (cercles)
            color = COLOR_SCHEMES['circles'][layer % len(COLOR_SCHEMES['circles'])]
            
            node_opts = {
                'color': color,
                'size': 25,
                'physics': True,
                'layer': layer,
                'risk_score': risk,
                'in_degree': in_deg,
                'out_degree': out_deg
            }
            
            if income_short in fixed_pos:
                node_opts['x'] = fixed_pos[income_short][0]
                node_opts['y'] = fixed_pos[income_short][1]
            
            title_html = f"""
            <b>{income}</b><br>
            Couche: {layer}<br>
            Score de risque: {risk}/7<br>
            Connexions entrantes: {in_deg}<br>
            Connexions sortantes: {out_deg}
            """
            
            net.add_node(income_short, label=income_short, title=title_html, **node_opts)
            added_nodes.add(income_short)
        
        for outcome in transac[income]:
            outcome_short = outcome[:15]
            if outcome_short not in added_nodes:
                layer = node_layer.get(outcome_short, 0)
                risk = risk_scores.get(outcome_short, 0)
                in_deg = len(predecessors.get(outcome_short, []))
                out_deg = len(successors.get(outcome_short, []))
                
                graph_data['nodes'][outcome_short] = {
                    'full_address': outcome,
                    'layer': layer,
                    'risk_score': risk,
                    'in_degree': in_deg,
                    'out_degree': out_deg,
                    'pos': fixed_pos.get(outcome_short, (0, 0))
                }
                
                color = COLOR_SCHEMES['circles'][layer % len(COLOR_SCHEMES['circles'])]
                
                node_opts = {
                    'color': color,
                    'size': 25,
                    'physics': True,
                    'layer': layer,
                    'risk_score': risk,
                    'in_degree': in_deg,
                    'out_degree': out_deg
                }
                
                if outcome_short in fixed_pos:
                    node_opts['x'] = fixed_pos[outcome_short][0]
                    node_opts['y'] = fixed_pos[outcome_short][1]
                
                title_html = f"""
                <b>{outcome}</b><br>
                Couche: {layer}<br>
                Score de risque: {risk}/7<br>
                Connexions entrantes: {in_deg}<br>
                Connexions sortantes: {out_deg}
                """
                
                net.add_node(outcome_short, label=outcome_short, title=title_html, **node_opts)
                added_nodes.add(outcome_short)
            
            # Données de l'arête
            tx_data = transac[income][outcome]
            count = tx_data['count']
            total_amount = tx_data['total_amount']
            avg_amount = total_amount / count if count > 0 else 0
            
            graph_data['edges'].append({
                'from': income_short,
                'to': outcome_short,
                'count': count,
                'total_amount': round(total_amount, 2),
                'avg_amount': round(avg_amount, 2)
            })
            
            net.add_edge(income_short, outcome_short, 
                        value=count,
                        title=f"Transactions: {count}<br>Montant total: {total_amount:.2f} KAS<br>Moyenne: {avg_amount:.2f} KAS",
                        label=str(count),
                        count=count,
                        total_amount=total_amount,
                        arrowStrikethrough=False)
    
    print(f"\nGraphe construit - Nœuds: {len(added_nodes)}, Arêtes: {len(graph_data['edges'])}")
    
    # Sauvegarder le graphe de base
    output_file = f"Pyvis_AugustinV3_cercle{nb_cercles}.html"
    net.save_graph(output_file)
    
    # Ajouter le panneau de contrôle interactif
    with open(output_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Injecter le code JavaScript pour les filtres
    custom_js = f"""
    <script>
    const graphData = {json.dumps(graph_data)};
    const colorSchemes = {json.dumps(COLOR_SCHEMES)};
    
    function hexToRgb(hex) {{
        const result = /^#?([a-f\\d]{{2}})([a-f\\d]{{2}})([a-f\\d]{{2}})$/i.exec(hex);
        return result ? {{
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        }} : null;
    }}
    
    function rgbToHex(r, g, b) {{
        return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
    }}
    
    function interpolateColor(color1, color2, factor) {{
        const c1 = hexToRgb(color1);
        const c2 = hexToRgb(color2);
        const r = Math.round(c1.r + factor * (c2.r - c1.r));
        const g = Math.round(c1.g + factor * (c2.g - c1.g));
        const b = Math.round(c1.b + factor * (c2.b - c1.b));
        return rgbToHex(r, g, b);
    }}
    
    function updateNodeColors(scheme) {{
        const nodes = network.body.data.nodes;
        nodes.forEach(node => {{
            let color;
            if (scheme === 'circles') {{
                const layer = node.layer || 0;
                color = colorSchemes.circles[layer % colorSchemes.circles.length];
            }} else if (scheme === 'risk') {{
                const risk = node.risk_score || 0;
                const colors = colorSchemes.risk;
                color = colors[risk % colors.length];
            }} else if (scheme === 'heat') {{
                const totalConnections = (node.in_degree || 0) + (node.out_degree || 0);
                const maxConnections = 50;
                const factor = Math.min(totalConnections / maxConnections, 1);
                const colors = colorSchemes.heat;
                const index = Math.floor(factor * (colors.length - 1));
                color = colors[index];
            }}
            nodes.update({{id: node.id, color: color}});
        }});
    }}
    
    function updateEdgeLabels(showAmount) {{
        const edges = network.body.data.edges;
        edges.forEach(edge => {{
            if (showAmount) {{
                const edgeData = graphData.edges.find(e => e.from === edge.from && e.to === edge.to);
                if (edgeData) {{
                    edges.update({{
                        id: edge.id, 
                        label: edgeData.total_amount.toFixed(2) + ' KAS',
                        title: `Transactions: ${{edgeData.count}}<br>Montant total: ${{edgeData.total_amount.toFixed(2)}} KAS<br>Moyenne: ${{edgeData.avg_amount.toFixed(2)}} KAS`
                    }});
                }}
            }} else {{
                edges.update({{id: edge.id, label: String(edge.count || '')}});
            }}
        }});
    }}
    
    function filterByRisk(minRisk) {{
        const nodes = network.body.data.nodes;
        nodes.forEach(node => {{
            const risk = node.risk_score || 0;
            if (risk >= minRisk) {{
                nodes.update({{id: node.id, hidden: false}});
            }} else {{
                nodes.update({{id: node.id, hidden: true}});
            }}
        }});
    }}
    
    function resetFilters() {{
        const nodes = network.body.data.nodes;
        nodes.forEach(node => {{
            nodes.update({{id: node.id, hidden: false}});
        }});
    }}
    
    // Attendre que le réseau soit chargé
    setTimeout(() => {{
        // Ajouter un panneau pour afficher l'adresse sélectionnée
        const addressPanel = document.createElement('div');
        addressPanel.style.position = 'fixed';
        addressPanel.style.bottom = '10px';
        addressPanel.style.left = '10px';
        addressPanel.style.background = 'rgba(0,0,0,0.9)';
        addressPanel.style.padding = '15px';
        addressPanel.style.borderRadius = '10px';
        addressPanel.style.color = 'white';
        addressPanel.style.zIndex = '1000';
        addressPanel.style.maxWidth = '600px';
        addressPanel.style.fontFamily = 'monospace';
        addressPanel.style.fontSize = '12px';
        addressPanel.style.display = 'none';
        addressPanel.id = 'addressPanel';
        
        addressPanel.innerHTML = `
            <div style="margin-bottom: 10px;">
                <b>Adresse sélectionnée:</b>
                <button id="closeAddressPanel" style="float:right; background:#ff4444; border:none; color:white; padding:5px 10px; border-radius:5px; cursor:pointer;">✕</button>
            </div>
            <div id="selectedAddress" style="word-break: break-all; background: #333; padding: 10px; border-radius: 5px; margin-bottom: 10px;"></div>
            <button id="copyAddress" style="width:100%; padding:10px; background:#2196F3; color:white; border:none; border-radius:5px; cursor:pointer; margin-bottom:5px;">
                Copier l'adresse
            </button>
            <a id="explorerLink" href="#" target="_blank" style="display:block; width:100%; padding:10px; background:#4CAF50; color:white; text-align:center; text-decoration:none; border-radius:5px;">
                Voir sur Kaspa Explorer
            </a>
        `;
        
        document.body.appendChild(addressPanel);
        
        // Event listener pour fermer le panneau
        document.getElementById('closeAddressPanel').addEventListener('click', () => {{
            document.getElementById('addressPanel').style.display = 'none';
        }});
        
        // Event listener pour copier l'adresse
        document.getElementById('copyAddress').addEventListener('click', () => {{
            const addressText = document.getElementById('selectedAddress').textContent;
            navigator.clipboard.writeText(addressText).then(() => {{
                const btn = document.getElementById('copyAddress');
                const originalText = btn.textContent;
                btn.textContent = '✓ Copié !';
                btn.style.background = '#4CAF50';
                setTimeout(() => {{
                    btn.textContent = originalText;
                    btn.style.background = '#2196F3';
                }}, 2000);
            }});
        }});
        
        // Event listener pour les clics sur les nœuds
        network.on('click', function(params) {{
            if (params.nodes.length > 0) {{
                const nodeId = params.nodes[0];
                const nodeData = graphData.nodes[nodeId];
                
                if (nodeData) {{
                    const fullAddress = nodeData.full_address;
                    document.getElementById('selectedAddress').textContent = fullAddress;
                    document.getElementById('explorerLink').href = `https://explorer.kaspa.org/addresses/${{fullAddress}}`;
                    document.getElementById('addressPanel').style.display = 'block';
                    
                    // Log dans la console aussi
                    console.log('='.repeat(80));
                    console.log('Adresse Kaspa sélectionnée:');
                    console.log(fullAddress);
                    console.log('Couche:', nodeData.layer);
                    console.log('Score de risque:', nodeData.risk_score + '/7');
                    console.log('Connexions entrantes:', nodeData.in_degree);
                    console.log('Connexions sortantes:', nodeData.out_degree);
                    console.log('='.repeat(80));
                }}
            }}
        }});
        
        // Ajouter les contrôles
        const controlPanel = document.createElement('div');
        controlPanel.id = 'controlPanel';
        controlPanel.style.position = 'fixed';
        controlPanel.style.top = '80px';
        controlPanel.style.right = '10px';
        controlPanel.style.background = 'rgba(0,0,0,0.8)';
        controlPanel.style.padding = '20px';
        controlPanel.style.borderRadius = '10px';
        controlPanel.style.color = 'white';
        controlPanel.style.zIndex = '1000';
        controlPanel.style.maxWidth = '300px';
        controlPanel.style.fontFamily = 'Arial, sans-serif';
        
        controlPanel.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h3 style="margin:0;">Contrôles d'Analyse</h3>
                <button id="closeControlPanel" style="background:#ff4444; border:none; color:white; padding:5px 10px; border-radius:5px; cursor:pointer; font-weight: bold;">✕</button>
            </div>
            
            <div style="margin-bottom: 15px;">
                <label><b>Schéma de couleurs:</b></label><br>
                <select id="colorScheme" style="width:100%; padding:5px; margin-top:5px;">
                    <option value="circles">Par Cercles (défaut)</option>
                    <option value="risk">Par Score de Risque</option>
                    <option value="heat">Par Centralité (Heat)</option>
                </select>
            </div>
            
            <div style="margin-bottom: 15px;">
                <label>
                    <input type="checkbox" id="showAmount">
                    Afficher montants (KAS) au lieu du nombre
                </label>
            </div>
            
            <div style="margin-bottom: 15px;">
                <label><b>Filtre risque minimum:</b></label><br>
                <input type="range" id="riskFilter" min="0" max="7" value="0" style="width:100%;">
                <span id="riskValue">0</span>/7
            </div>
            
            <button id="resetBtn" style="width:100%; padding:10px; background:#4CAF50; color:white; border:none; border-radius:5px; cursor:pointer;">
                Réinitialiser les filtres
            </button>
            
            <div style="margin-top:15px; font-size:12px; border-top:1px solid #666; padding-top:10px;">
                <b>Légende Score de Risque:</b><br>
                0-2: Faible 🟢<br>
                3-4: Moyen 🟡<br>
                5-7: Élevé 🔴
            </div>
        `;
        
        document.body.appendChild(controlPanel);
        
        // Event listeners pour le panneau de contrôle
        document.getElementById('closeControlPanel').addEventListener('click', () => {{
            document.getElementById('controlPanel').style.display = 'none';
            document.getElementById('toggleControlPanel').style.display = 'block';
        }});
        
        document.getElementById('colorScheme').addEventListener('change', (e) => {{
            updateNodeColors(e.target.value);
        }});
        
        document.getElementById('showAmount').addEventListener('change', (e) => {{
            updateEdgeLabels(e.target.checked);
        }});
        
        document.getElementById('riskFilter').addEventListener('input', (e) => {{
            document.getElementById('riskValue').textContent = e.target.value;
            filterByRisk(parseInt(e.target.value));
        }});
        
        document.getElementById('resetBtn').addEventListener('click', () => {{
            document.getElementById('riskFilter').value = 0;
            document.getElementById('riskValue').textContent = '0';
            document.getElementById('showAmount').checked = false;
            document.getElementById('colorScheme').value = 'circles';
            resetFilters();
            updateNodeColors('circles');
            updateEdgeLabels(false);
        }});
        
        // Ajouter des boutons pour réouvrir les panneaux fermés
        const toggleButtons = document.createElement('div');
        toggleButtons.style.position = 'fixed';
        toggleButtons.style.top = '10px';
        toggleButtons.style.right = '10px';
        toggleButtons.style.zIndex = '1001';
        toggleButtons.style.display = 'flex';
        toggleButtons.style.gap = '10px';
        
        toggleButtons.innerHTML = `
            <button id="toggleControlPanel" style="background:#4CAF50; border:none; color:white; padding:10px 15px; border-radius:5px; cursor:pointer; font-weight:bold; display:none;">
                Contrôles
            </button>
            <button id="toggleAddressPanel" style="background:#2196F3; border:none; color:white; padding:10px 15px; border-radius:5px; cursor:pointer; font-weight:bold; display:none;">
                Adresse
            </button>
        `;
        
        document.body.appendChild(toggleButtons);
        
        // Toggle pour le panneau de contrôle
        document.getElementById('toggleControlPanel').addEventListener('click', () => {{
            document.getElementById('controlPanel').style.display = 'block';
            document.getElementById('toggleControlPanel').style.display = 'none';
        }});
        
        // Toggle pour le panneau d'adresse
        document.getElementById('toggleAddressPanel').addEventListener('click', () => {{
            const panel = document.getElementById('addressPanel');
            panel.style.display = 'block';
            document.getElementById('toggleAddressPanel').style.display = 'none';
        }});
        
        // Modifier le comportement de fermeture du panneau d'adresse
        document.getElementById('closeAddressPanel').addEventListener('click', () => {{
            document.getElementById('addressPanel').style.display = 'none';
            document.getElementById('toggleAddressPanel').style.display = 'block';
        }});
    }}, 1000);
    </script>
    """
    html_content = html_content.replace('</body>', custom_js + '</body>')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Visualisation enregistrée sous : {os.path.abspath(output_file)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Arguments")
    parser.add_argument("--address", type=str, help="address Kaspa", required=True)
    parser.add_argument("--APIkey", type=str, help="API key", required=True)
    parser.add_argument("--limit", type=int, default=3, help="Limite de transactions")
    parser.add_argument("--nbCercles", type=int, default=3, help="Nombre de cercles")
    args = parser.parse_args()
    
    API_KEY = args.APIkey
    main(args)