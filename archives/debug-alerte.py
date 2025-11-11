#!/usr/bin/env python3
"""
Script pour débugger une alerte spécifique et voir pourquoi elle est en Firing
"""

import sys
from config import GRAFANA_URL, API_TOKEN, DISK_USAGE_THRESHOLD
from grafana_utils import (
    make_grafana_request,
    print_header,
    get_datasources,
    find_default_datasource,
    query_timescale
)


def debug_alert(alert_title: str):
    """
    Debug une alerte spécifique
    """
    # Récupérer l'alerte
    rules = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/v1/provisioning/alert-rules",
        api_token=API_TOKEN
    )
    
    if not rules:
        print("✗ Aucune alerte trouvée.")
        return
    
    # Trouver l'alerte
    alert = None
    for rule in rules:
        if alert_title in rule.get('title', ''):
            alert = rule
            break
    
    if not alert:
        print(f"✗ Alerte '{alert_title}' non trouvée.")
        return
    
    print_header(f"Debug de l'alerte: {alert.get('title')}")
    print(f"UID: {alert.get('uid')}")
    print(f"Groupe: {alert.get('ruleGroup')}")
    print(f"Condition: {alert.get('condition')}")
    print(f"For: {alert.get('for')}")
    print(f"Labels: {alert.get('labels')}")
    print()
    
    # Extraire le seuil de la condition
    print("Analyse de la condition:")
    for data in alert.get('data', []):
        ref_id = data.get('refId')
        print(f"\n  RefId {ref_id}:")
        
        if ref_id == 'A':
            sql = data.get('model', {}).get('rawSql', '')
            print(f"    SQL: {sql}")
        elif ref_id == 'B':
            conditions = data.get('model', {}).get('conditions', [])
            if conditions:
                evaluator = conditions[0].get('evaluator', {})
                threshold = evaluator.get('params', [None])[0]
                op_type = evaluator.get('type', 'N/A')
                print(f"    Type: reduce + threshold")
                print(f"    Opérateur: {op_type}")
                print(f"    Seuil: {threshold}")
    
    print()
    
    # Récupérer l'état actuel
    print("État actuel de l'alerte:")
    instances = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/alertmanager/grafana/api/v2/alerts",
        api_token=API_TOKEN
    )
    
    if instances:
        for inst in instances:
            labels = inst.get('labels', {})
            if alert.get('title') == labels.get('alertname'):
                state = inst.get('status', {}).get('state', 'N/A')
                print(f"  État: {state}")
                print(f"  Depuis: {inst.get('startsAt', 'N/A')}")
                
                # Afficher les valeurs
                annotations = inst.get('annotations', {})
                print(f"  Annotations: {annotations}")
                print(f"  Labels: {labels}")
                break
    
    print()
    
    # Tester la requête SQL directement
    print("Test de la requête SQL directement:")
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    default_ds = find_default_datasource(datasources)
    
    if default_ds:
        # Extraire le host du titre
        host = alert.get('labels', {}).get('host', '')
        if host:
            sql = f"SELECT MAX(used_percent) as max_used_percent FROM disk WHERE host = '{host}'"
            print(f"  SQL: {sql}")
            
            result = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql)
            
            if result:
                for res in result.get('results', {}).values():
                    for frame in res.get('frames', []):
                        values = frame.get('data', {}).get('values', [])
                        if values and len(values) > 0 and len(values[0]) > 0:
                            usage = values[0][0]
                            print(f"  Résultat: {usage:.2f}%")
                            print(f"  Seuil configuré: {DISK_USAGE_THRESHOLD}%")
                            
                            if usage > DISK_USAGE_THRESHOLD:
                                print(f"  ✗ {usage:.2f}% > {DISK_USAGE_THRESHOLD}% → Devrait être en FIRING")
                            else:
                                print(f"  ✓ {usage:.2f}% ≤ {DISK_USAGE_THRESHOLD}% → Devrait être NORMAL")


def main():
    if len(sys.argv) > 1:
        alert_title = " ".join(sys.argv[1:])
    else:
        alert_title = input("Entrez une partie du titre de l'alerte à débugger (ex: 'grafana12'): ")
    
    debug_alert(alert_title)


if __name__ == "__main__":
    main()
