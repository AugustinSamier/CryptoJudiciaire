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
            amount=input.get("previous_outpoint_amount") or 0
            amount=amount/100000000
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

def risk_score(addr_relations,nb_cercles):
    score=0
    risks=[]

    total_in=addr_relations["amount_in"]
    total_out=addr_relations["amount_out"]
    nb_transacs_in=addr_relations["nb_transacs_in"]
    nb_transacs_out=addr_relations["nb_transacs_out"]
    nb_sources=len(addr_relations["address_in"])
    nb_targets=len(addr_relations["address_out"])

    if nb_transacs_in>0:
        average_amount_in=total_in/nb_transacs_in
        if average_amount_in<100 and nb_transacs_in>20:
            score+=20
            risks.append(f"Structuration suspectée (beaucoup de petites transactions) : avg: {average_amount_in:.2f} KAS, {nb_transacs_in} transacs.")
    
    if total_in>0 and total_out>0 and addr_relations["cercle"]!=nb_cercles-1:
        dispersion_ratio=total_out/total_in
        if dispersion_ratio>0.9 and nb_transacs_out>15:
            score+=15
            risks.append(f"Dispersion rapide ({dispersion_ratio*100:.1f}% des fonds ressortent).")

    if nb_sources>30 or nb_targets>30:
        score+=15
        risks.append(f"Beaucoup de relations ({nb_sources} sources, {nb_targets} cibles).")
    
    if total_in>10000 and nb_sources<5:
        score+=10
        risks.append(f"Concentration suspecte ({total_in:.0f} KAS venant de {nb_sources} sources).")

    if nb_transacs_in>0:
        transac_ratio=nb_transacs_out/nb_transacs_in
        if transac_ratio>5:
            score+=10
            risks.append(f"Hub de distribution ({nb_transacs_in} sources, {nb_transacs_out} sorties donc {transac_ratio:.1f}x plus de sorties que d'entrées).")
    
    nb_round_amount=0
    for addr_data in addr_relations["address_out"].values():
        amount=addr_data["amount"]
        if amount%10==0:
            nb_round_amount+=1
    
    if nb_round_amount>10:
        score+=10
        risks.append(f"Montants ronds suspects (sûrement automatiques) : {nb_round_amount} transactions rondes.")
    
    total_amount=total_in+total_out
    if total_amount>100000:
        score+=10
        risks.append(f"Total montant élevé ({total_amount:.0f} KAS -> {total_amount*0.02809:.2f} €).")
    
    score=min(score,100)

    if score<20:
        risk_level="FAIBLE"
        risk_color="#4CAF50"
    elif score <40:
        risk_level="MODÉRÉ"
        risk_color="#FF9800"
    elif score<60:
        risk_level="ÉLEVÉ"
        risk_color="#FF5722"
    else:
        risk_level="CRITIQUE"
        risk_color="#F44336"

    return {"score":score,"level":risk_level,"color":risk_color,"risks":risks}

def create_vis(relations, initial_address,nb_cercles,limit):
    net=Network(height="900px", width="100%", bgcolor="#222222", font_color="white", directed=True)
    net.barnes_hut(gravity=-10000,central_gravity=0.3,spring_length=250,spring_strength=0.01)
    colors=["#FF0000","#FFA500","#FFFF00","#800080","#00FF00","#00FFFF","#FF00FF"]

    risk_dict={}
    for addr in relations:
        data=relations[addr]

        risk_dict[addr]=risk_score(data,nb_cercles)
        risk=risk_dict[addr]
        color_risk=risk["color"]

        if addr==initial_address:
            color_relations="#0000FF"
            size=40
        else:
            color_relations=colors[data["cercle"]]
            size=25
        
        titleNode = f'''Adresse : {addr}
        Cercle : {data["cercle"]}
        SCORE DE RISQUE : {risk["score"]}/100 ({risk["level"]})
        Total Reçu : {data["amount_in"]:.2f} KAS ({data["nb_transacs_in"]} tx)
        Total Envoyé : {data["amount_out"]:.2f} KAS ({data["nb_transacs_out"]} tx)
        Sources : {len(data["address_in"])} | Cibles : {len(data["address_out"])}
        INDICATEURS DE RISQUE :
        {chr(10).join(["-" + f for f in risk["risks"]]) if risk["risks"] else "- Aucun indicateur détecté"}
        '''

        net.add_node(addr,label=addr[:10]+"...",title=titleNode,color=color_relations,color_relations=color_relations,color_risk=color_risk,cercle=data["cercle"],risk_score=risk["score"],size=size)

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

    path=f"NEWKaspAPI_C{nb_cercles}LIMIT{limit}addr{initial_address[6:11]}.html"
    net.save_graph(path)

    risk_data_js=json.dumps({addr: risk_dict[addr] for addr in relations})

    injection_ui = f"""
    <!-- Custom Controls with Dynamic Mode Switching -->
    
    <script type="text/javascript">
        var riskData = {risk_data_js};
    </script>
    
    <!-- Top Right Controls -->
    <div id="rightControls" style="position: fixed; top: 20px; right: 20px; z-index: 9999; display: flex; flex-direction: column; align-items: flex-end; gap: 10px;">
        
        <!-- Toggle Edge Labels (Transactions/Montants) -->
        <button id="toggleEdgeBtn" onclick="toggleEdgeLabels()" 
                style="padding: 12px 24px; font-size: 16px; font-weight: bold; background-color: #2196F3; color: white; border: none; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.3); transition: background-color 0.3s; width: 250px;">
            Afficher Montants
        </button>
        
        <!-- Toggle Mode (Relations/Risque) -->
        <button id="toggleModeBtn" onclick="toggleMode()" 
                style="padding: 12px 24px; font-size: 16px; font-weight: bold; background-color: #9C27B0; color: white; border: none; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.3); transition: background-color 0.3s; width: 250px;">
            Mode RISQUE
        </button>
        
        <!-- Panel de filtres (dynamique) -->
        <div id="filterPanel" style="background: rgba(40,40,40,0.95); padding: 12px; border-radius: 8px; width: 250px;">
            <!-- Contenu dynamique géré par JavaScript -->
        </div>
    </div>

    <!-- Top Left Legend -->
    <div id="legendContainer" style="position: fixed; top: 20px; left: 20px; z-index: 9999; background-color: rgba(30, 30, 30, 0.95); padding: 20px; border-radius: 12px; color: white; font-family: 'Segoe UI', Arial, sans-serif; font-size: 16px; box-shadow: 0 4px 8px rgba(0,0,0,0.4); min-width: 250px;">
        <h4 style="margin: 0 0 15px 0; border-bottom: 2px solid #555; padding-bottom: 8px; font-size: 18px; text-align: center;">Légende</h4>
        
        <!-- Contenu dynamique géré par JavaScript -->
        <div id="legendContent"></div>
    </div>

    <script type="text/javascript">
        var showingAmount = false;
        var riskMode = false;  // false = Relations, true = Risque
        
        // Initialiser l'interface
        function initInterface() {{
            updateFilterPanel();
            updateLegend();
        }}
        
        function toggleEdgeLabels() {{
            showingAmount = !showingAmount;
            var btn = document.getElementById('toggleEdgeBtn');
            var updateArray = [];
            var allEdges = edges.get(); 
            
            allEdges.forEach(function(edge) {{
                if (showingAmount) {{
                     updateArray.push({{id: edge.id, label: edge.label_amount}});
                }} else {{
                     updateArray.push({{id: edge.id, label: edge.label_tx}});
                }}
            }});
            
            edges.update(updateArray);
            
            if (showingAmount) {{
                btn.innerText = "Afficher Transactions";
                btn.style.backgroundColor = "#FF9800"; 
            }} else {{
                btn.innerText = "Afficher Montants";
                btn.style.backgroundColor = "#2196F3"; 
            }}
        }}
        
        // FONCTION PRINCIPALE : Toggle entre mode Relations et Risque
        function toggleMode() {{
            riskMode = !riskMode;
            var btn = document.getElementById('toggleModeBtn');
            var updateArray = [];
            var allNodes = nodes.get();
            
            allNodes.forEach(function(node) {{
                if (riskMode) {{
                    // Mode RISQUE : changer couleur ET label
                    updateArray.push({{
                        id: node.id, 
                        label: node.label_risk,
                        color: node.color_risk
                    }});
                }} else {{
                    // Mode RELATIONS : revenir à la couleur du cercle
                    updateArray.push({{
                        id: node.id, 
                        label: node.label_relations,
                        color: node.color_relations
                    }});
                }}
            }});
            
            nodes.update(updateArray);
            
            // Mettre à jour le bouton
            if (riskMode) {{
                btn.innerText = "Mode RELATIONS";
                btn.style.backgroundColor = "#E91E63";
            }} else {{
                btn.innerText = "Mode RISQUE";
                btn.style.backgroundColor = "#9C27B0";
            }}
            
            // Mettre à jour le panel de filtres et la légende
            updateFilterPanel();
            updateLegend();
        }}
        
        // Mettre à jour le panel de filtres selon le mode
        function updateFilterPanel() {{
            var panel = document.getElementById('filterPanel');
            
            if (riskMode) {{
                // Mode RISQUE : afficher filtres par risque
                panel.innerHTML = `
                    <p style="margin: 0 0 8px 0; font-weight: bold; color: white; font-size: 14px; text-align: center; border-bottom: 1px solid #555; padding-bottom: 5px;">Filtrer par Risque</p>
                    <button onclick="filterByRisk(0, 100)" style="width: 100%; padding: 8px; margin-bottom: 5px; background: #607D8B; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 13px;">Tous</button>
                    <button onclick="filterByRisk(20, 100)" style="width: 100%; padding: 8px; background: #FF9800; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 13px;">Modéré (20+)</button>
                    <button onclick="filterByRisk(40, 100)" style="width: 100%; padding: 8px; margin-bottom: 5px; background: #FF5722; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 13px;">Élevé (40+)</button>
                    <button onclick="filterByRisk(60, 100)" style="width: 100%; padding: 8px; margin-bottom: 5px; background: #F44336; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 13px;">Critique (60+)</button>
                `;
            }} else {{
                // Mode RELATIONS : afficher filtres par cercle
                panel.innerHTML = `
                    <p style="margin: 0 0 8px 0; font-weight: bold; color: white; font-size: 14px; text-align: center; border-bottom: 1px solid #555; padding-bottom: 5px;">Filtrer par Cercle</p>
                    <button onclick="filterByCercle(0)" style="width: 100%; padding: 8px; margin-bottom: 5px; background: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 13px;">Cercle 0 (Cible)</button>
                    <button onclick="filterByCercle(1)" style="width: 100%; padding: 8px; margin-bottom: 5px; background: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 13px;">Cercles 0-1</button>
                    <button onclick="filterByCercle(2)" style="width: 100%; padding: 8px; margin-bottom: 5px; background: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 13px;">Cercles 0-2</button>
                    <button onclick="filterByCercle(3)" style="width: 100%; padding: 8px; margin-bottom: 5px; background: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 13px;">Cercles 0-3</button>
                    <button onclick="filterByCercle(100)" style="width: 100%; padding: 8px; background: #607D8B; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 13px;">Tous</button>
                `;
            }}
        }}
        
        // Mettre à jour la légende selon le mode
        function updateLegend() {{
            var legendContent = document.getElementById('legendContent');
            
            if (riskMode) {{
                // Légende RISQUE
                legendContent.innerHTML = `
                    <p style="margin: 0 0 8px 0; font-weight: bold; font-size: 14px;">Niveaux de Risque:</p>
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span style="width: 24px; height: 24px; background-color: #4CAF50; display: inline-block; margin-right: 12px; border-radius: 4px; box-shadow: 0 0 5px #4CAF50;"></span>
                        <span>Faible (0-19)</span>
                    </div>
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span style="width: 24px; height: 24px; background-color: #FF9800; display: inline-block; margin-right: 12px; border-radius: 4px; box-shadow: 0 0 5px #FF9800;"></span>
                        <span>Modéré (20-39)</span>
                    </div>
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span style="width: 24px; height: 24px; background-color: #FF5722; display: inline-block; margin-right: 12px; border-radius: 4px; box-shadow: 0 0 5px #FF5722;"></span>
                        <span>Élevé (40-59)</span>
                    </div>
                    <div style="display: flex; align-items: center;">
                        <span style="width: 24px; height: 24px; background-color: #F44336; display: inline-block; margin-right: 12px; border-radius: 4px; box-shadow: 0 0 5px #F44336;"></span>
                        <span>Critique (60+)</span>
                    </div>
                `;
            }} else {{
                // Légende RELATIONS (cercles)
                legendContent.innerHTML = `
                    <p style="margin: 0 0 8px 0; font-weight: bold; font-size: 14px;">Cercles:</p>
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span style="width: 24px; height: 24px; background-color: #0000FF; display: inline-block; margin-right: 12px; border-radius: 4px; border: 1px solid #fff; box-shadow: 0 0 5px #0000FF;"></span>
                        <span>Cible (0)</span>
                    </div>
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span style="width: 24px; height: 24px; background-color: #FFA500; display: inline-block; margin-right: 12px; border-radius: 4px; border: 1px solid #fff;"></span>
                        <span>Cercle 1</span>
                    </div>
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span style="width: 24px; height: 24px; background-color: #FFFF00; display: inline-block; margin-right: 12px; border-radius: 4px; border: 1px solid #fff;"></span>
                        <span>Cercle 2</span>
                    </div>
                    <div style="display: flex; align-items: center;">
                        <span style="width: 24px; height: 24px; background-color: #800080; display: inline-block; margin-right: 12px; border-radius: 4px; border: 1px solid #fff;"></span>
                        <span>Cercle 3</span>
                    </div>
                `;
            }}
        }}
        
        // Filtrer par cercle (mode Relations)
        function filterByCercle(maxCercle) {{
            var allNodes = nodes.get();
            var updateArray = [];
            
            allNodes.forEach(function(node) {{
                if (node.cercle <= maxCercle) {{
                    updateArray.push({{id: node.id, hidden: false}});
                }} else {{
                    updateArray.push({{id: node.id, hidden: true}});
                }}
            }});
            
            nodes.update(updateArray);
        }}
        
        // Filtrer par score de risque (mode Risque)
        function filterByRisk(minScore, maxScore) {{
            var allNodes = nodes.get();
            var updateArray = [];
            
            allNodes.forEach(function(node) {{
                var score = node.risk_score || 0;
                if (score >= minScore && score <= maxScore) {{
                    updateArray.push({{id: node.id, hidden: false}});
                }} else {{
                    updateArray.push({{id: node.id, hidden: true}});
                }}
            }});
            
            nodes.update(updateArray);
        }}
    
        // Popup au clic
        function setupClickHandler() {{
            if (typeof network !== 'undefined' && network !== null) {{
                network.on("click", function(params) {{
                    if (params.nodes && params.nodes.length > 0) {{
                        var nodeId = params.nodes[0];
                        var address = nodeId;
                        var risk = riskData[address];
                        
                        var existingPopup = document.getElementById('addressPopup');
                        if (existingPopup) {{
                            existingPopup.remove();
                        }}
                        
                        var riskHTML = '';
                        if (risk) {{
                            var factorsHTML = '';
                            if (risk.risks && risk.risks.length > 0) {{
                                factorsHTML = `
                                <div style="background: #222; padding: 10px; border-radius: 5px; text-align: left; margin-top: 10px; max-height: 200px; overflow-y: auto;">
                                    <p style="margin: 0 0 5px 0; font-weight: bold; font-size: 13px;">Indicateurs de Risque:</p>
                                    <ul style="margin: 0; padding-left: 20px; font-size: 12px;">
                                        ${{risk.risks.map(f => '<li style="margin-bottom: 5px;">' + f + '</li>').join('')}}
                                    </ul>
                                </div>
                                `;
                            }}
                            
                            riskHTML = `
                                <div style="background: ${{risk.color}}; padding: 12px; border-radius: 5px; margin: 10px 0;">
                                    <p style="margin: 0; font-weight: bold; font-size: 18px;">Score: ${{risk.score}}/100</p>
                                    <p style="margin: 5px 0 0 0; font-size: 15px;">Niveau: ${{risk.level}}</p>
                                </div>
                                ${{factorsHTML}}
                            `;
                        }}
                        
                        var popup = document.createElement('div');
                        popup.id = 'addressPopup';
                        popup.style.cssText = 'position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background-color: #333; padding: 20px; border-radius: 10px; z-index: 10000; box-shadow: 0 4px 6px rgba(0,0,0,0.3); color: white; font-family: Arial, sans-serif; min-width: 400px; max-width: 600px; max-height: 80vh; overflow-y: auto;';
                        
                        popup.innerHTML = `
                            <h3 style="margin-top: 0; color: #fff; border-bottom: 2px solid #555; padding-bottom: 10px;">Détails de l'adresse</h3>
                            <p style="font-size: 11px; word-break: break-all; background: #222; padding: 10px; border-radius: 5px; color: #ddd; font-family: monospace;">${{address}}</p>
                            ${{riskHTML}}
                            <div style="margin-top: 15px;">
                                <button onclick="window.open('https://explorer.kaspa.org/addresses/${{address}}', '_blank')" 
                                        style="width: 100%; padding: 12px; margin: 5px 0; cursor: pointer; background-color: #4CAF50; color: white; border: none; border-radius: 5px; font-size: 14px; font-weight: bold;">
                                    Voir sur Kaspa Explorer
                                </button>
                                <button onclick="navigator.clipboard.writeText('${{address}}').then(function() {{ alert('Adresse copiée dans le presse-papier !'); }}).catch(function(err) {{ alert('Erreur lors de la copie'); }});" 
                                        style="width: 100%; padding: 12px; margin: 5px 0; cursor: pointer; background-color: #2196F3; color: white; border: none; border-radius: 5px; font-size: 14px; font-weight: bold;">
                                    Copier l'adresse
                                </button>
                                <button onclick="document.getElementById('addressPopup').remove()" 
                                        style="width: 100%; padding: 12px; margin: 5px 0; cursor: pointer; background-color: #f44336; color: white; border: none; border-radius: 5px; font-size: 14px; font-weight: bold;">
                                    Fermer
                                </button>
                            </div>
                        `;
                        
                        document.body.appendChild(popup);
                    }}
                }});
                
                // Initialiser l'interface après que le réseau soit prêt
                initInterface();
            }} else {{
                setTimeout(setupClickHandler, 100);
            }}
        }}
        
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', setupClickHandler);
        }} else {{
            setupClickHandler();
        }}
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
    # address="kaspa:qqssy8x2stwk6x7trmw56m8rwfkwul70rpqxrvv789mxqz73pdny2sprry82x"
    address="kaspa:qp2sp0vvrwu4s8pw0j68muu2ta5qar5mehf8ehuvljw5zsrakk5cvx4gvqz7z"

    main(address,nb_cercles=4,limit=50)