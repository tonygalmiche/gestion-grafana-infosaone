#!/usr/bin/env python3
"""
Script pour créer des alertes Grafana pour chaque host
Alerte si pas de données depuis plus de 10 minutes dans la table mem
"""

import sys
from typing import List, Dict
from config import GRAFANA_URL, API_TOKEN, HOST_NO_DATA_MINUTES
from grafana_utils import (
    make_grafana_request,
    print_header,
    print_section,
    confirm_action,
    get_datasources,
    find_default_datasource,
    get_folders,
    create_or_get_folder,
    check_alert_exists,
    delete_alert_rule,
    delete_alerts_by_label,
    query_timescale,
    parse_query_results_to_list
)


def get_hosts_from_timescale(grafana_url: str, api_token: str, datasource_uid: str) -> List[str]:
    """
    Récupère la liste des hosts depuis TimescaleDB
    """
    sql_query = "SELECT DISTINCT host FROM mem ORDER BY host"
    results = query_timescale(grafana_url, api_token, datasource_uid, sql_query)
    return parse_query_results_to_list(results) if results else []


def create_alert_rule(
    grafana_url: str,
    api_token: str,
    host: str,
    datasource_uid: str,
    folder_uid: str,
    no_data_minutes: int = 10
) -> bool:
    """
    Crée une règle d'alerte pour un host spécifique via l'API Provisioning
    
    IMPORTANT: Les alertes créées via l'API Provisioning sont en lecture seule dans l'UI.
    Pour des alertes éditables, vous devez avoir un token avec les permissions Admin
    et utiliser l'API Ruler.
    
    Args:
        grafana_url: URL de Grafana
        api_token: Token API
        host: Nom du host à surveiller
        datasource_uid: UID de la datasource TimescaleDB
        folder_uid: UID du dossier où créer l'alerte
        no_data_minutes: Nombre de minutes sans données avant alerte (par défaut: 10)
    
    Returns:
        True si succès, False sinon
    """
    alert_title = f"[Host] {host} - Pas de données depuis {no_data_minutes} min"
    
    # Note: La suppression globale est faite avant la boucle de création
    # Pas besoin de vérifier/supprimer ici individuellement
    
    # Calculer les secondes
    no_data_seconds = no_data_minutes * 60
    
    # Requête SQL pour vérifier la dernière donnée reçue
    sql_query = f"""
SELECT 
    EXTRACT(EPOCH FROM (NOW() AT TIME ZONE 'UTC' - MAX(time))) as seconds_since_last_data
FROM mem
WHERE host = '{host}'
"""
    
    # Définition de la règle d'alerte (API Provisioning)
    alert_rule = {
        "title": alert_title,
        "folderUID": folder_uid,
        "ruleGroup": "Host Monitoring",
        "interval": "1m",
        "for": "1m",  # Alerte active après 1 minute (au lieu de 5)
        "condition": "C",
        "data": [
            {
                "refId": "A",
                "queryType": "",
                "relativeTimeRange": {
                    "from": no_data_seconds,
                    "to": 0
                },
                "datasourceUid": datasource_uid,
                "model": {
                    "rawSql": sql_query,
                    "format": "table",
                    "refId": "A"
                }
            },
            {
                "refId": "B",
                "queryType": "",
                "relativeTimeRange": {
                    "from": 0,
                    "to": 0
                },
                "datasourceUid": "-100",
                "model": {
                    "conditions": [
                        {
                            "evaluator": {
                                "params": [0],
                                "type": "gt"
                            },
                            "operator": {
                                "type": "and"
                            },
                            "query": {
                                "params": ["A"]
                            },
                            "type": "query"
                        }
                    ],
                    "datasource": {
                        "type": "__expr__",
                        "uid": "-100"
                    },
                    "expression": "A",
                    "reducer": "last",
                    "type": "reduce",
                    "refId": "B"
                }
            },
            {
                "refId": "C",
                "queryType": "",
                "relativeTimeRange": {
                    "from": 0,
                    "to": 0
                },
                "datasourceUid": "-100",
                "model": {
                    "conditions": [
                        {
                            "evaluator": {
                                "params": [no_data_seconds],
                                "type": "gt"
                            },
                            "operator": {
                                "type": "and"
                            },
                            "query": {
                                "params": ["C"]
                            },
                            "type": "query"
                        }
                    ],
                    "datasource": {
                        "type": "__expr__",
                        "uid": "-100"
                    },
                    "expression": "B",
                    "type": "threshold",
                    "refId": "C"
                }
            }
        ],
        "noDataState": "Alerting",
        "execErrState": "Alerting",
        "annotations": {
            "description": f"Le host {host} n'a envoyé aucune donnée dans la table 'mem' depuis plus de {no_data_minutes} minutes.",
            "summary": f"Pas de données pour {host}"
        },
        "labels": {
            "host": host,
            "severity": "warning",
            "type": "host_monitoring"
        }
    }
    
    result = make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/v1/provisioning/alert-rules",
        api_token=api_token,
        method="POST",
        data=alert_rule
    )
    
    if result:
        print(f"  ✓ Alerte créée: {alert_title}")
        return True
    else:
        print(f"  ✗ Erreur lors de la création de l'alerte: {alert_title}")
        return False


def main():
    """
    Fonction principale
    """
    print_header("Création d'alertes Grafana pour la surveillance des hosts")
    print(f"URL: {GRAFANA_URL}\n")
    
    # 1. Récupérer la datasource
    print("1. Récupération de la datasource TimescaleDB...")
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    
    if not datasources:
        print("✗ Aucune datasource trouvée.")
        sys.exit(1)
    
    default_ds = find_default_datasource(datasources)
    
    if not default_ds:
        print("✗ Aucune datasource par défaut trouvée.")
        sys.exit(1)
    
    print(f"✓ Datasource: {default_ds.get('name')} (UID: {default_ds.get('uid')})\n")
    
    # 2. Récupérer les hosts
    print("2. Récupération de la liste des hosts...")
    hosts = get_hosts_from_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'))
    
    if not hosts:
        print("✗ Aucun host trouvé.")
        sys.exit(1)
    
    print(f"✓ {len(hosts)} host(s) trouvé(s):")
    for host in hosts:
        print(f"   - {host}")
    print()
    
    # 3. Créer ou récupérer le dossier pour les alertes
    print("3. Création/récupération du dossier pour les alertes...")
    folder = create_or_get_folder(GRAFANA_URL, API_TOKEN, "Host Monitoring Alerts")
    
    if not folder:
        print("✗ Impossible de créer/récupérer le dossier.")
        sys.exit(1)
    
    print()
    
    # 4. Confirmation avant création
    if not confirm_action(f"Créer des alertes pour {len(hosts)} host(s)?", default=True):
        print("Opération annulée.")
        sys.exit(0)
    
    # 5. Supprimer toutes les alertes host existantes
    print("\n4. Suppression des alertes host existantes...")
    delete_alerts_by_label(GRAFANA_URL, API_TOKEN, 'type', 'host_monitoring')
    
    # 6. Créer les alertes
    print_section(f"Création des alertes pour {len(hosts)} host(s)")
    
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    for idx, host in enumerate(hosts, 1):
        print(f"\n[{idx}/{len(hosts)}] Création de l'alerte pour: {host}")
        
        if create_alert_rule(
            GRAFANA_URL,
            API_TOKEN,
            host,
            default_ds.get('uid'),
            folder.get('uid'),
            HOST_NO_DATA_MINUTES
        ):
            success_count += 1
        else:
            failed_count += 1
    
    # 7. Résumé
    print_header("RÉSUMÉ")
    print(f"Total de hosts: {len(hosts)}")
    print(f"✓ Alertes créées avec succès: {success_count}")
    if failed_count > 0:
        print(f"✗ Échecs: {failed_count}")
    print(f"\n{'='*80}\n")
    
    print(f"Les alertes se déclencheront si un host n'envoie pas de données pendant plus de {HOST_NO_DATA_MINUTES} minutes.")
    print(f"Vous pouvez les consulter dans Grafana → Alerting → Alert rules")


if __name__ == "__main__":
    main()
