#!/usr/bin/env python3
"""
Script pour récupérer la liste des alertes Grafana
"""

import sys
from typing import List, Dict
from datetime import datetime
from config import GRAFANA_URL, API_TOKEN
from grafana_utils import (
    make_grafana_request,
    save_to_json_file,
    print_header,
    print_section,
    confirm_action,
    format_list_as_string,
    truncate_text,
    get_safe_value
)

def get_alert_rules(grafana_url: str, api_token: str) -> Dict:
    """
    Récupère toutes les règles d'alerte (Alerting v9+)
    """
    result = make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/ruler/grafana/api/v1/rules",
        api_token=api_token
    )
    return result if result else {}


def get_provisioned_alert_rules(grafana_url: str, api_token: str) -> List[Dict]:
    """
    Récupère les règles d'alerte via l'API provisioning
    """
    result = make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/v1/provisioning/alert-rules",
        api_token=api_token
    )
    return result if result else []


def get_alert_instances(grafana_url: str, api_token: str) -> List[Dict]:
    """
    Récupère les instances d'alertes actives
    """
    result = make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/alertmanager/grafana/api/v2/alerts",
        api_token=api_token
    )
    return result if result else []

def display_alert_rules(rules_data: Dict):
    """
    Affiche les règles d'alerte (format ruler API)
    """
    if not rules_data:
        print("Aucune règle d'alerte trouvée (ruler API).")
        return
    
    print_header("RÈGLES D'ALERTE (Ruler API)")
    
    total_rules = 0
    for namespace, groups in rules_data.items():
        print(f"\n📁 Namespace: {namespace}")
        for group in groups:
            group_name = get_safe_value(group, 'name')
            print(f"  📂 Groupe: {group_name}")
            print(f"     Intervalle: {get_safe_value(group, 'interval')}")
            
            rules = group.get('rules', [])
            for idx, rule in enumerate(rules, 1):
                total_rules += 1
                grafana_alert = rule.get('grafana_alert', {})
                print(f"\n     {idx}. Alerte: {get_safe_value(grafana_alert, 'title')}")
                print(f"        UID: {get_safe_value(grafana_alert, 'uid')}")
                print(f"        Condition: {get_safe_value(grafana_alert, 'condition')}")
                print(f"        Durée (for): {get_safe_value(rule, 'for')}")
                
                # Annotations
                annotations = rule.get('annotations', {})
                if annotations:
                    print(f"        Description: {get_safe_value(annotations, 'description')}")
                
                # Labels
                labels = rule.get('labels', {})
                if labels:
                    label_str = format_list_as_string([f'{k}={v}' for k, v in labels.items()])
                    print(f"        Labels: {label_str}")
    
    print(f"\n{'='*80}")
    print(f"Nombre total de règles d'alerte: {total_rules}")
    print(f"{'='*80}\n")

def display_provisioned_rules(rules: List[Dict]):
    """
    Affiche les règles d'alerte (format provisioning API)
    """
    if not rules:
        print("Aucune règle d'alerte trouvée (provisioning API).")
        return
    
    print_header("RÈGLES D'ALERTE (Provisioning API)")
    
    for idx, rule in enumerate(rules, 1):
        print(f"{idx}. Titre: {get_safe_value(rule, 'title')}")
        print(f"   UID: {get_safe_value(rule, 'uid')}")
        print(f"   Dossier: {get_safe_value(rule, 'folderUID')}")
        print(f"   Groupe: {get_safe_value(rule, 'ruleGroup')}")
        print(f"   Condition: {get_safe_value(rule, 'condition')}")
        print(f"   État: {'Actif' if not rule.get('isPaused', False) else 'En pause'}")
        print(f"   Durée: {get_safe_value(rule, 'for')}")
        
        # Annotations
        annotations = rule.get('annotations', {})
        if annotations:
            description = truncate_text(get_safe_value(annotations, 'description'), 100)
            print(f"   Description: {description}")
        
        # Labels
        labels = rule.get('labels', {})
        if labels:
            label_str = format_list_as_string([f'{k}={v}' for k, v in labels.items()])
            print(f"   Labels: {label_str}")
        
        print()
    
    print(f"{'='*80}")
    print(f"Nombre total de règles: {len(rules)}")
    print(f"{'='*80}\n")


def display_alert_instances(instances: List[Dict]):
    """
    Affiche les instances d'alertes actives
    """
    if not instances:
        print("Aucune instance d'alerte active.")
        return
    
    print_header("INSTANCES D'ALERTES ACTIVES")
    
    for idx, instance in enumerate(instances, 1):
        labels = instance.get('labels', {})
        annotations = instance.get('annotations', {})
        
        print(f"{idx}. Alerte: {get_safe_value(labels, 'alertname')}")
        print(f"   État: {instance.get('status', {}).get('state', 'N/A')}")
        print(f"   Début: {get_safe_value(instance, 'startsAt')}")
        
        description = truncate_text(get_safe_value(annotations, 'description'), 100)
        print(f"   Description: {description}")
        
        label_str = format_list_as_string([f'{k}={v}' for k, v in labels.items()])
        print(f"   Labels: {label_str}")
        print()
    
    print(f"{'='*80}")
    print(f"Nombre total d'instances actives: {len(instances)}")
    print(f"{'='*80}\n")

def main():
    """
    Fonction principale
    """
    print("Récupération des alertes Grafana...")
    print(f"URL: {GRAFANA_URL}\n")
    
    # Récupération via différentes APIs
    print("1. Récupération via Ruler API...")
    ruler_rules = get_alert_rules(GRAFANA_URL, API_TOKEN)
    
    print("2. Récupération via Provisioning API...")
    provisioned_rules = get_provisioned_alert_rules(GRAFANA_URL, API_TOKEN)
    
    print("3. Récupération des instances actives...")
    alert_instances = get_alert_instances(GRAFANA_URL, API_TOKEN)
    
    # Affichage
    if provisioned_rules:
        display_provisioned_rules(provisioned_rules)
    elif ruler_rules:
        display_alert_rules(ruler_rules)
    else:
        print("\n⚠️  Aucune règle d'alerte trouvée.\n")
    
    if alert_instances:
        display_alert_instances(alert_instances)
    
    # Sauvegarde optionnelle
    if confirm_action("Voulez-vous sauvegarder les alertes dans des fichiers JSON?"):
        if provisioned_rules:
            save_to_json_file(provisioned_rules, "alert_rules.json")
        elif ruler_rules:
            save_to_json_file(ruler_rules, "alert_rules_ruler.json")
        if alert_instances:
            save_to_json_file(alert_instances, "alert_instances.json")

if __name__ == "__main__":
    main()
