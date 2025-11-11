#!/usr/bin/env python3
"""
Script pour créer un silence (mute) pour les alertes disk
Utile pour désactiver temporairement les notifications sans supprimer les alertes
"""

import sys
from datetime import datetime, timedelta
from config import GRAFANA_URL, API_TOKEN
from grafana_utils import make_grafana_request, print_header


def create_silence(label_key: str, label_value: str, duration_hours: int = 720):
    """
    Crée un silence pour les alertes matchant un label
    
    Args:
        label_key: Clé du label (ex: 'type')
        label_value: Valeur du label (ex: 'disk_monitoring')
        duration_hours: Durée du silence en heures (défaut: 720h = 30 jours)
    """
    now = datetime.utcnow()
    end_time = now + timedelta(hours=duration_hours)
    
    silence_data = {
        "matchers": [
            {
                "name": label_key,
                "value": label_value,
                "isRegex": False,
                "isEqual": True
            }
        ],
        "startsAt": now.isoformat() + "Z",
        "endsAt": end_time.isoformat() + "Z",
        "createdBy": "Script Python",
        "comment": f"Silence automatique pour {label_key}={label_value} - Notifications gérées par script externe"
    }
    
    result = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/alertmanager/grafana/api/v2/silences",
        api_token=API_TOKEN,
        method="POST",
        data=silence_data
    )
    
    return result


def list_silences():
    """
    Liste tous les silences actifs
    """
    result = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/alertmanager/grafana/api/v2/silences",
        api_token=API_TOKEN
    )
    
    return result


def delete_silence(silence_id: str):
    """
    Supprime un silence
    """
    # L'endpoint correct pour supprimer est différent
    result = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint=f"/api/alertmanager/grafana/api/v2/silence/{silence_id}",
        api_token=API_TOKEN,
        method="DELETE"
    )
    
    return result


def main():
    print_header("Gestion des Silences (Mutes) Grafana")
    print(f"URL: {GRAFANA_URL}\n")
    
    # Afficher le menu
    print("Que voulez-vous faire ?")
    print("1. Créer un silence pour les alertes DISK (désactiver emails)")
    print("2. Lister les silences actifs")
    print("3. Supprimer un silence")
    print("4. Quitter")
    
    choice = input("\nVotre choix (1-4): ").strip()
    
    if choice == "1":
        print("\n" + "=" * 80)
        duration = input("Durée du silence en heures (défaut: 720 = 30 jours): ").strip()
        duration_hours = int(duration) if duration else 720
        
        print(f"\nCréation d'un silence pour type=disk_monitoring pendant {duration_hours}h...")
        result = create_silence('type', 'disk_monitoring', duration_hours)
        
        if result:
            print("✓ Silence créé avec succès!")
            print(f"  ID: {result.get('silenceID', 'N/A')}")
            print(f"  Les alertes disk resteront actives mais n'enverront plus de notifications.")
        else:
            print("✗ Erreur lors de la création du silence.")
    
    elif choice == "2":
        print("\n" + "=" * 80)
        print("Silences actifs:")
        print("=" * 80)
        silences = list_silences()
        
        if silences:
            for silence in silences:
                status = silence.get('status', {})
                if status.get('state') == 'active':
                    print(f"\n🔕 Silence ID: {silence.get('id', 'N/A')}")
                    print(f"   Matchers: {silence.get('matchers', [])}")
                    print(f"   Commentaire: {silence.get('comment', 'N/A')}")
                    print(f"   Début: {silence.get('startsAt', 'N/A')}")
                    print(f"   Fin: {silence.get('endsAt', 'N/A')}")
                    print(f"   Créé par: {silence.get('createdBy', 'N/A')}")
        else:
            print("ℹ️  Aucun silence actif.")
    
    elif choice == "3":
        silences = list_silences()
        if not silences:
            print("\nℹ️  Aucun silence à supprimer.")
            return
        
        print("\n" + "=" * 80)
        print("Silences disponibles:")
        for idx, silence in enumerate(silences, 1):
            print(f"{idx}. ID: {silence.get('id')} - {silence.get('comment', 'N/A')}")
        
        choice_idx = input("\nNuméro du silence à supprimer (ou 'q' pour annuler): ").strip()
        
        if choice_idx.lower() != 'q':
            try:
                silence = silences[int(choice_idx) - 1]
                silence_id = silence.get('id')
                
                confirm = input(f"\nConfirmer la suppression du silence {silence_id} ? (O/n): ").strip().lower()
                if confirm in ['o', 'y', '']:
                    result = delete_silence(silence_id)
                    if result is not None:
                        print("✓ Silence supprimé avec succès!")
                    else:
                        print("✗ Erreur lors de la suppression.")
            except (ValueError, IndexError):
                print("✗ Choix invalide.")
    
    elif choice == "4":
        print("\nAu revoir!")
        return
    
    else:
        print("\n✗ Choix invalide.")
    
    print("\n" + "=" * 80)
    print(f"\n🌐 Interface Grafana: {GRAFANA_URL}/alerting/silences")


if __name__ == "__main__":
    main()
