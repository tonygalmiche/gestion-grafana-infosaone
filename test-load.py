#!/usr/bin/env python3
"""
Test de la requête load1
"""

from config import GRAFANA_URL, API_TOKEN
from grafana_utils import get_datasources, find_default_datasource, query_timescale
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import json

def test_load():
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    default_ds = find_default_datasource(datasources)
    
    if not default_ds:
        print("Erreur: pas de datasource par défaut")
        return
    
    print(f"Datasource: {default_ds.get('name')} (uid: {default_ds.get('uid')})")
    
    # Calculer le timestamp pour il y a 15 minutes en timezone Paris
    now_paris = datetime.now(ZoneInfo('Europe/Paris'))
    fifteen_min_ago_paris = now_paris - timedelta(minutes=15)
    
    print(f"\nMaintenant (Paris): {now_paris}")
    print(f"15 minutes ago (Paris): {fifteen_min_ago_paris}")
    
    # Formater pour PostgreSQL
    time_str = fifteen_min_ago_paris.strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"Time string: {time_str}")
    
    # Test avec différentes approches
    tests = [
        f"SELECT time, host, load1 FROM system WHERE load1 IS NOT NULL AND time >= '{time_str}' ORDER BY time DESC LIMIT 10",
        f"SELECT time, host, load1 FROM system WHERE load1 IS NOT NULL AND time >= TIMESTAMP '{time_str}' ORDER BY time DESC LIMIT 10",
        "SELECT time, host, load1 FROM system WHERE load1 IS NOT NULL AND time >= (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Paris' - INTERVAL '15 minutes') ORDER BY time DESC LIMIT 10",
    ]
    
    for i, sql in enumerate(tests, 1):
        print(f"\n\nTest {i}:\n{sql}\n")
        results = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql)
        
        if results and 'results' in results:
            for result in results.get('results', {}).values():
                if 'frames' in result:
                    for frame in result['frames']:
                        data_values = frame.get('data', {}).get('values', [])
                        print(f"Nombre de colonnes: {len(data_values)}")
                        if len(data_values) >= 3:
                            times = data_values[0]
                            hosts = data_values[1]
                            loads = data_values[2]
                            print(f"Nombre de lignes: {len(times)}")
                            
                            # Collecter par host
                            host_loads = {}
                            for j in range(len(hosts)):
                                host = hosts[j]
                                load = loads[j]
                                if host not in host_loads:
                                    host_loads[host] = []
                                host_loads[host].append(load)
                            
                            # Afficher les moyennes
                            print("\nMoyennes par host:")
                            for host, lds in sorted(host_loads.items()):
                                avg = sum(lds) / len(lds)
                                print(f"  {host}: {avg:.2f} (sur {len(lds)} valeurs)")
                            
                            print("\n✓ Cette syntaxe fonctionne!")
                            break
                        else:
                            print("✗ Pas de résultats")

if __name__ == '__main__':
    test_load()
