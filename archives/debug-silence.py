#!/usr/bin/env python3
"""
Script pour supprimer un silence via curl (debug)
"""

import subprocess
import json
from config import GRAFANA_URL, API_TOKEN
from grafana_utils import make_grafana_request


def list_and_delete_silences():
    """
    Liste et supprime les silences via différentes méthodes
    """
    # 1. Lister les silences
    print("1. Liste des silences:")
    silences = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/alertmanager/grafana/api/v2/silences",
        api_token=API_TOKEN
    )
    
    if not silences:
        print("Aucun silence trouvé.")
        return
    
    for silence in silences:
        sid = silence.get('id')
        status = silence.get('status', {}).get('state', 'unknown')
        print(f"  - ID: {sid}, État: {status}")
        
        if status == 'active':
            print(f"\n2. Tentative de suppression du silence {sid}...")
            
            # Méthode 1: Via make_grafana_request
            print("\n  Méthode 1: Via make_grafana_request DELETE")
            result = make_grafana_request(
                grafana_url=GRAFANA_URL,
                endpoint=f"/api/alertmanager/grafana/api/v2/silence/{sid}",
                api_token=API_TOKEN,
                method="DELETE"
            )
            print(f"  Résultat: {result}")
            
            # Méthode 2: Via curl direct
            print("\n  Méthode 2: Via curl")
            curl_cmd = [
                'curl', '-X', 'DELETE',
                '-H', f'Authorization: Bearer {API_TOKEN}',
                '-H', 'Content-Type: application/json',
                f'{GRAFANA_URL}/api/alertmanager/grafana/api/v2/silence/{sid}',
                '-v'
            ]
            
            print(f"  Commande: {' '.join(curl_cmd[:6])}... [URL masquée]")
            result = subprocess.run(curl_cmd, capture_output=True, text=True)
            print(f"  Code retour: {result.returncode}")
            print(f"  Sortie: {result.stdout}")
            if result.stderr:
                print(f"  Erreur: {result.stderr[-500:]}")  # Derniers 500 chars


if __name__ == "__main__":
    list_and_delete_silences()
