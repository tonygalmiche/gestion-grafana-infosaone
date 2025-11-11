#!/usr/bin/env python3
"""
Script pour voir les alertes actives avec les valeurs actuelles du disque
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


def get_current_disk_usage_for_host(grafana_url: str, api_token: str, datasource_uid: str, host: str):
    """
    Récupère l'utilisation disque actuelle d'un host
    """
    sql_query = f"""
SELECT MAX(used_percent) as current_usage
FROM disk 
WHERE host = '{host}'
  AND time > NOW() - INTERVAL '24 hours'
"""
    
    results = query_timescale(grafana_url, api_token, datasource_uid, sql_query)
    
    if not results:
        return None
    
    # Debug: afficher la structure
    # print(f"DEBUG {host}: {results}")
    
    try:
        for result in results.get('results', {}).values():
            for frame in result.get('frames', []):
                data = frame.get('data', {})
                values = data.get('values', [])
                
                # Les valeurs sont dans values[0][0]
                if values and len(values) > 0 and len(values[0]) > 0:
                    usage = values[0][0]
                    # Vérifier si c'est None ou un nombre
                    if usage is not None:
                        return float(usage)
    except (KeyError, IndexError, TypeError) as e:
        print(f"  Erreur de parsing pour {host}: {e}")
        return None
    
    return None


def main():
    print_header("Alertes DISK actives avec valeurs réelles")
    print(f"URL: {GRAFANA_URL}")
    print(f"Seuil: {DISK_USAGE_THRESHOLD}%\n")
    
    # Récupérer la datasource
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    default_ds = find_default_datasource(datasources)
    
    if not default_ds:
        print("✗ Datasource non trouvée.")
        sys.exit(1)
    
    # Récupérer les alertes actives
    instances = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/alertmanager/grafana/api/v2/alerts",
        api_token=API_TOKEN
    )
    
    if not instances:
        print("ℹ️  Aucune alerte active.")
        return
    
    # Filtrer les alertes disk
    disk_alerts = [
        alert for alert in instances 
        if alert.get('labels', {}).get('type') == 'disk_monitoring'
    ]
    
    if not disk_alerts:
        print("ℹ️  Aucune alerte disk active.")
        return
    
    print(f"🔔 {len(disk_alerts)} alerte(s) disk active(s):\n")
    print("=" * 100)
    print(f"{'Host':<45} {'Usage actuel':<15} {'Seuil':<10} {'État':<15} {'Depuis'}")
    print("-" * 100)
    
    for alert in disk_alerts:
        labels = alert.get('labels', {})
        host = labels.get('host', 'N/A')
        threshold = labels.get('threshold', DISK_USAGE_THRESHOLD)
        state = alert.get('status', {}).get('state', 'N/A')
        starts_at = alert.get('startsAt', 'N/A')
        
        # Récupérer la valeur actuelle du disque
        current_usage = get_current_disk_usage_for_host(
            GRAFANA_URL, 
            API_TOKEN, 
            default_ds.get('uid'), 
            host
        )
        
        if current_usage is not None:
            usage_str = f"{current_usage:.1f}%"
            alert_marker = "🔴" if current_usage > float(threshold) else "⚠️"
        else:
            usage_str = "N/A"
            alert_marker = "❓"
        
        print(f"{alert_marker} {host:<43} {usage_str:<15} {threshold}%      {state:<15} {starts_at[:19] if len(starts_at) > 19 else starts_at}")
    
    print("=" * 100)
    print(f"\n💡 Pour voir les détails dans Grafana: {GRAFANA_URL}/alerting/list")


if __name__ == "__main__":
    main()
