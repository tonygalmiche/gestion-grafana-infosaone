#!/usr/bin/env python3
"""
Script pour tester et vérifier les alertes disk
Affiche les valeurs actuelles de used_percent et l'état des alertes
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


def get_current_disk_usage(grafana_url: str, api_token: str, datasource_uid: str):
    """
    Récupère l'utilisation disque actuelle de tous les hosts
    """
    sql_query = """
SELECT 
    host,
    MAX(used_percent) as current_usage,
    MAX(time) as last_update
FROM disk 
WHERE time > NOW() - INTERVAL '10 minutes'
GROUP BY host
ORDER BY current_usage DESC
"""
    
    results = query_timescale(grafana_url, api_token, datasource_uid, sql_query)
    
    if not results:
        return []
    
    hosts_data = []
    for result in results.get('results', {}).values():
        for frame in result.get('frames', []):
            data = frame.get('data', {})
            values = data.get('values', [])
            
            if len(values) >= 3:
                hosts = values[0]  # host
                usages = values[1]  # current_usage
                times = values[2]   # last_update
                
                for i in range(len(hosts)):
                    hosts_data.append({
                        'host': hosts[i],
                        'usage': usages[i] if usages[i] is not None else 0,
                        'last_update': times[i]
                    })
    
    return hosts_data


def get_alert_states(grafana_url: str, api_token: str):
    """
    Récupère l'état des alertes disk
    """
    # Récupérer les règles d'alerte
    rules = make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/v1/provisioning/alert-rules",
        api_token=api_token
    )
    
    if not rules:
        return []
    
    disk_alerts = [
        alert for alert in rules 
        if alert.get('labels', {}).get('type') == 'disk_monitoring'
    ]
    
    # Récupérer l'état actuel des alertes
    alert_states = []
    for alert in disk_alerts:
        alert_states.append({
            'title': alert.get('title'),
            'uid': alert.get('uid'),
            'labels': alert.get('labels', {}),
        })
    
    return alert_states


def get_alert_instances(grafana_url: str, api_token: str):
    """
    Récupère les instances d'alertes actives (alertes en cours de déclenchement)
    """
    instances = make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/alertmanager/grafana/api/v2/alerts",
        api_token=api_token
    )
    
    if not instances:
        return []
    
    # Filtrer les alertes disk
    disk_instances = [
        inst for inst in instances 
        if inst.get('labels', {}).get('type') == 'disk_monitoring'
    ]
    
    return disk_instances


def main():
    """
    Fonction principale
    """
    print_header("Test et vérification des alertes DISK")
    print(f"URL: {GRAFANA_URL}")
    print(f"Seuil configuré: {DISK_USAGE_THRESHOLD}%\n")
    
    # 1. Récupérer la datasource
    print("1. Récupération de la datasource...")
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    
    if not datasources:
        print("✗ Aucune datasource trouvée.")
        sys.exit(1)
    
    default_ds = find_default_datasource(datasources)
    
    if not default_ds:
        print("✗ Aucune datasource par défaut trouvée.")
        sys.exit(1)
    
    print(f"✓ Datasource: {default_ds.get('name')} (UID: {default_ds.get('uid')})\n")
    
    # 2. Récupérer l'utilisation disque actuelle
    print("2. Utilisation disque actuelle:")
    print("=" * 80)
    hosts_data = get_current_disk_usage(GRAFANA_URL, API_TOKEN, default_ds.get('uid'))
    
    if not hosts_data:
        print("✗ Aucune donnée trouvée.")
    else:
        print(f"{'Host':<40} {'Usage %':<15} {'Au-dessus seuil':<20} {'Dernière mise à jour'}")
        print("-" * 80)
        
        for host_data in hosts_data:
            host = host_data['host']
            usage = host_data['usage']
            above_threshold = "🔴 OUI" if usage > DISK_USAGE_THRESHOLD else "✓ Non"
            last_update = host_data['last_update']
            
            print(f"{host:<40} {usage:>6.2f}%        {above_threshold:<20} {last_update}")
    
    print()
    
    # 3. Vérifier les règles d'alerte configurées
    print("3. Règles d'alerte configurées:")
    print("=" * 80)
    alert_states = get_alert_states(GRAFANA_URL, API_TOKEN)
    
    if not alert_states:
        print("✗ Aucune règle d'alerte disk trouvée.")
    else:
        print(f"✓ {len(alert_states)} règle(s) d'alerte disk configurée(s):")
        for alert in alert_states:
            print(f"   - {alert['title']}")
            print(f"     UID: {alert['uid']}")
            print(f"     Host: {alert['labels'].get('host', 'N/A')}")
    
    print()
    
    # 4. Vérifier les alertes actives
    print("4. Alertes actives (en cours de déclenchement):")
    print("=" * 80)
    instances = get_alert_instances(GRAFANA_URL, API_TOKEN)
    
    if not instances:
        print("ℹ️  Aucune alerte disk active en ce moment.")
    else:
        print(f"🔔 {len(instances)} alerte(s) disk active(s):")
        for inst in instances:
            labels = inst.get('labels', {})
            print(f"\n   📌 {labels.get('alertname', 'N/A')}")
            print(f"      Host: {labels.get('host', 'N/A')}")
            print(f"      État: {inst.get('status', {}).get('state', 'N/A')}")
            print(f"      Depuis: {inst.get('startsAt', 'N/A')}")
    
    print()
    
    # 5. Recommandations
    print("=" * 80)
    print("DIAGNOSTIC:")
    print("=" * 80)
    
    hosts_above = [h for h in hosts_data if h['usage'] > DISK_USAGE_THRESHOLD]
    
    if hosts_above and not instances:
        print("⚠️  ATTENTION: Des hosts dépassent le seuil mais aucune alerte n'est active!")
        print(f"\n   Hosts au-dessus du seuil ({DISK_USAGE_THRESHOLD}%):")
        for host in hosts_above:
            print(f"   - {host['host']}: {host['usage']:.2f}%")
        
        print("\n   Raisons possibles:")
        print("   1. Les alertes ont une condition 'for: 5m' - elles se déclenchent après 5 minutes")
        print("   2. Vérifiez que la requête SQL retourne des données")
        print("   3. Vérifiez l'intervalle d'évaluation (interval: 1m)")
        print("   4. Consultez Grafana → Alerting → Alert rules pour voir l'état détaillé")
        
    elif instances:
        print("✓ Des alertes sont actives comme prévu!")
        
    else:
        print("✓ Aucun host ne dépasse le seuil, tout est normal.")
    
    print("\n" + "=" * 80)
    print("\nPour plus de détails:")
    print(f"→ Grafana UI: {GRAFANA_URL}/alerting/list")
    print(f"→ Voir les alertes: {GRAFANA_URL}/alerting/groups")
    print("→ Tester une requête: Grafana → Explore → Sélectionnez la datasource PostgreSQL")


if __name__ == "__main__":
    main()
