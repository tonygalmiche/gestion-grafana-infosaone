#!/usr/bin/env python3
"""
Script autonome de surveillance disque - SANS Grafana Alerting
Interroge directement TimescaleDB et envoie des emails
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from config import (
    GRAFANA_URL, API_TOKEN, DISK_USAGE_THRESHOLD, HOST_NO_DATA_MINUTES,
    SMTP_SERVER, SMTP_PORT, SMTP_USE_TLS, SMTP_USERNAME, SMTP_PASSWORD,
    FROM_EMAIL, TO_EMAIL
)
from grafana_utils import (
    get_datasources, find_default_datasource, query_timescale,
    send_email_report, get_last_ok_report_date, save_ok_report_date,
    clear_ok_report_date, should_send_ok_report
)
import json

LAST_OK_REPORT_FILE = "/tmp/surveiller-disk-last-ok-report.txt"

def get_disk_usage():
    """Récupère l'utilisation disque de tous les hosts"""
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    default_ds = find_default_datasource(datasources)
    
    if not default_ds:
        return []
    
    # Requête pour obtenir la dernière valeur de chaque host
    sql = """
    SELECT DISTINCT ON (host) 
        host, 
        used_percent, 
        time
    FROM disk
    ORDER BY host, time DESC
    """
    
    results = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql)
    
    if not results or 'results' not in results:
        return []
    
    hosts_data = []
    for result in results.get('results', {}).values():
        if 'frames' in result:
            for frame in result['frames']:
                schema = frame.get('schema', {}).get('fields', [])
                data_values = frame.get('data', {}).get('values', [])
                
                if len(data_values) >= 3:
                    hosts = data_values[0]
                    percentages = data_values[1]
                    timestamps = data_values[2]
                    
                    for i in range(len(hosts)):
                        # Convertir le timestamp en datetime
                        ts = timestamps[i] / 1000  # millisecondes vers secondes
                        last_contact = datetime.fromtimestamp(ts, tz=timezone.utc)
                        
                        hosts_data.append({
                            'host': hosts[i],
                            'usage': int(round(percentages[i])),
                            'last_contact': last_contact
                        })
    
    return hosts_data

def send_summary_email(all_hosts, alerts, threshold, no_data_minutes):
    """Envoie un email récapitulatif avec toutes les alertes"""
    
    nb_total = len(all_hosts)
    nb_alerts = len(alerts)
    nb_ok = nb_total - nb_alerts
    
    # Calculer le nombre de hosts sans données récentes
    now = datetime.now(timezone.utc)
    hosts_no_data = [h for h in all_hosts if (now - h['last_contact']).total_seconds() > no_data_minutes * 60]
    nb_no_data = len(hosts_no_data)
    
    # Icônes pour le sujet
    disk_icon = "🟠" if nb_alerts > 0 else "✅"
    contact_icon = "🔴" if nb_no_data > 0 else "✅"
    
    # Date et heure pour le sujet
    now_paris = datetime.now(ZoneInfo('Europe/Paris'))
    date_time_str = now_paris.strftime('%d/%m %H:%M')
    
    subject = f"[Grafana] {date_time_str} {disk_icon} {nb_alerts}/{nb_total} alerte espace disque (>{threshold}%) et {contact_icon} {nb_no_data}/{nb_total} alerte contact (>{no_data_minutes}mn)"
    
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
        td:nth-child(3), td:nth-child(4) {{ text-align: right; }}
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
        Serveurs en alerte (>{threshold}%) : <strong style="color: red;">{nb_alerts}</strong><br>
        Serveurs sans données récentes (>{no_data_minutes}min) : <strong style="color: orange;">{nb_no_data}</strong><br>
        Serveurs OK (≤{threshold}%) : <strong style="color: green;">{nb_ok}</strong>
    </div>
    
    <table>
        <tr>
            <th>Statut</th>
            <th>Serveur</th>
            <th style="text-align: right;">Utilisation</th>
            <th style="text-align: right;">Dernier contact</th>
        </tr>
"""
    
    # Trier : du plus gros au plus petit usage
    sorted_hosts = sorted(all_hosts, key=lambda h: h['usage'], reverse=True)
    
    for host_data in sorted_hosts:
        is_alert = host_data['usage'] > threshold
        
        # Vérifier si pas de données récentes
        time_diff = (now - host_data['last_contact']).total_seconds()
        is_no_data = time_diff > no_data_minutes * 60
        
        # Formater le dernier contact en heure de Paris
        last_contact_paris = host_data['last_contact'].astimezone(ZoneInfo('Europe/Paris'))
        last_contact_str = last_contact_paris.strftime('%d/%m %H:%M')
        
        # Icône et style
        if is_no_data:
            status_icon = "🔴"
            row_style = 'style="background-color: #fff3cd;"'
            contact_style = 'style="color: orange; font-weight: bold;"'
        elif is_alert:
            status_icon = "🟠"
            row_style = 'style="background-color: #ffe6e6;"'
            contact_style = ''
        else:
            status_icon = "✅"
            row_style = ""
            contact_style = ''
        
        usage_style = 'style="color: red; font-weight: bold;"' if is_alert else 'style="color: green;"'
        
        html_body += f"""
        <tr {row_style}>
            <td class="{'no-data' if is_no_data else ('alert' if is_alert else 'ok')}">{status_icon}</td>
            <td>{host_data['host']}</td>
            <td {usage_style}>{host_data['usage']}%</td>
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
- Serveurs en alerte (>{threshold}%) : {nb_alerts}
- Serveurs OK (≤{threshold}%) : {nb_ok}

{'='*50}

Liste des serveurs :

"""
    
    for host_data in sorted_hosts:
        is_alert = host_data['usage'] > threshold
        status = "🔴 ALERTE" if is_alert else "✅ OK    "
        text_body += f"{status}  {host_data['host']:<40} {host_data['usage']:>6.1f}%\n"
    
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
    
    # Trouver les alertes (disques > seuil)
    alerts = [h for h in hosts_data if h['usage'] > DISK_USAGE_THRESHOLD]
    
    # Calculer les anomalies
    now = datetime.now(timezone.utc)
    hosts_no_data = [h for h in hosts_data if (now - h['last_contact']).total_seconds() > HOST_NO_DATA_MINUTES * 60]
    
    nb_total = len(hosts_data)
    nb_alerts = len(alerts)
    nb_no_data = len(hosts_no_data)
    
    # Déterminer s'il y a des anomalies
    has_anomaly = nb_alerts > 0 or nb_no_data > 0
    
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
    
    # Préparer le sujet
    disk_icon = "🟠" if nb_alerts > 0 else "✅"
    contact_icon = "🔴" if nb_no_data > 0 else "✅"
    
    # Date et heure pour le sujet
    now_paris = datetime.now(ZoneInfo('Europe/Paris'))
    date_time_str = now_paris.strftime('%d/%m %H:%M')
    
    subject = f"[Grafana] {date_time_str} {disk_icon} {nb_alerts}/{nb_total} alerte espace disque (>{DISK_USAGE_THRESHOLD}%) et {contact_icon} {nb_no_data}/{nb_total} alerte contact (>{HOST_NO_DATA_MINUTES}mn)"
    
    if send_email:
        print(f"{subject} - {reason}")
        send_summary_email(hosts_data, alerts, DISK_USAGE_THRESHOLD, HOST_NO_DATA_MINUTES)
        
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
