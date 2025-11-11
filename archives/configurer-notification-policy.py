#!/usr/bin/env python3
"""
Script pour configurer la notification policy Grafana
afin de NE PAS envoyer de notifications pour les alertes avec notifications=disabled
"""

from config import GRAFANA_URL, API_TOKEN
from grafana_utils import make_grafana_request
import json

def get_notification_policy():
    """Récupère la notification policy actuelle"""
    result = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/v1/provisioning/policies",
        method="GET",
        api_token=API_TOKEN
    )
    return result

def update_notification_policy():
    """
    Met à jour la notification policy pour bloquer les notifications
    des alertes avec notifications=disabled
    """
    
    print("Récupération de la notification policy actuelle...")
    current_policy = get_notification_policy()
    
    if not current_policy:
        print("❌ Impossible de récupérer la policy actuelle")
        return False
    
    print("✓ Policy actuelle récupérée\n")
    print("Configuration actuelle:")
    print(json.dumps(current_policy, indent=2))
    
    # Ajouter une route qui bloque les notifications=disabled
    new_route = {
        "receiver": "grafana-default-email",  # Contact point par défaut
        "object_matchers": [
            ["notifications", "=", "disabled"]
        ],
        "continue": False,  # Arrête le matching ici
        "mute_time_intervals": [],
        "routes": []
    }
    
    # Créer une policy avec une route qui n'envoie RIEN pour notifications=disabled
    updated_policy = current_policy.copy()
    
    # Option 1: Ajouter une route silencieuse au début
    if "routes" not in updated_policy:
        updated_policy["routes"] = []
    
    # Insérer la nouvelle route en PREMIER (priorité)
    updated_policy["routes"].insert(0, {
        "receiver": "",  # Pas de receiver = pas de notification
        "object_matchers": [
            ["notifications", "=", "disabled"]
        ],
        "continue": False
    })
    
    print("\n\n⚠️  ATTENTION: Cette opération va modifier la notification policy.")
    print("Voulez-vous continuer? (oui/non): ", end="")
    response = input().strip().lower()
    
    if response != "oui":
        print("Opération annulée.")
        return False
    
    print("\nMise à jour de la notification policy...")
    result = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/v1/provisioning/policies",
        method="PUT",
        data=updated_policy,
        api_token=API_TOKEN
    )
    
    if result:
        print("✅ Notification policy mise à jour avec succès")
        print("   Les alertes avec notifications=disabled ne déclencheront PLUS d'emails")
        return True
    else:
        print("❌ Erreur lors de la mise à jour de la policy")
        return False

if __name__ == "__main__":
    print("Configuration de la notification policy pour bloquer les emails...\n")
    update_notification_policy()
