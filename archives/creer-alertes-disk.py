#!/usr/bin/env python3
"""
Script pour créer des alertes Grafana pour la surveillance de l'utilisation disque
Alerte si used_percent dépasse le seuil configuré
"""

import sys
from typing import List, Dict
from config import GRAFANA_URL, API_TOKEN, DISK_USAGE_THRESHOLD
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


def get_hosts_from_disk_table(grafana_url: str, api_token: str, datasource_uid: str) -> List[str]:
    """
    Récupère la liste des hosts depuis la table disk de TimescaleDB
    """
    sql_query = """
        SELECT DISTINCT host 
        FROM disk 
        where host like '%filets%' 
        ORDER BY host
    """
    results = query_timescale(grafana_url, api_token, datasource_uid, sql_query)
    return parse_query_results_to_list(results) if results else []


def create_disk_alert_rule(
    grafana_url: str,
    api_token: str,
    host: str,
    datasource_uid: str,
    folder_uid: str,
    threshold: int,
    enable_notifications: bool = True
) -> bool:
    """
    Crée une règle d'alerte pour surveiller l'utilisation disque d'un host
    
    Args:
        grafana_url: URL de Grafana
        api_token: Token API
        host: Nom du host à surveiller
        datasource_uid: UID de la datasource TimescaleDB
        folder_uid: UID du dossier où créer l'alerte
        threshold: Seuil en pourcentage (ex: 80)
    
    Returns:
        True si succès, False sinon
    """
    alert_title = f"[Disk] {host} - Utilisation disque > {threshold}%"
    
    # Note: La suppression globale est faite avant la boucle de création
    # Pas besoin de vérifier/supprimer ici individuellement
    
    # Requête SQL pour récupérer le max de used_percent
    # Note: Le filtre de temps est géré par relativeTimeRange, pas par la requête SQL
    sql_query = f"SELECT MAX(used_percent) as max_used_percent FROM disk WHERE host = '{host}'"
    
    # Définition de la règle d'alerte
    # Utiliser un timestamp dans le nom du groupe pour forcer la réévaluation
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    
    alert_rule = {
        "title": alert_title,
        "folderUID": folder_uid,
        "ruleGroup": f"Disk Monitoring {timestamp}",  # Nom unique à chaque création
        "interval": "1m",
        "for": "0m",  # Alerte immédiate (pas de délai)
        "condition": "C",  # Changé de B à C
        "data": [
            {
                "refId": "A",
                "queryType": "",
                "relativeTimeRange": {
                    "from": 300,
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
                                "params": [threshold],
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
        "noDataState": "NoData",
        "execErrState": "Alerting",
        "annotations": {
            "description": f"Le host {host} a une utilisation disque de {{{{ printf \"%.0f\" $values.B.Value }}}}% (seuil: {threshold}%).",
            "summary": f"Alerte disque sur {host}: {{{{ printf \"%.0f\" $values.B.Value }}}}% (seuil: {threshold}%)"
        },
        "labels": {
            "host": host,
            "severity": "warning",
            "type": "disk_monitoring",
            "threshold": str(threshold),
            "notifications": "enabled" if enable_notifications else "disabled"
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
    print_header("Gestion des alertes Grafana - Surveillance disque")
    print(f"URL: {GRAFANA_URL}")
    print(f"Seuil configuré: {DISK_USAGE_THRESHOLD}%\n")
    
    # Menu principal
    print("Que voulez-vous faire ?")
    print("1. Créer les alertes disk AVEC notifications email")
    print("2. Créer les alertes disk SANS notifications email (pour script externe)")
    print("3. Supprimer toutes les alertes disk existantes")
    print("4. Quitter")
    
    choice = input("\nVotre choix (1-4): ").strip()
    
    if choice == "4":
        print("\nAu revoir!")
        sys.exit(0)
    
    # 1. Récupérer la datasource
    print("\n1. Récupération de la datasource TimescaleDB...")
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    
    if not datasources:
        print("✗ Aucune datasource trouvée.")
        sys.exit(1)
    
    default_ds = find_default_datasource(datasources)
    
    if not default_ds:
        print("✗ Aucune datasource par défaut trouvée.")
        sys.exit(1)
    
    print(f"✓ Datasource: {default_ds.get('name')} (UID: {default_ds.get('uid')})\n")
    
    if choice == "3":
        # Mode suppression uniquement
        print("2. Suppression des alertes disque existantes...")
        deleted = delete_alerts_by_label(GRAFANA_URL, API_TOKEN, 'type', 'disk_monitoring')
        print(f"\n✓ Opération terminée.")
        sys.exit(0)
    
    elif choice not in ["1", "2"]:
        print("\n✗ Choix invalide.")
        sys.exit(1)
    
    # Déterminer si les notifications sont activées
    enable_notifications = (choice == "1")
    notification_status = "AVEC" if enable_notifications else "SANS"
    
    # Mode création (choice == "1" ou "2")
    # 2. Récupérer les hosts
    print("2. Récupération de la liste des hosts depuis la table 'disk'...")
    hosts = get_hosts_from_disk_table(GRAFANA_URL, API_TOKEN, default_ds.get('uid'))
    
    if not hosts:
        print("✗ Aucun host trouvé.")
        sys.exit(1)
    
    print(f"✓ {len(hosts)} host(s) trouvé(s):")
    for host in hosts:
        print(f"   - {host}")
    print()
    
    # 3. Créer ou récupérer le dossier pour les alertes
    print("3. Création/récupération du dossier pour les alertes...")
    folder = create_or_get_folder(GRAFANA_URL, API_TOKEN, "Disk Monitoring Alerts")
    
    if not folder:
        print("✗ Impossible de créer/récupérer le dossier.")
        sys.exit(1)
    
    print()
    
    # 4. Supprimer toutes les alertes disque existantes
    print("4. Suppression des alertes disque existantes...")
    delete_alerts_by_label(GRAFANA_URL, API_TOKEN, 'type', 'disk_monitoring')
    print()
    
    # 5. Créer les alertes
    print_section(f"Création des alertes {notification_status} notifications pour {len(hosts)} host(s)")
    
    success_count = 0
    failed_count = 0
    
    for idx, host in enumerate(hosts, 1):
        print(f"\n[{idx}/{len(hosts)}] Création de l'alerte pour: {host}")
        
        if create_disk_alert_rule(
            GRAFANA_URL,
            API_TOKEN,
            host,
            default_ds.get('uid'),
            folder.get('uid'),
            DISK_USAGE_THRESHOLD,
            enable_notifications
        ):
            success_count += 1
        else:
            failed_count += 1
    
    # 7. Résumé
    print_header("RÉSUMÉ")
    print(f"Mode: Notifications {notification_status.lower()}")
    print(f"Total de hosts: {len(hosts)}")
    print(f"✓ Alertes créées avec succès: {success_count}")
    if failed_count > 0:
        print(f"✗ Échecs: {failed_count}")
    print(f"\n{'='*80}\n")
    
    print(f"Les alertes se déclencheront si l'utilisation disque dépasse {DISK_USAGE_THRESHOLD}% pendant plus de 5 minutes.")
    print(f"Vous pouvez modifier le seuil dans config.py (DISK_USAGE_THRESHOLD)")
    print(f"Consultez les alertes dans Grafana → Alerting → Alert rules")


if __name__ == "__main__":
    main()
