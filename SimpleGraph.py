import requests
import networkx as nx
import matplotlib.pyplot as plt
import argparse
from pyvis.network import Network

def make_graph(G,address,limit,allAddresses,transac,addresses=None):
    url=f"https://api.kas.fyi/v1/addresses/{address}/"
    headers = {"x-api-key": API_KEY}

    responseTag=requests.get(url+"tag", headers=headers)
    dataTag=responseTag.json()

    if "tag" in dataTag:
        print("Exchange platform",dataTag)
        return G,None,transac

    responseTransac = requests.get(url+"transactions?limit={limit}", headers=headers)
    data=responseTransac.json()

    try:
        for transactions in data["transactions"]:
            for input in transactions["inputs"]:
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
        for income in transac:
            if income not in addresses and income not in allAddresses:
                addresses.append(income)
            for outcome in transac[income]:
                G.add_edge(income[:15],outcome[:15],weight=transac[income][outcome])
                if outcome not in addresses and outcome not in allAddresses:
                    addresses.append(outcome)
    except:
        print("ERREUR : ",address)
    return G,addresses,transac


COLOR=[
        "blue",
        "red",
        "orange",
        "yellow",
        "black"
    ]


def main(args):
    outcome=args.address
    nb_cercles=args.nbCercles

    G=nx.DiGraph()
    allOutcomes=[]
    allOutcomes.append([outcome])
    allAddresses=[]
    allAddresses.extend([outcome])
    print(len(allAddresses))
    colors=[]
    transac={}
    for cercle in range(nb_cercles):
        print("Size : ",len(allOutcomes[cercle]))
        for i in range(len(allOutcomes[cercle])):
            colors.append(COLOR[cercle])
            print(allOutcomes[cercle][i])
            G,outcomes,transac=make_graph(G,allOutcomes[cercle][i],transac=transac,limit=args.limit,allAddresses=allAddresses)
            if outcomes is not None:
                allOutcomes.append(outcomes)
                allAddresses.extend(outcomes)
            print(len(allAddresses))
    for i in range(len(G)-len(colors)):
        colors.append(COLOR[nb_cercles-1])
    print(len(G))
    plt.figure(figsize=(18, 14))

    pos = nx.spring_layout(
        G,
        k=3,
        iterations=300
    )

    nx.draw(
        G, pos,
        with_labels=True,
        node_color=colors,
        node_size=1800,
        font_size=8,
        arrowsize=15
    )

    edge_labels = nx.get_edge_attributes(G, 'weight')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=7)

    plt.title("Kaspa Graph")
    plt.show()

if __name__=="__main__":
    parser=argparse.ArgumentParser(description="Arguments")
    parser.add_argument("--address",type=str,help="address Kaspa")
    parser.add_argument("--APIkey",type=str,help="API key")
    parser.add_argument("--limit",type=int,default=3,help="Limite de transactions")
    parser.add_argument("--nbCercles",type=int,default=3,help="Nombre de cercles")
    args=parser.parse_args()
    API_KEY=args.APIkey
    main(args)