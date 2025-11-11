#!/usr/bin/env python3
"""
Script pour vérifier le seuil configuré dans les alertes disk
"""

from config import GRAFANA_URL, API_TOKEN, DISK_USAGE_THRESHOLD
from grafana_utils import make_grafana_request, print_header


def main():
    print_header("Vérification des seuils dans les alertes DISK")
    print(f"URL: {GRAFANA_URL}")
    print(f"Seuil dans config.py: {DISK_USAGE_THRESHOLD}%\n")
    
    # Récupérer les alertes
    rules = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/v1/provisioning/alert-rules",
        api_token=API_TOKEN
    )
    
    if not rules:
        print("✗ Aucune alerte trouvée.")
        return
    
    # Filtrer les alertes disk
    disk_alerts = [
        alert for alert in rules 
        if alert.get('labels', {}).get('type') == 'disk_monitoring'
    ]
    
    print(f"Nombre d'alertes disk trouvées: {len(disk_alerts)}\n")
    print("=" * 100)
    print(f"{'Titre':<60} {'Seuil label':<15} {'Seuil condition'}")
    print("-" * 100)
    
    mismatch_count = 0
    
    for alert in disk_alerts[:10]:  # Afficher les 10 premières
        title = alert.get('title', 'N/A')
        threshold_label = alert.get('labels', {}).get('threshold', 'N/A')
        
        # Extraire le seuil de la condition B
        threshold_condition = 'N/A'
        for data in alert.get('data', []):
            if data.get('refId') == 'B':
                model = data.get('model', {})
                conditions = model.get('conditions', [])
                if conditions:
                    params = conditions[0].get('evaluator', {}).get('params', [])
                    if params:
                        threshold_condition = params[0]
        
        # Vérifier si le seuil correspond
        if str(threshold_label) != str(DISK_USAGE_THRESHOLD) or threshold_condition != DISK_USAGE_THRESHOLD:
            mismatch_count += 1
            marker = "❌"
        else:
            marker = "✓"
        
        print(f"{marker} {title:<58} {threshold_label:<15} {threshold_condition}")
    
    print("=" * 100)
    
    if mismatch_count > 0:
        print(f"\n⚠️  {mismatch_count} alerte(s) ont un seuil incorrect!")
        print(f"   Seuil attendu: {DISK_USAGE_THRESHOLD}%")
        print(f"\n💡 Solution: Recréez les alertes avec:")
        print(f"   python3 gestion-infosaone/creer-alertes-disk.py")
    else:
        print(f"\n✓ Toutes les alertes utilisent le bon seuil ({DISK_USAGE_THRESHOLD}%)")
        print(f"\n💡 Si elles sont toujours en Firing, attendez 1-2 minutes que Grafana les réévalue.")


if __name__ == "__main__":
    main()
