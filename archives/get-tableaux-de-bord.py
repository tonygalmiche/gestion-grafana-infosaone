#!/usr/bin/env python3
"""
Script pour récupérer les noms des tableaux de bord Grafana
"""

import sys
from typing import List, Dict
from config import GRAFANA_URL, API_TOKEN
from grafana_utils import (
    make_grafana_request,
    save_to_json_file,
    print_header,
    confirm_action,
    format_list_as_string,
    get_safe_value
)

def get_dashboards_with_token(grafana_url: str, api_token: str) -> List[Dict]:
    """
    Récupère la liste des tableaux de bord via API token
    """
    return make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/search?type=dash-db",
        api_token=api_token
    ) or []


def get_dashboards_with_auth(grafana_url: str, username: str, password: str) -> List[Dict]:
    """
    Récupère la liste des tableaux de bord via username/password
    """
    return make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/search?type=dash-db",
        username=username,
        password=password
    ) or []

def display_dashboards(dashboards: List[Dict]):
    """
    Affiche les informations des tableaux de bord
    """
    if not dashboards:
        print("Aucun tableau de bord trouvé.")
        return
    
    print_header(f"Nombre total de tableaux de bord: {len(dashboards)}")
    
    for idx, dashboard in enumerate(dashboards, 1):
        print(f"{idx}. Nom: {get_safe_value(dashboard, 'title')}")
        print(f"   UID: {get_safe_value(dashboard, 'uid')}")
        print(f"   URI: {get_safe_value(dashboard, 'uri')}")
        print(f"   URL: {get_safe_value(dashboard, 'url')}")
        print(f"   Dossier: {get_safe_value(dashboard, 'folderTitle', 'General')}")
        print(f"   Tags: {format_list_as_string(dashboard.get('tags', []))}")
        print()

def main():
    """
    Fonction principale
    """
    print("Récupération des tableaux de bord Grafana...")
    print(f"URL: {GRAFANA_URL}\n")
    
    # Récupération avec API Token
    dashboards = get_dashboards_with_token(GRAFANA_URL, API_TOKEN)
    
    if not dashboards:
        print("✗ Aucun tableau de bord trouvé ou erreur lors de la récupération.")
        sys.exit(1)
    
    # Affichage
    display_dashboards(dashboards)
    
    # Sauvegarde optionnelle
    if confirm_action("Voulez-vous sauvegarder la liste dans un fichier JSON?"):
        save_to_json_file(dashboards, "dashboards.json")

if __name__ == "__main__":
    main()
