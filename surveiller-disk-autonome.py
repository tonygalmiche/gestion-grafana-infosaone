#!/usr/bin/env python3
"""
Script autonome de surveillance disque - SANS Grafana Alerting
Interroge directement TimescaleDB et envoie des emails

Fonctionnement (destiné à être lancé périodiquement, ex. via cron) :
1. get_all_known_hosts() interroge la table system (métrique load1, envoyée en
   continu par tout agent Telegraf actif) SANS limite de temps, afin d'obtenir
   la liste complète des hosts déjà connus et leur dernier contact. C'est cette
   liste qui sert de référence : un host qui cesse totalement d'envoyer des
   données (y compris ses métriques disque) continue donc à apparaître dans le
   rapport, avec une alerte "no data", au lieu de disparaître silencieusement.
2. get_disk_usage() interroge ensuite la table disk pour récupérer l'utilisation
   max (used_percent, sur les 10 dernières minutes) des hosts qui en ont envoyé
   récemment, et la rattache à la liste ci-dessus (usage = None/"N/A" sinon) ;
   get_load_averages() récupère en plus la moyenne du load1 sur les 30 dernières
   minutes par host.
3. main() exclut les hosts listés dans DISK_EXCLUDED_HOSTS, puis compare pour
   chaque host actif son utilisation disque (si connue) et son load1 aux seuils
   (globaux ou spécifiques par host via DISK_USAGE_THRESHOLD_PER_HOST /
   LOAD1_THRESHOLD_PER_HOST), et détecte les hosts sans données récentes
   (> HOST_NO_DATA_MINUTES, calculé sur le dernier contact issu de system).
4. Un email HTML récapitulatif (send_summary_email) est envoyé uniquement si :
   - une anomalie est détectée (disque ou load1 hors seuil, pas de données)
     -> envoi systématique, et la date du dernier rapport "OK" est effacée
     pour forcer un rapport de confirmation une fois le problème résolu ;
   - ou aucune anomalie mais aucun rapport "tout va bien" n'a encore été envoyé
     aujourd'hui (should_send_ok_report / LAST_OK_REPORT_FILE) -> un seul rapport
     OK quotidien est envoyé, sa date étant sauvegardée pour éviter les doublons.
5. Sinon, aucun email n'est envoyé (juste un message affiché en console).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from config import (
    GRAFANA_URL, API_TOKEN, DISK_USAGE_THRESHOLD, DISK_USAGE_THRESHOLD_PER_HOST, HOST_NO_DATA_MINUTES,
    DISK_EXCLUDED_HOSTS, LOAD1_THRESHOLD, LOAD1_THRESHOLD_PER_HOST, SMTP_SERVER, SMTP_PORT, SMTP_USE_TLS, SMTP_USERNAME, SMTP_PASSWORD,
    FROM_EMAIL, TO_EMAIL
)
from grafana_utils import (
    get_datasources, find_default_datasource, query_timescale,
    send_email_report, get_last_ok_report_date, save_ok_report_date,
    clear_ok_report_date, should_send_ok_report
)
import json

LAST_OK_REPORT_FILE = "/tmp/surveiller-disk-last-ok-report.txt"

def get_host_disk_threshold(hostname):
    """Retourne le seuil d'utilisation disque pour un host donné"""
    return DISK_USAGE_THRESHOLD_PER_HOST.get(hostname, DISK_USAGE_THRESHOLD)

def get_host_load_threshold(hostname):
    """Retourne le seuil load1 pour un host donné"""
    return LOAD1_THRESHOLD_PER_HOST.get(hostname, LOAD1_THRESHOLD)

def get_all_known_hosts():
    """Récupère tous les hosts connus (via la métrique load1 de la table system,
    envoyée en continu par tout agent Telegraf actif) et leur dernier contact,
    SANS limite de temps. Sert de liste de référence pour ne pas perdre de vue
    un host qui a totalement cessé d'envoyer des données."""
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    default_ds = find_default_datasource(datasources)

    if not default_ds:
        return {}

    sql = """
    SELECT DISTINCT ON (host)
        host,
        time
    FROM system
    ORDER BY host, time DESC
    """

    results = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql)

    hosts_dict = {}
    if results and 'results' in results:
        for result in results.get('results', {}).values():
            if 'frames' in result:
                for frame in result['frames']:
                    data_values = frame.get('data', {}).get('values', [])

                    if len(data_values) >= 2:
                        hosts = data_values[0]
                        timestamps = data_values[1]

                        for i in range(len(hosts)):
                            ts = timestamps[i] / 1000  # millisecondes vers secondes
                            hosts_dict[hosts[i]] = datetime.fromtimestamp(ts, tz=timezone.utc)

    return hosts_dict

def get_disk_usage():
    """Récupère l'utilisation disque de tous les hosts connus. Un host connu
    (cf. get_all_known_hosts) mais sans donnée disque récente apparaît quand
    même, avec usage = None (affiché en N/A)."""
    known_hosts = get_all_known_hosts()

    if not known_hosts:
        return []

    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    default_ds = find_default_datasource(datasources)

    if not default_ds:
        return []

    # Requête pour obtenir le used_percent maximum par host sur les hosts actifs récemment
    sql_usage = """
    SELECT DISTINCT ON (host)
        host,
        path,
        used_percent
    FROM disk
    WHERE   path not like '/snap%'
        and path not like '/sys%'
        and path not like '/mnt/PK-%'
        and path not like '/boot%'
        and path not like '/run%'
        and used_percent is not null
        and time >= (CURRENT_TIMESTAMP AT TIME ZONE 'UTC' - INTERVAL '10 minutes')
    ORDER BY host, used_percent DESC
    """

    # Récupérer les données d'utilisation
    results_usage = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql_usage)

    # Extraire les données d'utilisation par host
    usage_dict = {}
    if results_usage and 'results' in results_usage:
        for result in results_usage.get('results', {}).values():
            if 'frames' in result:
                for frame in result['frames']:
                    data_values = frame.get('data', {}).get('values', [])

                    if len(data_values) >= 3:
                        hosts = data_values[0]
                        paths = data_values[1]
                        percentages = data_values[2]

                        for i in range(len(hosts)):
                            usage_dict[hosts[i]] = int(round(percentages[i]))

    # Combiner la liste de référence des hosts avec l'utilisation disque connue
    hosts_dict = {}
    for hostname, last_contact in known_hosts.items():
        hosts_dict[hostname] = {
            'host': hostname,
            'usage': usage_dict.get(hostname, None),
            'last_contact': last_contact
        }

    return list(hosts_dict.values())

def get_load_averages():
    """Récupère la moyenne du load1 sur les 15 dernières minutes pour chaque host"""
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    default_ds = find_default_datasource(datasources)
    
    if not default_ds:
        return {}
    
    # Requête avec timezone Paris pour correspondre à la configuration du serveur
    sql = """
    SELECT
      host,
      round(avg(load1)::numeric, 1) AS load1
    FROM system
    WHERE
      time >= (CURRENT_TIMESTAMP AT TIME ZONE 'UTC' - INTERVAL '30 minutes')
      AND load1 IS NOT NULL
    GROUP BY host
    ORDER BY host
    """
    
    results = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql)
    
    if not results or 'results' not in results:
        return {}
    
    # Extraire les données
    load_data = {}
    for result in results.get('results', {}).values():
        if 'frames' in result:
            for frame in result['frames']:
                data_values = frame.get('data', {}).get('values', [])
                
                if len(data_values) >= 2:
                    hosts = data_values[0]
                    loads = data_values[1]
                    
                    for i in range(len(hosts)):
                        load_data[hosts[i]] = round(loads[i], 2)
    
    return load_data

def build_subject(all_hosts, threshold, no_data_minutes):
    """Construit le sujet de l'email basé sur les alertes actives"""
    nb_total = len(all_hosts)
    
    # Calculer le nombre de hosts sans données récentes
    now = datetime.now(timezone.utc)
    hosts_no_data = [h for h in all_hosts if (now - h['last_contact']).total_seconds() > no_data_minutes * 60]
    nb_no_data = len(hosts_no_data)
    
    # Calculer le nombre de hosts avec alerte disque et load1
    nb_disk_alerts = len([h for h in all_hosts if h['usage'] is not None and h['usage'] > get_host_disk_threshold(h['host'])])
    nb_load_alerts = len([h for h in all_hosts if h.get('load1') is not None and h['load1'] > get_host_load_threshold(h['host'])])

    # Date et heure pour le sujet
    now_paris = datetime.now(ZoneInfo('Europe/Paris'))
    date_time_str = now_paris.strftime('%d/%m %H:%M')
    
    # Construire le sujet avec uniquement les alertes actives
    subject_parts = [f"[Grafana] {date_time_str}"]
    
    if nb_disk_alerts > 0:
        subject_parts.append(f"🟠 {nb_disk_alerts}/{nb_total} disque")
    if nb_load_alerts > 0:
        subject_parts.append(f"🟠 {nb_load_alerts}/{nb_total} load1")
    if nb_no_data > 0:
        subject_parts.append(f"🔴 {nb_no_data}/{nb_total} contact (>{no_data_minutes}mn)")
    
    # Si aucune alerte, indiquer juste le nombre de serveurs surveillés
    if nb_disk_alerts == 0 and nb_load_alerts == 0 and nb_no_data == 0:
        subject_parts.append(f"✅ {nb_total} serveurs OK")
    
    return " ".join(subject_parts)

def send_summary_email(all_hosts, alerts, threshold, no_data_minutes, excluded_hosts):
    """Envoie un email récapitulatif avec toutes les alertes"""
    
    nb_total = len(all_hosts)
    nb_alerts = len(alerts)
    nb_excluded = len(excluded_hosts)
    
    # Calculer le nombre de hosts sans données récentes
    now = datetime.now(timezone.utc)
    hosts_no_data = [h for h in all_hosts if (now - h['last_contact']).total_seconds() > no_data_minutes * 60]
    nb_no_data = len(hosts_no_data)
    
    # Calculer le nombre de hosts avec alerte disque et load1
    nb_disk_alerts = len([h for h in all_hosts if h['usage'] is not None and h['usage'] > get_host_disk_threshold(h['host'])])
    nb_load_alerts = len([h for h in all_hosts if h.get('load1') is not None and h['load1'] > get_host_load_threshold(h['host'])])

    # Construire le sujet
    subject = build_subject(all_hosts, threshold, no_data_minutes)
    
    # Construction du tableau HTML
    html_body = f"""
<html>
<head>
    <style>
        body {{ font-family: sans-serif; font-size: 14px; }}
        h2 {{ color: #333; font-size: 16px; margin-bottom: 10px; }}
        table {{ border-collapse: collapse; width: 700px; margin-top: 10px; font-size: 12px; }}
        th {{ background-color: #4CAF50; color: white; padding: 3px; text-align: left; font-size: 14px; }}
        td {{ padding: 3px; border-bottom: 1px solid #ddd; }}
        td:nth-child(3), td:nth-child(4), td:nth-child(5) {{ text-align: right; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .ok {{ color: green; font-size: 14px; }}
        .alert {{ color: red; font-size: 14px; }}
        .no-data {{ color: orange; font-size: 14px; }}
        .summary {{ background-color: #f0f0f0; padding: 6px; border-radius: 5px; margin-bottom: 10px; font-size: 12px; }}
    </style>
</head>
<body>
    <h2>📊 Rapport de surveillance disque</h2>
    
    <div class="summary">
        <strong>Résumé :</strong><br>
        Total de serveurs surveillés : <strong>{nb_total}</strong><br>
        Serveurs en alerte espace disque : <strong style="color: red;">{nb_disk_alerts}</strong><br>
        Serveurs en alerte load1 : <strong style="color: red;">{nb_load_alerts}</strong><br>
        Serveurs sans données récentes (>{no_data_minutes}min) : <strong style="color: orange;">{nb_no_data}</strong><br>
        Serveurs exclus du rapport : <strong style="color: gray;">{nb_excluded}</strong>"""
    
    # Ajouter la liste des hosts exclus si elle n'est pas vide
    if excluded_hosts:
        excluded_names = ', '.join(sorted([h['host'] for h in excluded_hosts]))
        html_body += f"""<br>
        <span style="color: gray; font-size: 11px;">({excluded_names})</span>"""
    
    html_body += """
    </div>
    
    <table>
        <tr>
            <th>Statut</th>
            <th>Serveur</th>
            <th style="text-align: right;">Utilisation</th>
            <th style="text-align: right;">Load (15min)</th>
            <th style="text-align: right;">Dernier contact</th>
        </tr>
"""
    
    # Trier par nom de serveur
    sorted_hosts = sorted(all_hosts, key=lambda h: h['host'])
    
    for host_data in sorted_hosts:
        host_disk_threshold = get_host_disk_threshold(host_data['host'])
        usage = host_data['usage']
        is_alert = usage is not None and usage > host_disk_threshold

        # Vérifier si pas de données récentes
        time_diff = (now - host_data['last_contact']).total_seconds()
        is_no_data = time_diff > no_data_minutes * 60

        # Formater le dernier contact en heure de Paris
        last_contact_paris = host_data['last_contact'].astimezone(ZoneInfo('Europe/Paris'))
        last_contact_str = last_contact_paris.strftime('%d/%m %H:%M')

        # Formater l'utilisation disque avec seuil si alerte (N/A si aucune donnée récente)
        if usage is None:
            usage_str = "N/A"
        elif is_alert:
            usage_str = f"{usage}>{host_disk_threshold}"
        else:
            usage_str = f"{usage}%"

        # Récupérer le load1 pour ce host
        load1 = host_data.get('load1', None)
        if load1 is not None:
            host_load_threshold = get_host_load_threshold(host_data['host'])
            is_load_alert = load1 > host_load_threshold
            if is_load_alert:
                load1_str = f"{load1}>{host_load_threshold}"
            else:
                load1_str = f"{load1}"
        else:
            load1_str = "-"
            is_load_alert = False
        
        # Déterminer si anomalie (alerte ou pas de données)
        has_anomaly = is_no_data or is_alert or is_load_alert
        
        # Icône
        status_icon = "🔴" if has_anomaly else "✅"
        
        # Styles des cellules - fond rouge uniquement pour la cellule en alerte
        usage_style = 'style="background-color: red; color: white; font-weight: bold;"' if is_alert else ('style="color: gray;"' if usage is None else 'style="color: green;"')
        load_style = 'style="background-color: red; color: white; font-weight: bold;"' if is_load_alert else ('style="color: gray;"' if load1 is None else '')
        contact_style = 'style="background-color: red; color: white; font-weight: bold;"' if is_no_data else ''
        
        html_body += f"""
        <tr>
            <td class="{'alert' if has_anomaly else 'ok'}">{status_icon}</td>
            <td>{host_data['host']}</td>
            <td {usage_style}>{usage_str}</td>
            <td {load_style}>{load1_str}</td>
            <td {contact_style}>{last_contact_str}</td>
        </tr>
"""
    
    html_body += """
    </table>
    
    <p style="margin-top: 20px; color: #666; font-size: 12px;">
        Ce rapport est généré automatiquement par le système de surveillance disque.
    </p>
</body>
</html>
"""
    
    # Version texte pour les clients email sans HTML
    text_body = f"""
Rapport de surveillance disque
{'='*50}

Résumé :
- Total de serveurs surveillés : {nb_total}
- Serveurs en alerte espace disque : {nb_disk_alerts}
- Serveurs en alerte load1 : {nb_load_alerts}
- Serveurs sans données récentes (>{no_data_minutes}min) : {nb_no_data}

{'='*50}

Liste des serveurs :

"""
    
    for host_data in sorted_hosts:
        host_disk_threshold = get_host_disk_threshold(host_data['host'])
        usage = host_data['usage']
        is_alert = usage is not None and usage > host_disk_threshold
        status = "🔴 ALERTE" if is_alert else "✅ OK    "
        usage_str = f"{usage:>5.1f}%" if usage is not None else "  N/A "
        text_body += f"{status}  {host_data['host']:<40} {usage_str}\n"
    
    text_body += f"\n{'='*50}\n"
    
    # Utiliser la fonction commune pour envoyer l'email
    return send_email_report(
        from_email=FROM_EMAIL,
        to_email=TO_EMAIL,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        smtp_server=SMTP_SERVER,
        smtp_port=SMTP_PORT,
        smtp_use_tls=SMTP_USE_TLS,
        smtp_username=SMTP_USERNAME,
        smtp_password=SMTP_PASSWORD
    )

def main():
    """Fonction principale"""
    hosts_data = get_disk_usage()
    
    if not hosts_data:
        print("Erreur : Aucune donnée trouvée")
        return
    
    # Récupérer les moyennes de load1
    load_averages = get_load_averages()
    
    # Ajouter les données de load1 aux hosts_data
    for host in hosts_data:
        host['load1'] = load_averages.get(host['host'], None)
    
    # Séparer les hosts exclus des autres
    excluded_hosts = [h for h in hosts_data if h['host'] in DISK_EXCLUDED_HOSTS]
    active_hosts = [h for h in hosts_data if h['host'] not in DISK_EXCLUDED_HOSTS]
    
    # Trouver les alertes (disques > seuil OU load1 > seuil) parmi les hosts actifs uniquement
    alerts = [h for h in active_hosts if (h['usage'] is not None and h['usage'] > get_host_disk_threshold(h['host'])) or (h.get('load1') is not None and h['load1'] > get_host_load_threshold(h['host']))]

    # Calculer les anomalies
    now = datetime.now(timezone.utc)
    hosts_no_data = [h for h in active_hosts if (now - h['last_contact']).total_seconds() > HOST_NO_DATA_MINUTES * 60]

    nb_total = len(active_hosts)
    nb_disk_alerts = len([h for h in active_hosts if h['usage'] is not None and h['usage'] > get_host_disk_threshold(h['host'])])
    nb_load_alerts = len([h for h in active_hosts if h.get('load1') is not None and h['load1'] > get_host_load_threshold(h['host'])])
    nb_no_data = len(hosts_no_data)
    
    # Déterminer s'il y a des anomalies
    has_anomaly = nb_disk_alerts > 0 or nb_load_alerts > 0 or nb_no_data > 0
    
    # Décider si on envoie l'email
    send_email = False
    if has_anomaly:
        # Toujours envoyer si anomalie détectée
        send_email = True
        reason = "Anomalie détectée"
    elif should_send_ok_report(LAST_OK_REPORT_FILE):
        # Envoyer le rapport OK une fois par jour
        send_email = True
        reason = "Rapport quotidien OK"
    else:
        # Pas d'anomalie et rapport OK déjà envoyé aujourd'hui
        reason = "Pas d'anomalie, rapport OK déjà envoyé aujourd'hui"
    
    # Construire le sujet
    subject = build_subject(active_hosts, DISK_USAGE_THRESHOLD, HOST_NO_DATA_MINUTES)
    
    if send_email:
        print(f"{subject} - {reason}")
        send_summary_email(active_hosts, alerts, DISK_USAGE_THRESHOLD, HOST_NO_DATA_MINUTES, excluded_hosts)
        
        # Si tout est OK, sauvegarder la date du rapport
        if not has_anomaly:
            save_ok_report_date(LAST_OK_REPORT_FILE)
        else:
            # Si anomalie, effacer la date pour forcer l'envoi d'un rapport OK après résolution
            clear_ok_report_date(LAST_OK_REPORT_FILE)
    else:
        print(f"{subject} - {reason} - Email non envoyé")

if __name__ == "__main__":
    main()
