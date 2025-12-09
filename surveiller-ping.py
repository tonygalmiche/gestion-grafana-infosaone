#!/usr/bin/env python3
"""
Script autonome de surveillance ping - SANS Grafana Alerting
Interroge directement TimescaleDB et envoie des emails
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from config import (
    GRAFANA_URL, API_TOKEN, PING_RESPONSE_THRESHOLD, PING_RESPONSE_THRESHOLD_PER_HOST_URL,
    HOST_NO_DATA_MINUTES, PING_EXCLUDED_HOSTS, SMTP_SERVER, SMTP_PORT, SMTP_USE_TLS,
    SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL, TO_EMAIL
)
from grafana_utils import (
    get_datasources, find_default_datasource, query_timescale,
    send_email_report, get_last_ok_report_date, save_ok_report_date,
    clear_ok_report_date, should_send_ok_report
)
import json

LAST_OK_REPORT_FILE = "/tmp/surveiller-ping-last-ok-report.txt"

def get_ping_threshold(hostname, url):
    """Retourne le seuil de temps de réponse ping pour un couple host/url donné"""
    return PING_RESPONSE_THRESHOLD_PER_HOST_URL.get((hostname, url), PING_RESPONSE_THRESHOLD)

def get_ping_data():
    """Récupère les données de ping de tous les hosts"""
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    default_ds = find_default_datasource(datasources)
    
    if not default_ds:
        return []
    
    # Requête pour obtenir le average_response_ms le plus récent par couple (host, url)
    sql_ping = """
    SELECT DISTINCT ON (host, url) 
        host, 
        url,
        average_response_ms,
        time
    FROM ping
    ORDER BY host, url, time DESC
    """
    
    results = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql_ping)
    
    if not results or 'results' not in results:
        return []
    
    # Extraire les données
    hosts_dict = {}
    for result in results.get('results', {}).values():
        if 'frames' in result:
            for frame in result['frames']:
                data_values = frame.get('data', {}).get('values', [])
                
                if len(data_values) >= 4:
                    hosts = data_values[0]
                    urls = data_values[1]
                    pings = data_values[2]
                    timestamps = data_values[3]
                    
                    for i in range(len(hosts)):
                        hostname = hosts[i]
                        url = urls[i]
                        ping = round(pings[i], 2) if pings[i] is not None else None
                        ts = timestamps[i] / 1000  # millisecondes vers secondes
                        last_contact = datetime.fromtimestamp(ts, tz=timezone.utc)
                        
                        key = (hostname, url)
                        hosts_dict[key] = {
                            'host': hostname,
                            'url': url,
                            'ping': ping,
                            'last_contact': last_contact
                        }

    return list(hosts_dict.values())

def build_subject(all_hosts, threshold, no_data_minutes):
    """Construit le sujet de l'email basé sur les alertes actives"""
    nb_total = len(all_hosts)
    
    # Calculer le nombre de hosts sans données récentes
    now = datetime.now(timezone.utc)
    hosts_no_data = [h for h in all_hosts if (now - h['last_contact']).total_seconds() > no_data_minutes * 60]
    nb_no_data = len(hosts_no_data)
    
    # Calculer le nombre de hosts avec alerte ping (ping > seuil OU ping == 0 OU ping == None)
    nb_ping_alerts = len([h for h in all_hosts if h.get('ping') is None or h['ping'] == 0 or h['ping'] > get_ping_threshold(h['host'], h['url'])])
    
    # Date et heure pour le sujet
    now_paris = datetime.now(ZoneInfo('Europe/Paris'))
    date_time_str = now_paris.strftime('%d/%m %H:%M')
    
    # Construire le sujet avec uniquement les alertes actives
    subject_parts = [f"[Grafana Ping] {date_time_str}"]
    
    if nb_ping_alerts > 0:
        subject_parts.append(f"🟠 {nb_ping_alerts}/{nb_total} ping lent")
    if nb_no_data > 0:
        subject_parts.append(f"🔴 {nb_no_data}/{nb_total} contact (>{no_data_minutes}mn)")
    
    # Si aucune alerte, indiquer juste le nombre de serveurs surveillés
    if nb_ping_alerts == 0 and nb_no_data == 0:
        subject_parts.append(f"✅ {nb_total} pings OK")
    
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
    
    # Calculer le nombre de hosts avec alerte ping (ping > seuil OU ping == 0 OU ping == None)
    nb_ping_alerts = len([h for h in all_hosts if h.get('ping') is None or h['ping'] == 0 or h['ping'] > get_ping_threshold(h['host'], h['url'])])
    
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
        td:nth-child(4), td:nth-child(5) {{ text-align: right; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .ok {{ color: green; font-size: 14px; }}
        .alert {{ color: red; font-size: 14px; }}
        .no-data {{ color: orange; font-size: 14px; }}
        .summary {{ background-color: #f0f0f0; padding: 6px; border-radius: 5px; margin-bottom: 10px; font-size: 12px; }}
    </style>
</head>
<body>
    <h2>📊 Rapport de surveillance ping</h2>
    
    <div class="summary">
        <strong>Résumé :</strong><br>
        Total de pings surveillés : <strong>{nb_total}</strong><br>
        Pings en alerte (temps de réponse élevé) : <strong style="color: red;">{nb_ping_alerts}</strong><br>
        Pings sans données récentes (>{no_data_minutes}min) : <strong style="color: orange;">{nb_no_data}</strong><br>
        Pings exclus du rapport : <strong style="color: gray;">{nb_excluded}</strong>"""
    
    # Ajouter la liste des hosts exclus si elle n'est pas vide
    if excluded_hosts:
        excluded_names = ', '.join(sorted([f"{h['host']}->{h['url']}" for h in excluded_hosts]))
        html_body += f"""<br>
        <span style="color: gray; font-size: 11px;">({excluded_names})</span>"""
    
    html_body += """
    </div>
    
    <table>
        <tr>
            <th>Statut</th>
            <th>Serveur</th>
            <th>URL</th>
            <th style="text-align: right;">Ping (ms)</th>
            <th style="text-align: right;">Dernier contact</th>
        </tr>
"""
    
    # Trier par nom de serveur puis URL
    sorted_hosts = sorted(all_hosts, key=lambda h: (h['host'], h['url']))
    
    for host_data in sorted_hosts:
        ping_threshold = get_ping_threshold(host_data['host'], host_data['url'])
        ping_value = host_data.get('ping')
        
        # Alerte si ping > seuil OU ping == 0 OU ping == None
        is_alert = ping_value is None or ping_value == 0 or ping_value > ping_threshold
        
        # Vérifier si pas de données récentes
        time_diff = (now - host_data['last_contact']).total_seconds()
        is_no_data = time_diff > no_data_minutes * 60
        
        # Formater le dernier contact en heure de Paris
        last_contact_paris = host_data['last_contact'].astimezone(ZoneInfo('Europe/Paris'))
        last_contact_str = last_contact_paris.strftime('%d/%m %H:%M')
        
        # Formater le ping avec seuil si alerte (avec 1 décimale)
        if ping_value is None:
            ping_str = "-"
        elif ping_value == 0:
            ping_str = "0.0"
        elif ping_value > ping_threshold:
            ping_str = f"{ping_value:.1f}>{ping_threshold}"
        else:
            ping_str = f"{ping_value:.1f}"
        
        # Déterminer si anomalie (alerte ou pas de données)
        has_anomaly = is_no_data or is_alert
        
        # Icône
        status_icon = "🔴" if has_anomaly else "✅"
        
        # Styles des cellules - fond rouge uniquement pour la cellule en alerte
        ping_style = 'style="background-color: red; color: white; font-weight: bold;"' if is_alert else 'style="color: green;"'
        contact_style = 'style="background-color: red; color: white; font-weight: bold;"' if is_no_data else ''
        
        html_body += f"""
        <tr>
            <td class="{'alert' if has_anomaly else 'ok'}">{status_icon}</td>
            <td>{host_data['host']}</td>
            <td>{host_data['url']}</td>
            <td {ping_style}>{ping_str}</td>
            <td {contact_style}>{last_contact_str}</td>
        </tr>
"""
    
    html_body += """
    </table>
    
    <p style="margin-top: 20px; color: #666; font-size: 12px;">
        Ce rapport est généré automatiquement par le système de surveillance ping.
    </p>
</body>
</html>
"""
    
    # Version texte pour les clients email sans HTML
    text_body = f"""
Rapport de surveillance ping
{'='*50}

Résumé :
- Total de pings surveillés : {nb_total}
- Pings en alerte (temps de réponse élevé) : {nb_ping_alerts}
- Pings sans données récentes (>{no_data_minutes}min) : {nb_no_data}

{'='*50}

Liste des pings :

"""
    
    for host_data in sorted_hosts:
        ping_threshold = get_ping_threshold(host_data['host'], host_data['url'])
        ping_value = host_data.get('ping')
        is_alert = ping_value is None or ping_value == 0 or ping_value > ping_threshold
        status = "🔴 ALERTE" if is_alert else "✅ OK    "
        
        if ping_value is None:
            ping_val = "-"
        elif ping_value == 0:
            ping_val = "0.0ms"
        else:
            ping_val = f"{ping_value:.1f}ms"
        
        text_body += f"{status}  {host_data['host']:<30} -> {host_data['url']:<15} {ping_val:>10}\n"
    
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
    hosts_data = get_ping_data()
    
    if not hosts_data:
        print("Erreur : Aucune donnée trouvée")
        return
    
    # Séparer les hosts exclus des autres
    excluded_hosts = [h for h in hosts_data if (h['host'], h['url']) in PING_EXCLUDED_HOSTS]
    active_hosts = [h for h in hosts_data if (h['host'], h['url']) not in PING_EXCLUDED_HOSTS]
    
    # Trouver les alertes (ping > seuil OU ping == 0 OU ping == None) parmi les hosts actifs uniquement
    alerts = [h for h in active_hosts if h.get('ping') is None or h['ping'] == 0 or h['ping'] > get_ping_threshold(h['host'], h['url'])]
    
    # Calculer les anomalies
    now = datetime.now(timezone.utc)
    hosts_no_data = [h for h in active_hosts if (now - h['last_contact']).total_seconds() > HOST_NO_DATA_MINUTES * 60]
    
    nb_total = len(active_hosts)
    nb_ping_alerts = len(alerts)
    nb_no_data = len(hosts_no_data)
    
    # Déterminer s'il y a des anomalies
    has_anomaly = nb_ping_alerts > 0 or nb_no_data > 0
    
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
    subject = build_subject(active_hosts, PING_RESPONSE_THRESHOLD, HOST_NO_DATA_MINUTES)
    
    if send_email:
        print(f"{subject} - {reason}")
        send_summary_email(active_hosts, alerts, PING_RESPONSE_THRESHOLD, HOST_NO_DATA_MINUTES, excluded_hosts)
        
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
