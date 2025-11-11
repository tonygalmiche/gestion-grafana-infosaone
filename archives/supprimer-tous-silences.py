#!/usr/bin/env python3
"""
Script pour supprimer TOUS les silences Grafana
"""

from config import GRAFANA_URL, API_TOKEN
from grafana_utils import make_grafana_request

def list_silences():
    """Liste tous les silences"""
    return make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/alertmanager/grafana/api/v2/silences",
        api_token=API_TOKEN
    )

def delete_silence(silence_id):
    """Supprime un silence"""
    return make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint=f"/api/alertmanager/grafana/api/v2/silence/{silence_id}",
        api_token=API_TOKEN,
        method="DELETE"
    )

def main():
    print("Récupération des silences...")
    silences = list_silences()
    
    if not silences:
        print("Aucun silence trouvé.")
        return
    
    print(f"\n{len(silences)} silence(s) trouvé(s):\n")
    
    for silence in silences:
        silence_id = silence.get('id')
        status = silence.get('status', {}).get('state', 'unknown')
        comment = silence.get('comment', 'N/A')
        
        print(f"ID: {silence_id}")
        print(f"  Status: {status}")
        print(f"  Comment: {comment}")
        
        confirm = input(f"  Supprimer ce silence ? (O/n): ").strip().lower()
        if confirm in ['o', 'y', '']:
            result = delete_silence(silence_id)
            if result is not None:
                print(f"  ✓ Supprimé\n")
            else:
                print(f"  ✗ Erreur de suppression\n")
        else:
            print(f"  → Ignoré\n")

if __name__ == "__main__":
    main()
