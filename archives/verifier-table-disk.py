#!/usr/bin/env python3
"""
Script pour vérifier la structure et les données de la table disk
"""

import sys
from config import GRAFANA_URL, API_TOKEN
from grafana_utils import (
    print_header,
    get_datasources,
    find_default_datasource,
    query_timescale
)


def main():
    print_header("Vérification de la table DISK")
    
    # Récupérer la datasource
    print("1. Récupération de la datasource...")
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    default_ds = find_default_datasource(datasources)
    
    if not default_ds:
        print("✗ Aucune datasource trouvée.")
        sys.exit(1)
    
    print(f"✓ Datasource: {default_ds.get('name')}\n")
    
    # Test 1: Vérifier si la table existe et a des données
    print("2. Test: Nombre total de lignes dans la table disk")
    print("=" * 80)
    sql = "SELECT COUNT(*) as total FROM disk"
    result = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql)
    print(f"Requête: {sql}")
    print(f"Résultat brut: {result}\n")
    
    # Test 2: Vérifier les colonnes de la table
    print("3. Test: Structure de la table (colonnes)")
    print("=" * 80)
    sql = """
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'disk'
ORDER BY ordinal_position
"""
    result = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql)
    print(f"Requête: {sql}")
    print(f"Résultat brut: {result}\n")
    
    # Test 3: Vérifier les données récentes (sans filtre de temps)
    print("4. Test: 5 dernières lignes (sans filtre de temps)")
    print("=" * 80)
    sql = "SELECT host, used_percent, time FROM disk ORDER BY time DESC LIMIT 5"
    result = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql)
    print(f"Requête: {sql}")
    print(f"Résultat brut: {result}\n")
    
    # Test 4: Vérifier les données des dernières 24h
    print("5. Test: Données des dernières 24 heures")
    print("=" * 80)
    sql = """
SELECT 
    host,
    MAX(used_percent) as max_usage,
    COUNT(*) as nb_mesures,
    MAX(time) as derniere_mesure
FROM disk 
WHERE time > NOW() - INTERVAL '24 hours'
GROUP BY host
ORDER BY max_usage DESC
LIMIT 10
"""
    result = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql)
    print(f"Requête: {sql}")
    print(f"Résultat brut: {result}\n")
    
    # Test 5: Vérifier le fuseau horaire
    print("6. Test: Vérification du fuseau horaire")
    print("=" * 80)
    sql = "SELECT NOW() as now_utc, NOW() AT TIME ZONE 'Europe/Paris' as now_paris, CURRENT_TIMESTAMP as current_ts"
    result = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql)
    print(f"Requête: {sql}")
    print(f"Résultat brut: {result}\n")
    
    # Test 6: Vérifier l'âge des dernières données
    print("7. Test: Âge des données les plus récentes")
    print("=" * 80)
    sql = """
SELECT 
    host,
    MAX(time) as derniere_mesure,
    EXTRACT(EPOCH FROM (NOW() - MAX(time))) as secondes_depuis
FROM disk 
GROUP BY host
ORDER BY secondes_depuis
LIMIT 5
"""
    result = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql)
    print(f"Requête: {sql}")
    print(f"Résultat brut: {result}\n")


if __name__ == "__main__":
    main()
