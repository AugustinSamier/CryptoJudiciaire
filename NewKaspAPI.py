import requests
from pyvis.network import Network
import time
import os
import json

URLADDRESS="https://api.kaspa.org/addresses/"
URLTRANSAC="https://api.kaspa.org/transactions/"
CACHE_FILE="transaction_cache.txt"

def get_address_data(address):
    return requests.get(URLADDRESS+address+"/full-transactions").json()

def verify_name(address):
    global NAME_CACHE
    if address in NAME_CACHE:
        return NAME_CACHE[address]
    
    name=requests.get(URLADDRESS+address+"/name").json()
    NAME_CACHE[address]=name
    return name

TRANSACTION_CACHE={}
NAME_CACHE={}

def load_cache():
    global TRANSACTION_CACHE,NAME_CACHE
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data=json.load(f)
                TRANSACTION_CACHE=data.get("transactions",{})
                NAME_CACHE=data.get("names",{})
            print(f"Cache chargé: {len(TRANSACTION_CACHE)} transactions, {len(NAME_CACHE)} names")
        except Exception as e:
            print(f"Erreur lors du chargement du cache: {e}")
            TRANSACTION_CACHE={}
            NAME_CACHE={}
    else:
        print("Aucun cache existant trouvé")

def save_cache():
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "transactions":TRANSACTION_CACHE,
                "names":NAME_CACHE
                }, f, indent=2)
        print(f"Cache sauvegardé: {len(TRANSACTION_CACHE)} transactions, {len(NAME_CACHE)} names")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde du cache: {e}")

def get_transaction_cached(tx_hash):
    if tx_hash in TRANSACTION_CACHE:
        return TRANSACTION_CACHE[tx_hash]
    
    try:
        response=requests.get(URLTRANSAC+tx_hash)
        data=response.json()
    except:
        print(tx_hash)
        try:
            time.sleep(1)
            response=requests.get(URLTRANSAC+tx_hash)
            data=response.json()
        except:
            print("Last chance")
            time.sleep(2)
            response=requests.get(URLTRANSAC+tx_hash)
            data=response.json()
    TRANSACTION_CACHE[tx_hash]=data
    return data

def get_input_address(input_data):
    old_transac = input_data["previous_outpoint_hash"]
    old_index = int(input_data["previous_outpoint_index"])
    dataTransac = get_transaction_cached(old_transac)
    for old_output in dataTransac["outputs"]:
        if old_output["index"] == old_index:
            return old_output["script_public_key_address"]

def get_input(input):
    old_transac=input["previous_outpoint_hash"]
    old_index=int(input["previous_outpoint_index"])
    """responseTransac=requests.get(URLTRANSAC+old_transac)
    dataTransac=responseTransac.json()"""
    dataTransac=get_transaction_cached(old_transac)
    for old_output in dataTransac["outputs"]:
        if old_output["index"]==old_index:
            return old_output["script_public_key_address"]
        
def get_inputs_ouputs(transac):
    inputs=[]
    outputs=[]

    if transac["inputs"]:
        for input in transac["inputs"]:
            inp=get_input(input)
            ver_name=verify_name(inp)
            if "name" not in ver_name.keys():
                inputs.append(inp)
            else:
                print(ver_name)

    if transac["outputs"]:
        for output in transac["outputs"]:
            output_add=output["script_public_key_address"]
            ver_name=verify_name(output_add)
            if "name" not in ver_name.keys():
                outputs.append(output_add)
            else:
                print(ver_name)

        outputs=[output for output in outputs if output not in inputs]
    
    return inputs,outputs

def explore_address(relations,address,cercle,addrSeen,addrList,futurList):
    data_address=get_address_data(address)
    print("Nb de transactions: ",len(data_address))

    if address not in relations:
        relations[address]={
            "nb_transacs_in":0,
            "nb_transacs_out":0,
            "address_in":{},
            "address_out":{},
            "cercle":cercle
        }

    compteurNewAddr=0

    for i,transac in enumerate(data_address):
        print(f"Transaction : {i+1}/{len(data_address)}")
        inputs,outputs=get_inputs_ouputs(transac)
        for input in inputs:
            if input!=address:
                relations[address]["nb_transacs_in"]+=1
                if input in relations[address]["address_in"]:
                    relations[address]["address_in"][input]+=1
                else:
                    relations[address]["address_in"][input]=1
                    compteurNewAddr+=1
                if input not in addrList and input not in futurList and input not in addrSeen:
                    futurList.append(input)

        for output in outputs:
            if output!=address:
                relations[address]["nb_transacs_out"]+=1
                if output in relations[address]["address_out"]:
                    relations[address]["address_out"][output]+=1
                else:
                    relations[address]["address_out"][output]=1
                    compteurNewAddr+=1
                
            if output not in addrList and output not in futurList and output not in addrSeen:
                futurList.append(output)
    print("Nb new address: ",compteurNewAddr)

    return relations,futurList
    
def create_vis(relations, initial_address,nb_cercles):
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
        
        title_html=f"""
        <div style='background-color: #333; padding: 10px; border-radius: 5px;'>
            <b>Address:</b> {addr}<br>
            <a href='https://explorer.kaspa.org/addresses/{addr}' target='_blank' style='color: #4CAF50;'>🔍 Voir sur Kaspa Explorer</a><br>
            <button onclick="navigator.clipboard.writeText('{addr}'); alert('Adresse copiée!');" style='margin-top: 5px; cursor: pointer;'>📋 Copier l'adresse</button>
        </div>
        """

        net.add_node(addr,label=addr[:10],title=addr,color=color,size=size)

    for source, data in relations.items():
        for target, count in data["address_out"].items():
            if target in relations:
                if source==initial_address:
                    edge_color="#FF0000"
                    label=str(count)
                elif target==initial_address:
                    edge_color= "#FFFF00" 
                    label =str(count)
                else:
                    edge_color= "#666666"
                    label =str(count)

                net.add_edge(source,target,color=edge_color,value=count,title=f"{count} transactions",label=label)
    
    for target, data in relations.items():
        for source, count in data["address_in"].items():
            if source in relations:
                if source==initial_address:
                    edge_color="#FF0000"
                    label=str(count)
                elif target==initial_address:
                    edge_color= "#FFFF00" 
                    label =str(count)
                else:
                    edge_color= "#666666"
                    label =str(count)

                net.add_edge(target,source,color=edge_color,value=count,title=f"{count} transactions",label=label)

    net.set_options("""
    {
        "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true
        },
        "physics": {
            "enabled": true,
            "barnesHut": {
                "gravitationalConstant": -10000,
                "centralGravity": 0.3,
                "springLength": 250,
                "springConstant": 0.01
            }
        }
    }
    """)


    net.show("crypto_circles.html",notebook=False)
    net.save_graph(f"NewAPIGraph_cercle{nb_cercles}.html")

def main(initial_address,nb_cercles):
    load_cache()

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
                relations,futurList=explore_address(relations,addr,cercle,addrSeen,addrList,futurList)
                addrSeen.append(addr)
                i+=1
                print("Nb addr restantes :",len(addrList)-i)
            
        addrList=futurList
        print(len(addrList))
    
    save_cache()
    
    create_vis(relations,initial_address,nb_cercles)

if __name__=="__main__":
    address="kaspa:qqssy8x2stwk6x7trmw56m8rwfkwul70rpqxrvv789mxqz73pdny2sprry82x"
    main(address,4)
    """TODO:
    -Adresse cliquable dans le graph
    -Score de risque par adresse
    -Echelles de couleurs
    """