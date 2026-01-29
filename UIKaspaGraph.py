def main(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        html_content = f.read()

    custom_js = """
    <script type="text/javascript">
        network.on("click", function(params) {
            if (params.nodes.length > 0) {
                var nodeId = params.nodes[0];
                var address = nodeId;
                
                // Supprimer toute popup existante
                var existingPopup = document.getElementById('addressPopup');
                if (existingPopup) {
                    existingPopup.remove();
                }
                
                // Créer une popup personnalisée
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
                
                popup.innerHTML = `
                    <h3 style="margin-top: 0; word-break: break-all;">Adresse:</h3>
                    <p style="font-size: 12px; word-break: break-all; background: #222; padding: 10px; border-radius: 5px;">${address}</p>
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
    </script>
    """
    
    html_content = html_content.replace('</body>', custom_js + '</body>')
    newName=filename.split(".")[0]+"TESTMODIF"+".html"

    with open(newName, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Graphique sauvegardé: {newName}")

if __name__=="__main__":
    filename="NewAPIGraph_cercle3.html"
    main(filename)