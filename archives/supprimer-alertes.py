#!/usr/bin/env python3
"""
Script pour supprimer toutes les alertes de surveillance des hosts
"""

import sys
from typing import List, Dict
from config import GRAFANA_URL, API_TOKEN
from grafana_utils import (
    make_grafana_request,
    print_header,
    confirm_action
)


def get_all_provisioned_alerts(grafana_url: str, api_token: str) -> List[Dict]:
    """
    Récupère toutes les alertes provisionnées
    """
    result = make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/v1/provisioning/alert-rules",
        api_token=api_token
    )
    return result if result else []


def delete_provisioned_alert(grafana_url: str, api_token: str, alert_uid: str) -> bool:
    """
    Supprime une alerte provisionnée
    """
    result = make_grafana_request(
        grafana_url=grafana_url,
        endpoint=f"/api/v1/provisioning/alert-rules/{alert_uid}",
        api_token=api_token,
        method="DELETE"
    )
    return result is not None


def main():
    """
    Fonction principale
    """
    print_header("Suppression des alertes de surveillance des hosts")
    print(f"URL: {GRAFANA_URL}\n")
    
    # Récupérer toutes les alertes provisionnées
    print("Récupération des alertes existantes...")
    alerts = get_all_provisioned_alerts(GRAFANA_URL, API_TOKEN)
    
    if not alerts:
        print("✓ Aucune alerte provisionnée trouvée.")
        return
    
    # Filtrer les alertes de type host monitoring
    host_alerts = [
        alert for alert in alerts 
        if alert.get('title', '').startswith('[Host]') or 
           alert.get('labels', {}).get('type') == 'host_monitoring'
    ]
    
    if not host_alerts:
        print(f"ℹ️  {len(alerts)} alerte(s) trouvée(s), mais aucune alerte de host monitoring.")
        return
    
    print(f"\n{len(host_alerts)} alerte(s) de host monitoring trouvée(s):")
    for idx, alert in enumerate(host_alerts, 1):
        print(f"  {idx}. {alert.get('title')} (UID: {alert.get('uid')})")
    
    print()
    
    # Confirmation
    if not confirm_action(f"Supprimer ces {len(host_alerts)} alerte(s)?"):
        print("Opération annulée.")
        return
    
    # Suppression
    print(f"\nSuppression en cours...")
    success = 0
    failed = 0
    
    for idx, alert in enumerate(host_alerts, 1):
        title = alert.get('title')
        uid = alert.get('uid')
        
        print(f"[{idx}/{len(host_alerts)}] Suppression: {title}...", end=" ")
        
        if delete_provisioned_alert(GRAFANA_URL, API_TOKEN, uid):
            print("✓")
            success += 1
        else:
            print("✗")
            failed += 1
    
    # Résumé
    print_header("RÉSUMÉ")
    print(f"✓ Alertes supprimées: {success}")
    if failed > 0:
        print(f"✗ Échecs: {failed}")
    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    main()
