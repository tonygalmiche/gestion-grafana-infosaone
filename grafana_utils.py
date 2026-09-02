#!/usr/bin/env python3
"""
Fonctions utilitaires communes pour les scripts Grafana
"""

import requests
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Union
import sys

# Session HTTP partagée : réutilise la même connexion TCP/TLS (keep-alive)
# pour tous les appels vers Grafana, au lieu d'en ouvrir une nouvelle à
# chaque requête. Evite de multiplier les connexions "à froid" qui peuvent
# rester bloquées de longues secondes (ex: hairpin NAT quand le script
# tourne sur le serveur Grafana lui-même et rappelle son propre nom public).
_session = requests.Session()


def make_grafana_request(
    grafana_url: str,
    endpoint: str,
    api_token: str = None,
    username: str = None,
    password: str = None,
    method: str = "GET",
    data: Dict = None
) -> Union[Dict, List]:
    """
    Effectue une requête HTTP vers l'API Grafana
    
    Args:
        grafana_url: URL du serveur Grafana
        endpoint: Point de terminaison de l'API (ex: /api/search)
        api_token: Token d'API (recommandé)
        username: Nom d'utilisateur (alternative)
        password: Mot de passe (alternative)
        method: Méthode HTTP (GET, POST, etc.)
        data: Données à envoyer (pour POST/PUT)
    
    Returns:
        Réponse JSON de l'API
    """
    # Préparation des headers
    headers = {"Content-Type": "application/json"}
    
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    
    # Préparation de l'authentification
    auth = None
    if username and password:
        auth = (username, password)
    
    # Construction de l'URL complète
    url = f"{grafana_url}{endpoint}"
    
    try:
        if method.upper() == "GET":
            response = _session.get(url, headers=headers, auth=auth)
        elif method.upper() == "POST":
            response = _session.post(url, headers=headers, auth=auth, json=data)
        elif method.upper() == "PUT":
            response = _session.put(url, headers=headers, auth=auth, json=data)
        elif method.upper() == "DELETE":
            response = _session.delete(url, headers=headers, auth=auth)
        else:
            raise ValueError(f"Méthode HTTP non supportée: {method}")
        
        response.raise_for_status()
        
        # Pour DELETE, une réponse vide est un succès
        if method.upper() == "DELETE":
            # Retourner True pour indiquer le succès, même si pas de contenu
            return True if response.status_code in [200, 204] else None
        
        # Pour les autres méthodes, essayer de parser le JSON
        if response.text:
            return response.json()
        else:
            # Réponse vide mais succès (ex: 204 No Content)
            return True
    
    except requests.exceptions.HTTPError as e:
        print(f"Erreur HTTP {response.status_code}: {e}")
        if response.text:
            print(f"Détails: {response.text}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Erreur de requête: {e}")
        return None
    except json.JSONDecodeError as e:
        # Pour les DELETE, c'est normal de ne pas avoir de JSON
        if method.upper() == "DELETE" and response.status_code in [200, 204]:
            return True
        print(f"Erreur de décodage JSON: {e}")
        return None


def save_to_json_file(data: Union[Dict, List], filename: str) -> bool:
    """
    Sauvegarde des données dans un fichier JSON
    
    Args:
        data: Données à sauvegarder (dict ou list)
        filename: Nom du fichier de sortie
    
    Returns:
        True si succès, False sinon
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✓ Données sauvegardées dans: {filename}")
        return True
    except IOError as e:
        print(f"✗ Erreur lors de la sauvegarde: {e}")
        return False


def load_from_json_file(filename: str) -> Union[Dict, List, None]:
    """
    Charge des données depuis un fichier JSON
    
    Args:
        filename: Nom du fichier à charger
    
    Returns:
        Données chargées ou None en cas d'erreur
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"✗ Fichier non trouvé: {filename}")
        return None
    except json.JSONDecodeError as e:
        print(f"✗ Erreur de décodage JSON: {e}")
        return None
    except IOError as e:
        print(f"✗ Erreur lors de la lecture: {e}")
        return None


def print_header(title: str, width: int = 80):
    """
    Affiche un en-tête formaté
    
    Args:
        title: Titre à afficher
        width: Largeur de l'en-tête
    """
    print(f"\n{'='*width}")
    print(title)
    print(f"{'='*width}\n")


def print_section(title: str, width: int = 80):
    """
    Affiche un séparateur de section
    
    Args:
        title: Titre de la section
        width: Largeur du séparateur
    """
    print(f"\n{'-'*width}")
    print(title)
    print(f"{'-'*width}\n")


def confirm_action(message: str, default: bool = False) -> bool:
    """
    Demande confirmation à l'utilisateur
    
    Args:
        message: Message à afficher
        default: Valeur par défaut (True/False)
    
    Returns:
        True si l'utilisateur confirme, False sinon
    """
    if default:
        prompt = f"{message} (O/n): "
        positive = ['', 'o', 'oui', 'y', 'yes']
    else:
        prompt = f"{message} (o/N): "
        positive = ['o', 'oui', 'y', 'yes']
    
    response = input(prompt).lower().strip()
    return response in positive


def format_list_as_string(items: List[str], separator: str = ", ") -> str:
    """
    Formate une liste en chaîne de caractères
    
    Args:
        items: Liste d'éléments
        separator: Séparateur entre les éléments
    
    Returns:
        Chaîne formatée
    """
    if not items:
        return "Aucun"
    return separator.join(items)


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Tronque un texte s'il dépasse une longueur maximale
    
    Args:
        text: Texte à tronquer
        max_length: Longueur maximale
        suffix: Suffixe à ajouter si tronqué
    
    Returns:
        Texte tronqué
    """
    if not text or len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def validate_url(url: str) -> bool:
    """
    Valide qu'une URL est correcte
    
    Args:
        url: URL à valider
    
    Returns:
        True si l'URL est valide, False sinon
    """
    if not url:
        return False
    return url.startswith(('http://', 'https://'))


def get_safe_value(data: Dict, key: str, default: str = "N/A") -> str:
    """
    Récupère une valeur d'un dictionnaire de manière sécurisée
    
    Args:
        data: Dictionnaire source
        key: Clé à récupérer
        default: Valeur par défaut si la clé n'existe pas
    
    Returns:
        Valeur trouvée ou valeur par défaut
    """
    return data.get(key, default)


# ============================================================================
# Fonctions spécifiques à l'API Grafana
# ============================================================================

def get_datasources(grafana_url: str, api_token: str) -> List[Dict]:
    """
    Récupère la liste des datasources Grafana
    
    Args:
        grafana_url: URL du serveur Grafana
        api_token: Token d'API
    
    Returns:
        Liste des datasources
    """
    result = make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/datasources",
        api_token=api_token
    )
    return result if result else []


def find_default_datasource(datasources: List[Dict]) -> Union[Dict, None]:
    """
    Trouve la datasource par défaut dans une liste
    
    Args:
        datasources: Liste des datasources
    
    Returns:
        Datasource par défaut ou la première si aucune n'est marquée par défaut
    """
    for ds in datasources:
        if ds.get('isDefault', False):
            return ds
    return datasources[0] if datasources else None


def get_folders(grafana_url: str, api_token: str) -> List[Dict]:
    """
    Récupère la liste des dossiers Grafana
    
    Args:
        grafana_url: URL du serveur Grafana
        api_token: Token d'API
    
    Returns:
        Liste des dossiers
    """
    result = make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/folders",
        api_token=api_token
    )
    return result if result else []


def create_or_get_folder(grafana_url: str, api_token: str, folder_title: str) -> Union[Dict, None]:
    """
    Crée un dossier ou le récupère s'il existe déjà
    
    Args:
        grafana_url: URL du serveur Grafana
        api_token: Token d'API
        folder_title: Titre du dossier
    
    Returns:
        Dossier créé ou existant
    """
    # Vérifier si le dossier existe
    folders = get_folders(grafana_url, api_token)
    for folder in folders:
        if folder.get('title') == folder_title:
            print(f"✓ Dossier '{folder_title}' existe déjà (UID: {folder.get('uid')})")
            return folder
    
    # Créer le dossier
    payload = {"title": folder_title}
    
    result = make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/folders",
        api_token=api_token,
        method="POST",
        data=payload
    )
    
    if result:
        print(f"✓ Dossier '{folder_title}' créé (UID: {result.get('uid')})")
    
    return result


def check_alert_exists(grafana_url: str, api_token: str, alert_title: str) -> Dict:
    """
    Vérifie si une alerte existe déjà (API Provisioning)
    
    Args:
        grafana_url: URL du serveur Grafana
        api_token: Token d'API
        alert_title: Titre de l'alerte à chercher
    
    Returns:
        Dict avec 'exists', 'uid', 'folder_uid'
    """
    prov_result = make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/v1/provisioning/alert-rules",
        api_token=api_token
    )
    
    if prov_result:
        for rule in prov_result:
            if rule.get('title') == alert_title:
                return {
                    'exists': True,
                    'uid': rule.get('uid'),
                    'folder_uid': rule.get('folderUID')
                }
    
    return {'exists': False}


def delete_alert_rule(grafana_url: str, api_token: str, alert_info: Dict) -> bool:
    """
    Supprime une règle d'alerte (API Provisioning)
    
    Args:
        grafana_url: URL du serveur Grafana
        api_token: Token d'API
        alert_info: Informations de l'alerte (doit contenir 'uid')
    
    Returns:
        True si succès, False sinon
    """
    result = make_grafana_request(
        grafana_url=grafana_url,
        endpoint=f"/api/v1/provisioning/alert-rules/{alert_info['uid']}",
        api_token=api_token,
        method="DELETE"
    )
    return result is not None


def delete_alerts_by_label(grafana_url: str, api_token: str, label_key: str, label_value: str) -> int:
    """
    Supprime toutes les alertes ayant un label spécifique
    
    Args:
        grafana_url: URL du serveur Grafana
        api_token: Token d'API
        label_key: Clé du label (ex: 'type')
        label_value: Valeur du label (ex: 'host_monitoring', 'disk_monitoring')
    
    Returns:
        Nombre d'alertes supprimées
    """
    # Récupérer toutes les alertes
    result = make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/v1/provisioning/alert-rules",
        api_token=api_token
    )
    
    if not result:
        return 0
    
    # Filtrer les alertes par label
    alerts_to_delete = [
        alert for alert in result 
        if alert.get('labels', {}).get(label_key) == label_value
    ]
    
    if not alerts_to_delete:
        print(f"  ℹ️  Aucune alerte avec le label {label_key}={label_value} à supprimer.")
        return 0
    
    print(f"  ℹ️  {len(alerts_to_delete)} alerte(s) avec le label {label_key}={label_value} trouvée(s), suppression...")
    
    deleted = 0
    for alert in alerts_to_delete:
        alert_info = {
            'uid': alert.get('uid'),
            'folder_uid': alert.get('folderUID')
        }
        if delete_alert_rule(grafana_url, api_token, alert_info):
            deleted += 1
    
    print(f"  ✓ {deleted} alerte(s) supprimée(s)")
    return deleted


def query_timescale(grafana_url: str, api_token: str, datasource_uid: str, sql_query: str) -> Union[Dict, None]:
    """
    Exécute une requête SQL sur TimescaleDB via l'API Grafana
    
    Args:
        grafana_url: URL du serveur Grafana
        api_token: Token d'API
        datasource_uid: UID de la datasource TimescaleDB
        sql_query: Requête SQL à exécuter
    
    Returns:
        Résultats de la requête
    """
    payload = {
        "queries": [
            {
                "datasource": {
                    "type": "postgres",
                    "uid": datasource_uid
                },
                "rawSql": sql_query,
                "format": "table",
                "refId": "A"
            }
        ]
    }
    
    result = make_grafana_request(
        grafana_url=grafana_url,
        endpoint="/api/ds/query",
        api_token=api_token,
        method="POST",
        data=payload
    )
    
    return result if result else None


def parse_query_results_to_list(results: Dict, column_index: int = 0) -> List[str]:
    """
    Parse les résultats d'une requête Grafana pour extraire une colonne
    
    Args:
        results: Résultats bruts de l'API
        column_index: Index de la colonne à extraire (0 par défaut)
    
    Returns:
        Liste des valeurs de la colonne
    """
    values = []
    
    if not results or 'results' not in results:
        return values
    
    # Parcourir les résultats
    for key, result in results['results'].items():
        if 'frames' in result:
            for frame in result['frames']:
                if 'data' in frame and 'values' in frame['data']:
                    data_values = frame['data']['values']
                    if data_values and len(data_values) > column_index:
                        values = data_values[column_index]
    
    return values


# ============================================================================
# Fonctions pour les rapports autonomes (email et gestion des rapports OK)
# ============================================================================

def send_email_report(from_email: str, to_email: str, subject: str, html_body: str, text_body: str,
                     smtp_server: str, smtp_port: int, smtp_use_tls: bool, 
                     smtp_username: str, smtp_password: str) -> bool:
    """
    Envoie un email HTML avec fallback texte
    
    Args:
        from_email: Email expéditeur
        to_email: Email destinataire
        subject: Sujet de l'email
        html_body: Corps HTML
        text_body: Corps texte (fallback)
        smtp_server: Serveur SMTP
        smtp_port: Port SMTP
        smtp_use_tls: Utiliser TLS
        smtp_username: Nom d'utilisateur SMTP
        smtp_password: Mot de passe SMTP
    
    Returns:
        True si succès, False sinon
    """
    msg = MIMEMultipart('alternative')
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg['Date'] = datetime.now(ZoneInfo('Europe/Paris')).strftime('%a, %d %b %Y %H:%M:%S %z')
    
    # Ajouter les deux versions (texte et HTML)
    part1 = MIMEText(text_body, 'plain', 'utf-8')
    part2 = MIMEText(html_body, 'html', 'utf-8')
    msg.attach(part1)
    msg.attach(part2)
    
    try:
        # Port 465 = SSL, Port 587 = TLS
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
            if smtp_use_tls:
                server.starttls()
        
        if smtp_username and smtp_password:
            server.login(smtp_username, smtp_password)
        
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Erreur envoi email : {e}")
        return False


def get_last_ok_report_date(report_file: str) -> Union[str, None]:
    """
    Récupère la date du dernier rapport OK envoyé
    
    Args:
        report_file: Chemin du fichier de suivi
    
    Returns:
        Date (YYYY-MM-DD) ou None
    """
    if os.path.exists(report_file):
        try:
            with open(report_file, 'r') as f:
                return f.read().strip()
        except:
            return None
    return None


def save_ok_report_date(report_file: str) -> None:
    """
    Enregistre la date du jour comme dernier rapport OK
    
    Args:
        report_file: Chemin du fichier de suivi
    """
    today = datetime.now(ZoneInfo('Europe/Paris')).strftime('%Y-%m-%d')
    try:
        with open(report_file, 'w') as f:
            f.write(today)
    except Exception as e:
        print(f"Erreur sauvegarde date rapport OK : {e}")


def clear_ok_report_date(report_file: str) -> None:
    """
    Efface la date du dernier rapport OK (lors d'une anomalie)
    
    Args:
        report_file: Chemin du fichier de suivi
    """
    try:
        if os.path.exists(report_file):
            os.remove(report_file)
    except Exception as e:
        print(f"Erreur suppression date rapport OK : {e}")


def should_send_ok_report(report_file: str) -> bool:
    """
    Détermine si un rapport OK doit être envoyé (au moins 1 fois par jour)
    
    Args:
        report_file: Chemin du fichier de suivi
    
    Returns:
        True si le rapport OK doit être envoyé
    """
    last_date = get_last_ok_report_date(report_file)
    today = datetime.now(ZoneInfo('Europe/Paris')).strftime('%Y-%m-%d')
    return last_date != today
