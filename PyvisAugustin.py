import requests
from pyvis.network import Network
import argparse
import os
import math

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
            for input in transactions["inputs"]:
                incomeAddress = input["previousOutput"]["scriptPublicKeyAddress"]
                if incomeAddress not in transac:
                    transac[incomeAddress] = {}
                for output in transactions["outputs"]:
                    outcomeAddress = output["scriptPublicKeyAddress"]
                    if outcomeAddress not in transac[incomeAddress]:
                        transac[incomeAddress][outcomeAddress] = 1
                    else:
                        transac[incomeAddress][outcomeAddress] += 1
        
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


COLOR = [
    "blue",
    "red",
    "orange",
    "yellow",
    "purple",
    "green",
    "cyan",
    "magenta"
]


def main(args):
    outcome = args.address
    nb_cercles = args.nbCercles

    # Créer le graphe PyVis avec des paramètres optimisés
    net = Network(height="900px", width="100%", bgcolor="#222222", 
                  font_color="white", select_menu=True, filter_menu=True)
    
    # Configuration de la physique optimisée (inspirée de Bastos)
    net.barnes_hut(gravity=-10000, central_gravity=0.3, spring_length=200, 
                   spring_strength=0.01, damping=0.09, overlap=0)
    
    allOutcomes = []
    allOutcomes.append([outcome])
    allAddresses = []
    allAddresses.extend([outcome])
    print(f"Adresses initiales: {len(allAddresses)}")
    
    # Dictionnaire pour stocker la couche de chaque nœud
    node_layer = {}
    # Dictionnaire pour les prédécesseurs (pour layout optimisé)
    predecessors = {}
    transac = {}
    
    for cercle in range(nb_cercles):
        print(f"Cercle {cercle + 1} - Taille : {len(allOutcomes[cercle])}")
        for i in range(len(allOutcomes[cercle])):
            addr = allOutcomes[cercle][i]
            node_short = addr[:15]
            if node_short not in node_layer:
                node_layer[node_short] = cercle
            
            print(f"  Traitement: {addr}")
            _, outcomes, transac = make_graph(None, addr, limit=args.limit, 
                                             allAddresses=allAddresses, 
                                             transac=transac)
            
            if outcomes is not None:
                allOutcomes.append(outcomes)
                allAddresses.extend(outcomes)
            
            print(f"  Total adresses: {len(allAddresses)}")
    
    # Construire le dictionnaire des prédécesseurs
    for income in transac:
        income_short = income[:15]
        for outcome in transac[income]:
            outcome_short = outcome[:15]
            if outcome_short not in predecessors:
                predecessors[outcome_short] = []
            predecessors[outcome_short].append(income_short)
    
    # Calculer les positions en disposition circulaire concentrique
    print("Computing layout...")
    fixed_pos = {}
    
    # Constantes pour le layout
    MIN_R_FIRST = 200.0
    MIN_DR = 150.0
    SPACING_ARC = 60.0
    
    # Position du nœud central
    start_node_short = outcome[:15]
    fixed_pos[start_node_short] = (0, 0)
    
    # Organiser les nœuds par couche
    layers_nodes = {}
    for node_short in node_layer:
        layer = node_layer[node_short]
        if layer not in layers_nodes:
            layers_nodes[layer] = []
        layers_nodes[layer].append(node_short)
    
    current_radius = 0.0
    
    # Positionner chaque couche
    for lvl in sorted(layers_nodes.keys()):
        if lvl == 0:
            continue  # Le nœud central est déjà positionné
            
        layer_nodes = layers_nodes[lvl]
        N_nodes = len(layer_nodes)
        
        if N_nodes == 0:
            continue
        
        # Calculer le rayon pour cette couche
        if lvl == 1:
            target_min_r = MIN_R_FIRST
        else:
            target_min_r = current_radius + MIN_DR
        
        required_circumference = N_nodes * SPACING_ARC
        required_r_spacing = required_circumference / (2 * math.pi)
        
        R = max(target_min_r, required_r_spacing)
        current_radius = R
        
        # Trier les nœuds par angle moyen de leurs prédécesseurs
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
        
        # Positionner les nœuds en cercle
        angle_step = 2 * math.pi / N_nodes
        for i, node in enumerate(sorted_layer_nodes):
            angle = i * angle_step
            fixed_pos[node] = (math.cos(angle) * R, math.sin(angle) * R)
    
    # Ajouter tous les nœuds au graphe avec leurs positions
    added_nodes = set()
    for income in transac:
        income_short = income[:15]
        if income_short not in added_nodes:
            layer = node_layer.get(income_short, nb_cercles - 1)
            color = COLOR[layer % len(COLOR)]
            
            # Options du nœud avec position fixée
            node_opts = {
                'color': color,
                'size': 25,
                'physics': True  # Permet un ajustement léger par la physique
            }
            
            if income_short in fixed_pos:
                node_opts['x'] = fixed_pos[income_short][0]
                node_opts['y'] = fixed_pos[income_short][1]
            
            net.add_node(income_short, label=income_short, title=income, **node_opts)
            added_nodes.add(income_short)
        
        for outcome in transac[income]:
            outcome_short = outcome[:15]
            if outcome_short not in added_nodes:
                layer = node_layer.get(outcome_short, nb_cercles - 1)
                color = COLOR[layer % len(COLOR)]
                
                node_opts = {
                    'color': color,
                    'size': 25,
                    'physics': True
                }
                
                if outcome_short in fixed_pos:
                    node_opts['x'] = fixed_pos[outcome_short][0]
                    node_opts['y'] = fixed_pos[outcome_short][1]
                
                net.add_node(outcome_short, label=outcome_short, title=outcome, **node_opts)
                added_nodes.add(outcome_short)
            
            # Ajouter l'arête avec le poids et le label visible
            weight = transac[income][outcome]
            net.add_edge(income_short, outcome_short, value=weight, 
                        title=f"Transactions: {weight}", label=str(weight),
                        arrowStrikethrough=False)
    
    print(f"\nGraphe construit - Nœuds: {len(added_nodes)}, Arêtes: {sum(len(v) for v in transac.values())}")
    
    # Sauvegarder le graphe
    output_file = f"pyvis_Augustin{nb_cercles}.html"
    net.save_graph(output_file)
    print(f"Visualisation sauvegardée dans: {os.path.abspath(output_file)}")
    print(f"Ouvrez le fichier dans votre navigateur pour voir le graphe interactif!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Arguments")
    parser.add_argument("--address", type=str, help="address Kaspa", required=True)
    parser.add_argument("--APIkey", type=str, help="API key", required=True)
    parser.add_argument("--limit", type=int, default=3, help="Limite de transactions")
    parser.add_argument("--nbCercles", type=int, default=3, help="Nombre de cercles")
    args = parser.parse_args()
    
    API_KEY = args.APIkey
    main(args)