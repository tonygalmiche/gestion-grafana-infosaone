#!/usr/bin/env python3
"""
Script pour lister et gérer les contact points Grafana
"""

import sys
from config import GRAFANA_URL, API_TOKEN
from grafana_utils import make_grafana_request, print_header


def list_contact_points():
    """
    Liste tous les contact points configurés
    """
    result = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/v1/provisioning/contact-points",
        api_token=API_TOKEN
    )
    
    if not result:
        print("✗ Aucun contact point trouvé ou erreur.")
        return []
    
    return result


def list_notification_policies():
    """
    Liste les politiques de notification
    """
    result = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/v1/provisioning/policies",
        api_token=API_TOKEN
    )
    
    return result


def main():
    print_header("Contact Points et Notification Policies Grafana")
    print(f"URL: {GRAFANA_URL}\n")
    
    # 1. Lister les contact points
    print("1. Contact Points configurés:")
    print("=" * 80)
    contact_points = list_contact_points()
    
    if contact_points:
        for cp in contact_points:
            name = cp.get('name', 'N/A')
            uid = cp.get('uid', 'N/A')
            receivers = cp.get('settings', {})
            
            print(f"\n📧 Contact Point: {name}")
            print(f"   UID: {uid}")
            print(f"   Type: {receivers.get('type', 'N/A')}")
            
            # Afficher les détails selon le type
            if receivers.get('type') == 'email':
                addresses = receivers.get('addresses', 'N/A')
                print(f"   📬 Adresses email: {addresses}")
            elif receivers.get('type') == 'webhook':
                url = receivers.get('url', 'N/A')
                print(f"   🔗 Webhook URL: {url}")
    else:
        print("ℹ️  Aucun contact point trouvé.")
    
    print("\n" + "=" * 80)
    
    # 2. Lister les notification policies
    print("\n2. Notification Policies:")
    print("=" * 80)
    policies = list_notification_policies()
    
    if policies:
        print(f"Receiver par défaut: {policies.get('receiver', 'N/A')}")
        print(f"Group by: {policies.get('group_by', [])}")
        print(f"Repeat interval: {policies.get('repeat_interval', 'N/A')}")
        
        routes = policies.get('routes', [])
        if routes:
            print(f"\nRoutes configurées: {len(routes)}")
            for idx, route in enumerate(routes, 1):
                print(f"  Route {idx}:")
                print(f"    Receiver: {route.get('receiver', 'N/A')}")
                print(f"    Matchers: {route.get('matchers', [])}")
    else:
        print("ℹ️  Aucune politique trouvée.")
    
    print("\n" + "=" * 80)
    print("\n💡 Pour désactiver les emails Grafana:")
    print("   → Option 1: Grafana UI → Alerting → Contact points → Modifier/Supprimer le contact point email")
    print("   → Option 2: Grafana UI → Alerting → Notification policies → Changer le receiver par défaut")
    print("   → Option 3: Créer un silence pour toutes les alertes disk")
    print(f"\n🌐 Interface Grafana: {GRAFANA_URL}/alerting/notifications")


if __name__ == "__main__":
    main()
