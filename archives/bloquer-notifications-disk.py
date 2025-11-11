#!/usr/bin/env python3
"""
Script pour créer un silence permanent sur les alertes disk avec notifications=disabled
Cela empêche Grafana d'envoyer des emails
"""

from config import GRAFANA_URL, API_TOKEN
from grafana_utils import make_grafana_request
from datetime import datetime, timedelta

def create_permanent_silence():
    """Crée un silence de 10 ans sur les alertes disk_monitoring avec notifications=disabled"""
    
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
            },
            {
                "name": "notifications",
                "value": "disabled",
                "isRegex": False,
                "isEqual": True
            }
        ],
        "startsAt": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endsAt": end_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "createdBy": "Script auto",
        "comment": "Notifications désactivées - utilisation d'un script externe pour les alertes disk"
    }
    
    result = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/alertmanager/grafana/api/v2/silences",
        method="POST",
        data=silence_data,
        api_token=API_TOKEN
    )
    
    if result:
        print("✅ Silence créé avec succès pour 10 ans")
        print("   Les alertes avec notifications=disabled ne déclencheront PLUS d'emails")
        print("   Les alertes restent visibles dans Grafana mais sans notification")
        return True
    else:
        print("❌ Erreur lors de la création du silence")
        return False

if __name__ == "__main__":
    print("Création d'un silence permanent pour bloquer les notifications email...")
    print("(Les alertes disk avec notifications=disabled)\n")
    create_permanent_silence()
