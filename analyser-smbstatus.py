#!/usr/bin/env python3
"""
Script pour analyser la sortie de smbstatus et afficher les utilisateurs 
avec le nombre de fichiers qu'ils ont ouverts.
N'affiche que les utilisateurs ayant au moins un fichier ouvert.
"""

import subprocess
import re
from collections import defaultdict
import config
import os


def executer_smbstatus():
    """Exécute la commande smbstatus et retourne la sortie."""
    try:
        result = subprocess.run(['smbstatus'], capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de l'exécution de smbstatus: {e}")
        return None
    except FileNotFoundError:
        print("La commande smbstatus n'est pas disponible. Assurez-vous que Samba est installé.")
        return None


def analyser_smbstatus(contenu):
    """
    Analyse le contenu de smbstatus et retourne un dictionnaire
    {username: {'nb_fichiers': int, 'ip': str}}
    """
    lignes = contenu.split('\n')
    
    # Dictionnaires pour stocker les informations
    pid_vers_username = {}  # {pid: username}
    username_vers_info = {}  # {username: {'nb_fichiers': int, 'ip': str}}
    
    # Extraction des utilisateurs du premier tableau
    dans_section_utilisateurs = False
    for ligne in lignes:
        # Détection de l'en-tête du premier tableau
        if 'PID' in ligne and 'Username' in ligne and 'Group' in ligne:
            dans_section_utilisateurs = True
            continue
        
        # Détection de la fin du premier tableau
        if dans_section_utilisateurs and (ligne.startswith('Service') or ligne == ''):
            if 'Service' in ligne:
                dans_section_utilisateurs = False
            continue
        
        # Extraction des données utilisateur
        if dans_section_utilisateurs and ligne.strip():
            # Ignorer les lignes de séparation
            if ligne.startswith('---'):
                continue
            
            # Parser la ligne pour extraire PID, Username et IP
            parties = ligne.split()
            if len(parties) >= 4:
                try:
                    pid = int(parties[0])
                    username = parties[1]
                    # Extraire l'IP de toute la ligne (format: ipv4:10.1.40.162:58050)
                    ip_match = re.search(r'ipv4:(\d+\.\d+\.\d+\.\d+)', ligne)
                    ip = ip_match.group(1) if ip_match else ''
                    
                    pid_vers_username[pid] = username
                    
                    # Initialiser l'entrée utilisateur si elle n'existe pas encore
                    if username not in username_vers_info:
                        username_vers_info[username] = {'nb_fichiers': 0, 'ip': ip}
                except ValueError:
                    # Ignorer les lignes qui ne commencent pas par un PID valide
                    continue
    
    # Extraction des fichiers verrouillés
    dans_section_fichiers = False
    for ligne in lignes:
        # Détection de la section "Locked files"
        if ligne.startswith('Locked files:'):
            dans_section_fichiers = True
            continue
        
        if dans_section_fichiers and ligne.strip():
            # Ignorer les lignes d'en-tête et de séparation
            if 'Pid' in ligne or ligne.startswith('---'):
                continue
            
            # Parser la ligne de fichier
            parties = ligne.split()
            if len(parties) >= 1:
                try:
                    pid = int(parties[0])
                    
                    # Vérifier si le fichier n'est pas juste "." (répertoire)
                    # Le nom du fichier est généralement dans les dernières colonnes
                    # On cherche la colonne "Name" qui est généralement avant "Time"
                    # Format: Pid User(ID) DenyMode Access R/W Oplock SharePath Name Time
                    
                    # Trouver l'index de "Time" pour savoir où se trouve le nom
                    if len(parties) >= 9:
                        # Le nom du fichier peut contenir des espaces, donc on prend tout
                        # entre SharePath et Time (les 5 derniers éléments sont généralement la date/heure)
                        nom_fichier_parties = parties[7:-5]  # Entre SharePath et Time
                        nom_fichier = ' '.join(nom_fichier_parties) if nom_fichier_parties else ''
                        
                        # Ignorer les entrées qui sont juste le répertoire "."
                        if nom_fichier and nom_fichier.strip() != '.':
                            if pid in pid_vers_username:
                                username = pid_vers_username[pid]
                                if username in username_vers_info:
                                    username_vers_info[username]['nb_fichiers'] += 1
                except (ValueError, IndexError):
                    continue
    
    return username_vers_info


def afficher_resultats(username_vers_info):
    """Affiche les résultats formatés."""
    # Filtrer pour n'afficher que les utilisateurs avec des fichiers ouverts
    utilisateurs_avec_fichiers = {
        username: info for username, info in username_vers_info.items()
        if info['nb_fichiers'] > 0
    }
    
    if not utilisateurs_avec_fichiers:
        print("Aucun utilisateur avec des fichiers ouverts.")
        return
    
    # Trier par nom d'utilisateur
    utilisateurs_tries = sorted(utilisateurs_avec_fichiers.items(), key=lambda x: x[0])
    
    # Afficher l'en-tête
    print(f"{'Utilisateur':<20} {'IP':<16} {'Nb fichiers':>12}")
    print('-' * 50)
    
    # Afficher les utilisateurs avec leurs IPs et nombres de fichiers
    for username, info in utilisateurs_tries:
        print(f"{username:<20} {info['ip']:<16} {info['nb_fichiers']:>12}")
    
    print('-' * 50)
    total_fichiers = sum(info['nb_fichiers'] for info in utilisateurs_avec_fichiers.values())
    print(f"{'Total':<37} {total_fichiers:>12}")


def main():
    """Fonction principale."""
    # Déterminer la source des données
    if hasattr(config, 'SMBSTATUS_FILE_PATH') and config.SMBSTATUS_FILE_PATH:
        # Lire depuis le fichier spécifié dans config.py
        file_path = config.SMBSTATUS_FILE_PATH
        if not os.path.exists(file_path):
            print(f"Erreur: Le fichier '{file_path}' n'existe pas.")
            return
        
        with open(file_path, 'r') as f:
            contenu = f.read()
    else:
        # Exécuter smbstatus directement
        contenu = executer_smbstatus()
    
    if contenu:
        username_vers_info = analyser_smbstatus(contenu)
        afficher_resultats(username_vers_info)


if __name__ == '__main__':
    main()
