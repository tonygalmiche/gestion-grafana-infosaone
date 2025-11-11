#!/usr/bin/env python3
"""
Script pour créer un silence permanent sur les alertes disk
pour désactiver les notifications email Grafana
"""

from config import GRAFANA_URL, GRAFANA_TOKEN
from grafana_utils import make_grafana_request
from datetime import datetime, timedelta

def create_permanent_silence():
    """Crée un silence de 10 ans sur les alertes disk_monitoring"""
    
    # Silence de 10 ans
    start_time = datetime.utcnow()
    end_time = start_time + timedelta(days=3650)  # 10 ans
    
    silence_data = {
        "matchers": [
            {
                "name": "type",
                "value": "disk_monitoring",
                "isRegex": False,
                "isEqual": True
            }
        ],
        "startsAt": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endsAt": end_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "createdBy": "Script de désactivation",
        "comment": "Notifications désactivées - utilisation d'un script externe pour les alertes"
    }
    
    result = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/alertmanager/grafana/api/v2/silences",
        method="POST",
        data=silence_data,
        api_token=GRAFANA_TOKEN
    )
    
    if result:
        print("✅ Silence créé avec succès pour 10 ans")
        print(f"   Les notifications email Grafana sont désactivées")
        print(f"   Utilisez votre script externe pour les alertes")
        return True
    else:
        print("❌ Erreur lors de la création du silence")
        return False

if __name__ == "__main__":
    print("Désactivation des notifications email Grafana pour les alertes disk...")
    create_permanent_silence()
