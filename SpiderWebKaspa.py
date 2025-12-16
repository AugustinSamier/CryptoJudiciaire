import requests
import networkx as nx
import matplotlib.pyplot as plt
import argparse

address="kaspa:qqssy8x2stwk6x7trmw56m8rwfkwul70rpqxrvv789mxqz73pdny2sprry82x"
API_KEY="kdp_722ad9825ff1144878629812d69609b0e3084323ec6d4299ffd4cbd4b23a0f2b"

def spiderweb(address,dig_amount,nb_transacs,api_key):
    url = f"https://api.kas.fyi/v1/addresses/{address}/transactions"
    headers = {"x-api-key": api_key}
    response = requests.get(url, headers=headers)
    data = response.json()
 
    print("Nb de transactions: ",len(data["transactions"]))
    
    transacs_key=[]
    for transactions in data["transactions"][:nb_transacs]:
        outs,ins=[],[]
        
        outputs=transactions["outputs"]
        for output in outputs:
            key_out=output["scriptPublicKeyAddress"]
            outs.append(key_out)

        inputs=transactions["inputs"]
        for input in inputs:
            key_in=input["previousOutput"]["scriptPublicKeyAddress"]
            amount=int(input["previousOutput"]["amount"][:dig_amount])
            ins.append([key_in,float(amount/1000)])
        transacs_key.append([ins,outs])
        
    for i in range(len(data["transactions"][:nb_transacs])):
        print(f"Transaction : {i}\nInputs: {transacs_key[i][0]}\nOutputs: {transacs_key[i][1]}")


    name_size=20
    allKey=[]
    G = nx.MultiDiGraph()
    for transac in transacs_key:
        for in_key,amount in transac[0]:
            allKey.append(in_key[:name_size])
        for out_key in transac[1]:
            allKey.append(out_key[:name_size])
        allKey=list(set(allKey))
        G.add_nodes_from(allKey)
        
        
        for in_key,amount in transac[0]:
            for out_key in transac[1]:
                print(in_key[:name_size],"and",out_key[:name_size],"amount: ",amount)
                G.add_edge(in_key[:name_size],out_key[:name_size],amount=amount)
            
    pos = nx.spring_layout(G, seed=42)
    nx.draw_networkx_nodes(G, pos, node_color='skyblue', node_size=1000)
    nx.draw_networkx_labels(G, pos, font_size=8)
    for i, (u, v, k, data) in enumerate(G.edges(keys=True, data=True)):
        rad = 0.15 * (k - len(G[u][v]) // 2)
        nx.draw_networkx_edges(
        G, pos,
        connectionstyle=f'arc3,rad={rad}', 
        arrows=True,                       
        arrowstyle='-|>',                  
        arrowsize=50,                      
        edge_color='black'
        )
        x_mid = (pos[u][0] + pos[v][0]) / 2
        y_mid = (pos[u][1] + pos[v][1]) / 2
        plt.text(x_mid, y_mid + rad, f"{data['amount']} KAS", fontsize=7, color="darkred", ha="center")

    plt.show()

def main():
    parser=argparse.ArgumentParser(description="Arguments")
    parser.add_argument("--address",type=str,help="address Kaspa")
    parser.add_argument("--deci",type=int,default=4,help="Nb de chiffres après la virgule")
    parser.add_argument("--nb_transac",default=100,type=str,help="Nb de transactions")
    parser.add_argument("--APIkey",type=str,help="API key")
    args=parser.parse_args()

    spiderweb(args.address,args.deci,args.nb_transac,args.APIkey)

if __name__=="__main__":
    main()