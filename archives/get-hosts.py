#!/usr/bin/env python3
"""
Script pour récupérer la liste des hosts depuis TimescaleDB via Grafana
"""

import sys
from typing import List, Dict
from config import GRAFANA_URL, API_TOKEN
from grafana_utils import (
    make_grafana_request,
    save_to_json_file,
    print_header,
    confirm_action,
    get_datasources,
    find_default_datasource,
    query_timescale,
    parse_query_results_to_list
)


def display_hosts(hosts: List[str]):
    """
    Affiche la liste des hosts
    """
    if not hosts:
        print("Aucun host trouvé.")
        return
    
    print_header(f"Liste des hosts ({len(hosts)} trouvés)")
    
    for idx, host in enumerate(hosts, 1):
        print(f"{idx}. {host}")
    
    print(f"\n{'='*80}\n")


def main():
    """
    Fonction principale
    """
    print("Récupération des hosts depuis TimescaleDB via Grafana...")
    print(f"URL: {GRAFANA_URL}\n")
    
    # 1. Récupérer les datasources
    print("1. Récupération des datasources...")
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    
    if not datasources:
        print("✗ Aucune datasource trouvée.")
        sys.exit(1)
    
    # 2. Trouver la datasource par défaut (TimescaleDB)
    default_ds = find_default_datasource(datasources)
    
    if not default_ds:
        print("✗ Aucune datasource par défaut trouvée.")
        sys.exit(1)
    
    print(f"✓ Datasource trouvée: {default_ds.get('name')} (UID: {default_ds.get('uid')})")
    print(f"  Type: {default_ds.get('type')}")
    print(f"  URL: {default_ds.get('url', 'N/A')}\n")
    
    # 3. Exécuter la requête pour récupérer les hosts
    print("2. Récupération des hosts depuis la table 'mem'...")
    
    sql_query = "SELECT DISTINCT host FROM mem ORDER BY host"
    
    results = query_timescale(
        GRAFANA_URL,
        API_TOKEN,
        default_ds.get('uid'),
        sql_query
    )
    
    if not results:
        print("✗ Erreur lors de l'exécution de la requête.")
        sys.exit(1)
    
    # 4. Parser et afficher les résultats
    hosts = parse_query_results_to_list(results)
    
    if not hosts:
        print("⚠️  Aucun host trouvé dans les résultats.")
        print("\nRésultats bruts de l'API:")
        print(results)
        sys.exit(1)
    
    display_hosts(hosts)
    
    # 5. Sauvegarde optionnelle
    if confirm_action("Voulez-vous sauvegarder la liste des hosts dans un fichier JSON?"):
        hosts_data = {
            "datasource": {
                "name": default_ds.get('name'),
                "uid": default_ds.get('uid'),
                "type": default_ds.get('type')
            },
            "query": sql_query,
            "hosts": hosts,
            "count": len(hosts)
        }
        save_to_json_file(hosts_data, "hosts.json")


if __name__ == "__main__":
    main()
