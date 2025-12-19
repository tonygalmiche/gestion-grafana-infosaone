#!/usr/bin/env python3
"""
Script pour bloquer automatiquement les IPs Facebook/Meta abusives
basé sur l'analyse des logs Nginx
"""

import subprocess
import sys
from pathlib import Path

# Liste des plages IP Facebook/Meta connues
META_IP_RANGES = [
    "57.141.0.0/24",     # Plage principale détectée
    "69.63.176.0/20",
    "66.220.144.0/20",
    "69.171.224.0/19",
    "173.252.64.0/18",
    "204.15.20.0/22",
]

def bloquer_plages_meta():
    """Bloque les plages IP de Meta avec iptables"""
    print("🔥 Blocage des plages IP Facebook/Meta avec iptables...")
    
    for ip_range in META_IP_RANGES:
        try:
            # Vérifier si la règle existe déjà
            check_cmd = f"sudo iptables -C INPUT -s {ip_range} -j DROP 2>/dev/null"
            result = subprocess.run(check_cmd, shell=True, capture_output=True)
            
            if result.returncode != 0:
                # La règle n'existe pas, on l'ajoute
                block_cmd = f"sudo iptables -I INPUT -s {ip_range} -j DROP"
                subprocess.run(block_cmd, shell=True, check=True)
                print(f"✅ Bloqué: {ip_range}")
            else:
                print(f"⏭️  Déjà bloqué: {ip_range}")
                
        except subprocess.CalledProcessError as e:
            print(f"❌ Erreur lors du blocage de {ip_range}: {e}")
    
    # Sauvegarder les règles iptables
    print("\n💾 Sauvegarde des règles iptables...")
    try:
        subprocess.run("sudo netfilter-persistent save", shell=True, check=True)
        print("✅ Règles sauvegardées")
    except subprocess.CalledProcessError:
        print("⚠️  Installer netfilter-persistent: sudo apt install iptables-persistent")

def afficher_regles():
    """Affiche les règles iptables actuelles"""
    print("\n📋 Règles iptables pour Meta:")
    try:
        result = subprocess.run(
            "sudo iptables -L INPUT -n -v | grep -E '(57\\.141|69\\.63|66\\.220|69\\.171|173\\.252|204\\.15)'",
            shell=True,
            capture_output=True,
            text=True
        )
        if result.stdout:
            print(result.stdout)
        else:
            print("Aucune règle Meta trouvée")
    except subprocess.CalledProcessError as e:
        print(f"Erreur: {e}")

def debloquer_plages_meta():
    """Débloque les plages IP de Meta"""
    print("🔓 Déblocage des plages IP Facebook/Meta...")
    
    for ip_range in META_IP_RANGES:
        try:
            unblock_cmd = f"sudo iptables -D INPUT -s {ip_range} -j DROP 2>/dev/null"
            subprocess.run(unblock_cmd, shell=True)
            print(f"✅ Débloqué: {ip_range}")
        except subprocess.CalledProcessError as e:
            print(f"⏭️  Pas bloqué: {ip_range}")
    
    print("\n💾 Sauvegarde des règles iptables...")
    try:
        subprocess.run("sudo netfilter-persistent save", shell=True, check=True)
        print("✅ Règles sauvegardées")
    except subprocess.CalledProcessError:
        print("⚠️  netfilter-persistent non disponible")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--debloquer":
        debloquer_plages_meta()
    elif len(sys.argv) > 1 and sys.argv[1] == "--status":
        afficher_regles()
    else:
        print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║          BLOCAGE DES PLAGES IP FACEBOOK/META                              ║
╚═══════════════════════════════════════════════════════════════════════════╝

Ce script va bloquer au niveau firewall (iptables) toutes les plages IP
connues de Facebook/Meta pour éviter leur crawling abusif.

⚠️  ATTENTION: Cela bloquera COMPLÈTEMENT l'accès depuis Facebook
   (y compris les partages de liens sur Facebook)

Options:
  ./bloquer-meta-iptables.py            - Bloquer Meta
  ./bloquer-meta-iptables.py --status   - Voir les règles actuelles
  ./bloquer-meta-iptables.py --debloquer - Débloquer Meta

""")
        reponse = input("Voulez-vous continuer? [o/N] ").strip().lower()
        if reponse == 'o':
            bloquer_plages_meta()
            afficher_regles()
            print("\n✅ Terminé! Facebook/Meta est maintenant bloqué au niveau firewall.")
        else:
            print("❌ Annulé")
