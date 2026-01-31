import requests
from pyvis.network import Network
import time
import os
import json
import sqlite3

URLADDRESS="https://api.kaspa.org/addresses/"
URLTRANSAC="https://api.kaspa.org/transactions/"
CACHE_FILE="transacs_cache.db"
conn=sqlite3.connect(CACHE_FILE)
cursor=conn.cursor()

def init_db():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS names (
                address TEXT PRIMARY KEY,
                data TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transac_hash TEXT PRIMARY KEY,
            data TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions_inout (
            transac_hash TEXT PRIMARY KEY,
            inputs TEXT,
            outputs TEXT
        )
    ''')
    conn.commit()

init_db()

def get_address_data(address,limit):
    return requests.get(URLADDRESS+address+f"/full-transactions?limit={limit}&offset=0&resolve_previous_outpoints=light").json()

def verify_name(address):
    cursor.execute('SELECT data FROM names WHERE address = ?',(address,))
    row=cursor.fetchone()
    if row:
        return json.loads(row[0])
    
    try:
        res=requests.get(f"{URLADDRESS}{address}/name")
        name_data=res.json()
    except:
        name_data={}
    
    cursor.execute('INSERT OR REPLACE INTO names (address,data) VALUES (?,?)',(address,json.dumps(name_data)))
    conn.commit()
    return name_data

def save_transac_db(transac_hash,transac_data):
    cursor.execute('INSERT OR IGNORE INTO transactions (transac_hash,data) VALUES (?,?)',(transac_hash,json.dumps(transac_data)))

def get_transac_db(transac_hash):
    cursor.execute('SELECT data FROM transactions WHERE transac_hash = ?',(transac_hash,))
    row=cursor.fetchone()
    if row: return json.loads(row[0])
    return None

def get_inout_db(transac_hash):
    cursor.execute('SELECT inputs,outputs FROM transactions_inout WHERE transac_hash = ?',(transac_hash,))
    row=cursor.fetchone()
    if row: return json.loads(row[0]),json.loads(row[1])
    return None, None

def save_transaction_inout(transac_hash,inputs,outputs):
    cursor.execute('INSERT OR IGNORE INTO transactions_inout (transac_hash,inputs,outputs) VALUES (?,?,?)',(transac_hash,json.dumps(inputs),json.dumps(outputs)))
        
def get_inputs_ouputs(transac):
    inputs=[]
    outputs=[]

    if transac["inputs"]:
        for input in transac["inputs"]:
            addr=input.get("previous_outpoint_address")
            amount=input.get("previous_outpoint_amount",0)/100000000
            if addr:
                inputs.append({"address":addr,"amount":amount})

    if transac["outputs"]:
        for output in transac["outputs"]:
            addr=output.get("script_public_key_address")
            amount=output.get("amount",0)/100000000
            if addr:
                outputs.append({"address":addr,"amount":amount})

    input_addrs={i["address"] for i in inputs}
    outputs=[o for o in outputs if o["address"] not in input_addrs]
    
    return inputs,outputs

def explore_address(relations,address,cercle,addrSeen,addrList,futurList,limit):
    data_address=get_address_data(address,limit)
    # print("Nb de transactions: ",len(data_address))

    if address not in relations:
        relations[address]={
            "nb_transacs_in":0,
            "nb_transacs_out":0,
            "address_in":{},
            "amount_in":0,
            "address_out":{},
            "amount_out":0,
            "cercle":cercle
        }

    for i,transac in enumerate(data_address):
        # print(f"Transaction : {i+1}/{len(data_address)}")
        transac_hash=transac.get("verboseData",{}).get("transactionId") or transac.get("hash")
        inputs,outputs=get_inout_db(transac_hash)
        if inputs is None or outputs is None:
            cached_transac=get_transac_db(transac_hash)

            if cached_transac:
                transac_process=cached_transac
            else:
                save_transac_db(transac_hash,transac)
                transac_process=transac
            
            inputs,outputs=get_inputs_ouputs(transac_process)
            save_transaction_inout(transac_hash,inputs,outputs)

        

        if any(o["address"]==address for o in outputs):
            for input in inputs:
                src=input["address"]
                if src!=address:
                    ver=verify_name(src)
                    if "name" in ver:
                        # print(ver)
                        continue

                    relations[address]["nb_transacs_in"]+=1
                    relations[address]["amount_in"]+=input["amount"]

                    if src not in relations[address]["address_in"]:
                        relations[address]["address_in"][src]={"nb":0,"amount":0}

                    relations[address]["address_in"][src]["nb"]+=1
                    relations[address]["address_in"][src]["amount"]+=input["amount"]

                    if src not in addrList and src not in futurList and src not in addrSeen:
                        futurList.append(src)

        if any(inp["address"]==address for inp in inputs):
            for output in outputs:
                target=output["address"]
                if target!=address:
                    ver=verify_name(target)
                    if "name" in ver:
                        # print(ver)
                        continue

                    relations[address]["nb_transacs_out"]+=1
                    relations[address]["amount_out"]+=output["amount"]

                    if target not in relations[address]["address_out"]:
                        relations[address]["address_out"][target]={"nb":0,"amount":0}

                    relations[address]["address_out"][target]["nb"]+=1
                    relations[address]["address_out"][target]["amount"]+=output["amount"]
                    
                if target not in addrList and target not in futurList and target not in addrSeen:
                    futurList.append(target)

    return relations,futurList
    
def create_vis(relations, initial_address,nb_cercles,limit):
    net=Network(height="900px", width="100%", bgcolor="#222222", font_color="white", directed=True)
    net.barnes_hut(gravity=-10000,central_gravity=0.3,spring_length=250,spring_strength=0.01)
    colors=["#FF0000","#FFA500","#FFFF00","#800080","#00FF00","#00FFFF","#FF00FF"]

    for addr in relations:
        if addr==initial_address:
            color="#0000FF"
            size=40
        else:
            color=colors[relations[addr]["cercle"]]
            size=25
        
        data=relations[addr]
        titleNode=f'Adresse : {addr}\nTotal Reçu : {data["amount_in"]:.2f} KAS ({data["nb_transacs_in"]} transactions)\nTotal Envoyé : {data["amount_out"]:.2f} KAS({data["nb_transacs_out"]} transactions)\n'

        net.add_node(addr,label=addr[:10]+"...",title=titleNode,color=color,size=size)

    edge_id=0
    edges_seen=set()

    for source, data in relations.items():
        for target,info in data["address_out"].items():
            if target in relations:
                edge_key=(source,target)
                if (edge_key in edges_seen):
                    continue
                edges_seen.add(edge_key)

                nb=info["nb"]
                amount=info["amount"]
                label_transacs=f"{nb} transactions"
                label_amount=f"{amount:.2f} KAS"

                if source==initial_address:
                    edge_color="#FF0000"
                    width_base=3
                elif target==initial_address:
                    edge_color= "#FFFF00" 
                    width_base=3
                else:
                    edge_color= "#666666"
                    width_base=1

                net.add_edge(source,target,id=edge_id,label=label_transacs,title=f"{label_transacs} / {label_amount}",value=nb,width=width_base,custom_count=nb,custom_amount=amount,label_tx=label_transacs,label_amount=label_amount,color=edge_color)
                edge_id+=1

    for target, data in relations.items():
        for source,info in data["address_in"].items():
            if source in relations:
                edge_key=(source,target)
                if edge_key in edges_seen:
                    continue
                edges_seen.add(edge_key)

                nb=info["nb"]
                amount=info["amount"]
                label_transacs=f"{nb} transactions"
                label_amount=f"{amount:.2f} KAS"

                if source==initial_address:
                    edge_color="#FF0000"
                    width_base=3
                elif target==initial_address:
                    edge_color= "#FFFF00" 
                    width_base=3
                else:
                    edge_color= "#666666"
                    width_base=1

                net.add_edge(source,target,id=edge_id,label=label_transacs,title=f"{label_transacs} / {label_amount}",value=nb,width=width_base,custom_count=nb,custom_amount=amount,label_tx=label_transacs,label_amount=label_amount,color=edge_color)
                edge_id+=1

    path=f"NEWKaspAPI_C{nb_cercles}LIMIT{limit}.html"
    net.save_graph(path)

    injection_ui = """
    <!-- Custom Controls Injected by NewKaspAPI -->
    
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
            // Mapping colors to layers
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
        }
    
        function setupClickHandler() {
            if (typeof network !== 'undefined' && network !== null) {
                
                network.on("click", function(params) {
                    
                    if (params.nodes && params.nodes.length > 0) {
                        var nodeId = params.nodes[0];
                        
                        // L'ID du nœud EST l'adresse Kaspa
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
                        popup.style.maxWidth = '500px';
                        popup.style.textAlign = 'center';
                        
                        popup.innerHTML = `
                            <h3 style="margin-top: 0; word-break: break-all; color: #fff;">Détails de l'adresse</h3>
                            <p style="font-size: 12px; word-break: break-all; background: #222; padding: 10px; border-radius: 5px; color: #ddd; font-family: monospace;">${address}</p>
                            <button onclick="window.open('https://explorer.kaspa.org/addresses/${address}', '_blank')" 
                                    style="width: 100%; padding: 10px; margin: 5px 0; cursor: pointer; background-color: #4CAF50; color: white; border: none; border-radius: 5px; font-size: 14px; font-weight: bold;">
                                Voir sur Kaspa Explorer
                            </button>
                            <button onclick="navigator.clipboard.writeText('${address}').then(function() { alert('Adresse copiée dans le presse-papier !'); }).catch(function(err) { console.error('Erreur copie:', err); alert('Erreur lors de la copie'); });" 
                                    style="width: 100%; padding: 10px; margin: 5px 0; cursor: pointer; background-color: #2196F3; color: white; border: none; border-radius: 5px; font-size: 14px; font-weight: bold;">
                                Copier l'adresse
                            </button>
                            <button onclick="document.getElementById('addressPopup').remove()" 
                                    style="width: 100%; padding: 10px; margin: 5px 0; cursor: pointer; background-color: #f44336; color: white; border: none; border-radius: 5px; font-size: 14px; font-weight: bold;">
                                Fermer
                            </button>
                        `;
                        
                        document.body.appendChild(popup);
                    }
                });
            } else {
                setTimeout(setupClickHandler, 100);
            }
        }
        
        // Lancer la configuration au chargement
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', setupClickHandler);
        } else {
            setupClickHandler();
        }
    </script>
    """

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    new_content=content.replace("<body>", "<body>" + injection_ui)
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    print(f"Graphique interactif généré : {path}")
    

def main(initial_address,nb_cercles,limit):
    relations={}
    addrSeen=[]
    addrList=[initial_address]
    for cercle in range(nb_cercles):
        print("cercle: ",cercle)
        futurList=[]
        i=0
        for addr in addrList:
            if addr not in addrSeen:
                ver_name=verify_name(addr)
                if "name" in ver_name.keys():
                    print("Adresse ignorée : ",ver_name)
                    addrSeen.append(addr)
                    continue

                print("expl: ",addr)
                relations,futurList=explore_address(relations,addr,cercle,addrSeen,addrList,futurList,limit)
                conn.commit()
                addrSeen.append(addr)
                i+=1
                print("Nb addr restantes :",len(addrList)-i)
            
        addrList=list(set(futurList))
        print(len(addrList))
    
    create_vis(relations,initial_address,nb_cercles,limit)

if __name__=="__main__":
    address="kaspa:qqssy8x2stwk6x7trmw56m8rwfkwul70rpqxrvv789mxqz73pdny2sprry82x"
    main(address,nb_cercles=4,limit=50)
    """TODO:
    -Adresse cliquable dans le graph
    -Score de risque par adresse
    -Echelles de couleurs
    """