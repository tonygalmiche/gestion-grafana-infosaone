#!/usr/bin/env python3
"""
Script autonome de surveillance des sauvegardes - SANS Grafana Alerting
Interroge directement TimescaleDB et envoie des emails
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import sys
from config import (
    GRAFANA_URL, API_TOKEN, BACKUP_MAX_SIZE_MB,
    SMTP_SERVER, SMTP_PORT, SMTP_USE_TLS, SMTP_USERNAME, 
    SMTP_PASSWORD, FROM_EMAIL, TO_EMAIL
)
from grafana_utils import (
    get_datasources, find_default_datasource, query_timescale,
    send_email_report, get_last_ok_report_date, save_ok_report_date,
    clear_ok_report_date, should_send_ok_report
)
import json

LAST_OK_REPORT_FILE = "/tmp/analyser-sauvegardes-last-ok-report.txt"


def get_latest_backups():
    """Récupère les dernières sauvegardes pour chaque host/name"""
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    default_ds = find_default_datasource(datasources)
    
    if not default_ds:
        return []
    
    # Requête pour obtenir la dernière entrée pour chaque combinaison host/name
    sql = """
    SELECT DISTINCT ON (host, name)
        host,
        name,
        file_path,
        file_name,
        modification_time,
        file_size,
        time
    FROM file_info
    ORDER BY host, name, time DESC
    """
    
    results = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql)
    
    if not results or 'results' not in results:
        return []
    
    backups_data = []
    for result in results.get('results', {}).values():
        if 'frames' in result:
            for frame in result['frames']:
                data_values = frame.get('data', {}).get('values', [])
                
                if len(data_values) >= 7:
                    hosts = data_values[0]
                    names = data_values[1]
                    file_paths = data_values[2]
                    file_names = data_values[3]
                    modification_times = data_values[4]
                    file_sizes = data_values[5]
                    timestamps = data_values[6]
                    
                    for i in range(len(hosts)):
                        # Convertir les timestamps en datetime
                        mod_ts = modification_times[i] / 1000 if modification_times[i] else 0
                        ts = timestamps[i] / 1000 if timestamps[i] else 0
                        
                        modification_time = datetime.fromtimestamp(mod_ts, tz=timezone.utc) if mod_ts else None
                        time = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
                        
                        backups_data.append({
                            'host': hosts[i],
                            'name': names[i],
                            'file_path': file_paths[i],
                            'file_name': file_names[i],
                            'modification_time': modification_time,
                            'file_size': file_sizes[i],
                            'time': time
                        })
    
    return backups_data


def send_summary_email(all_backups, alerts):
    """Envoie un email récapitulatif avec toutes les alertes sauvegardes"""
    
    nb_total = len(all_backups)
    nb_alerts = len(alerts)
    nb_ok = nb_total - nb_alerts
    
    # Calculer les types d'alertes
    now = datetime.now(timezone.utc)
    limit_24h = now - timedelta(hours=24)
    
    nb_old = 0
    nb_empty = 0
    nb_too_large = 0
    
    for backup in all_backups:
        modification_time = backup['modification_time']
        file_size = backup['file_size']
        size_mb = file_size / (1024 * 1024) if file_size else 0
        
        is_old = modification_time < limit_24h if modification_time else True
        is_empty = file_size == 0 if file_size is not None else True
        is_too_large = size_mb > BACKUP_MAX_SIZE_MB
        
        if is_old:
            nb_old += 1
        if is_empty:
            nb_empty += 1
        if is_too_large:
            nb_too_large += 1
    
    # Icônes pour le sujet
    old_icon = "🔴" if nb_old > 0 else "✅"
    empty_icon = "🔴" if nb_empty > 0 else "✅"
    large_icon = "🟠" if nb_too_large > 0 else "✅"
    
    # Date et heure pour le sujet
    now_paris = datetime.now(ZoneInfo('Europe/Paris'))
    date_time_str = now_paris.strftime('%d/%m %H:%M')
    
    subject = f"[Grafana] {date_time_str} {old_icon} {nb_old}/{nb_total} alerte anciennes (>24h), {empty_icon} {nb_empty}/{nb_total} vides et {large_icon} {nb_too_large}/{nb_total} trop grosses (>{BACKUP_MAX_SIZE_MB}Mo)"
    
    # Construction du tableau HTML
    html_body = f"""
<html>
<head>
    <style>
        body {{ font-family: sans-serif; font-size: 14px; }}
        h2 {{ color: #333; font-size: 16px; margin-bottom: 10px; }}
        table {{ border-collapse: collapse; width: 900px; margin-top: 10px; font-size: 12px; }}
        th {{ background-color: #2196F3; color: white; padding: 3px; text-align: left; font-size: 14px; }}
        td {{ padding: 3px; border-bottom: 1px solid #ddd; }}
        td:nth-child(4), td:nth-child(5) {{ text-align: right; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .ok {{ color: green; font-size: 14px; }}
        .alert {{ color: red; font-size: 14px; }}
        .summary {{ background-color: #f0f0f0; padding: 6px; border-radius: 5px; margin-bottom: 10px; font-size: 12px; }}
    </style>
</head>
<body>
    <h2>💾 Rapport de surveillance des sauvegardes</h2>
    
    <div class="summary">
        <strong>Résumé :</strong><br>
        Total de sauvegardes surveillées : <strong>{nb_total}</strong><br>
        Sauvegardes trop anciennes (>24h) : <strong style="color: red;">{nb_old}</strong><br>
        Sauvegardes vides (0 octets) : <strong style="color: red;">{nb_empty}</strong><br>
        Sauvegardes trop grosses (>{BACKUP_MAX_SIZE_MB}Mo) : <strong style="color: orange;">{nb_too_large}</strong><br>
        Sauvegardes OK : <strong style="color: green;">{nb_ok}</strong>
    </div>
    
    <table>
        <tr>
            <th>Statut</th>
            <th>Host</th>
            <th>Name</th>
            <th style="text-align: right;">Taille</th>
            <th style="text-align: right;">Âge (heures)</th>
            <th>Dernière modification</th>
        </tr>
"""
    
    # Calculer pour chaque backup
    now = datetime.now(timezone.utc)
    limit_24h = now - timedelta(hours=24)
    
    backup_info = []
    for backup in all_backups:
        modification_time = backup['modification_time']
        
        # Calculer l'âge
        if modification_time:
            age = now - modification_time
            age_hours = age.total_seconds() / 3600
        else:
            age_hours = 0
        
        # Convertir la taille en Mo
        size_mb = backup['file_size'] / (1024 * 1024) if backup['file_size'] else 0
        
        # Vérifier les alertes
        is_old = modification_time < limit_24h if modification_time else True
        is_empty = backup['file_size'] == 0 if backup['file_size'] is not None else True
        is_too_large = size_mb > BACKUP_MAX_SIZE_MB
        has_alert = is_old or is_empty or is_too_large
        
        backup_info.append({
            'host': backup['host'],
            'name': backup['name'],
            'file_path': backup['file_path'],
            'modification_time': modification_time,
            'file_size': backup['file_size'],
            'size_mb': size_mb,
            'age_hours': age_hours,
            'is_old': is_old,
            'is_empty': is_empty,
            'is_too_large': is_too_large,
            'has_alert': has_alert
        })
    
    # Trier : alertes en premier, puis par host et name
    sorted_backups = sorted(backup_info, key=lambda b: (not b['has_alert'], b['host'], b['name']))
    
    for backup_data in sorted_backups:
        # Formater la dernière modification en heure de Paris
        if backup_data['modification_time']:
            modif_paris = backup_data['modification_time'].astimezone(ZoneInfo('Europe/Paris'))
            modif_str = modif_paris.strftime('%d/%m %H:%M')
        else:
            modif_str = "N/A"
        
        # Icône et style
        if backup_data['has_alert']:
            status_icon = "🔴"
            row_class = "alert"
        else:
            status_icon = "✅"
            row_class = "ok"
        
        # Style pour la taille si fichier vide ou trop gros
        if backup_data['is_empty']:
            size_style = 'style="background-color: red; color: white; font-weight: bold;"'
        elif backup_data['is_too_large']:
            size_style = 'style="background-color: red; color: white; font-weight: bold;"'
        else:
            size_style = ''
        
        # Style pour l'âge si > 24h
        if backup_data['is_old']:
            age_style = 'style="background-color: red; color: white; font-weight: bold;"'
        else:
            age_style = ''
        
        html_body += f"""
        <tr>
            <td class="{row_class}">{status_icon}</td>
            <td>{backup_data['host']}</td>
            <td>{backup_data['name']}</td>
            <td {size_style}>{backup_data['size_mb']:.1f} Mo</td>
            <td {age_style}>{backup_data['age_hours']:.1f}h</td>
            <td>{modif_str}</td>
        </tr>
"""
    
    html_body += """
    </table>
    
    <p style="margin-top: 20px; color: #666; font-size: 12px;">
        Ce rapport est généré automatiquement par le système de surveillance des sauvegardes.
    </p>
</body>
</html>
"""
    
    # Version texte pour les clients email sans HTML
    text_body = f"""
Rapport de surveillance des sauvegardes
{'='*50}

Résumé :
- Total de sauvegardes surveillées : {nb_total}
- Sauvegardes en alerte : {nb_alerts}
- Sauvegardes OK : {nb_ok}

{'='*50}

Liste des sauvegardes :

"""
    
    for backup_data in sorted_backups:
        status = "🔴 ALERTE" if backup_data['has_alert'] else "✅ OK    "
        text_body += f"{status}  {backup_data['host']:<30} {backup_data['name']:<15} {backup_data['size_mb']:>8.1f} Mo  Âge: {backup_data['age_hours']:>6.1f}h\n"
    
    text_body += f"\n{'='*50}\n"
    
    # Envoyer l'email
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


def analyze_backups(backups):
    """Analyse les sauvegardes et détecte les problèmes"""
    now = datetime.now(timezone.utc)
    limit_24h = now - timedelta(hours=24)
    
    alerts = []
    
    for backup in backups:
        modification_time = backup['modification_time']
        file_size = backup['file_size']
        size_mb = file_size / (1024 * 1024) if file_size else 0
        
        # Vérifier les alertes
        is_old = modification_time < limit_24h if modification_time else True
        is_empty = file_size == 0 if file_size is not None else True
        is_too_large = size_mb > BACKUP_MAX_SIZE_MB
        
        if is_old or is_empty or is_too_large:
            alerts.append(backup)
    
    return alerts


def main():
    """Fonction principale"""
    backups = get_latest_backups()
    
    if not backups:
        print("Erreur : Aucune donnée trouvée")
        return
    
    # Analyser les sauvegardes
    alerts = analyze_backups(backups)
    
    nb_total = len(backups)
    nb_alerts = len(alerts)
    
    # Calculer les types d'alertes
    now = datetime.now(timezone.utc)
    limit_24h = now - timedelta(hours=24)
    
    nb_old = 0
    nb_empty = 0
    nb_too_large = 0
    
    for backup in backups:
        modification_time = backup['modification_time']
        file_size = backup['file_size']
        size_mb = file_size / (1024 * 1024) if file_size else 0
        
        is_old = modification_time < limit_24h if modification_time else True
        is_empty = file_size == 0 if file_size is not None else True
        is_too_large = size_mb > BACKUP_MAX_SIZE_MB
        
        if is_old:
            nb_old += 1
        if is_empty:
            nb_empty += 1
        if is_too_large:
            nb_too_large += 1
    
    # Déterminer s'il y a des anomalies
    has_anomaly = nb_alerts > 0
    
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
    old_icon = "🔴" if nb_old > 0 else "✅"
    empty_icon = "🔴" if nb_empty > 0 else "✅"
    large_icon = "🟠" if nb_too_large > 0 else "✅"
    
    now_paris = datetime.now(ZoneInfo('Europe/Paris'))
    date_time_str = now_paris.strftime('%d/%m %H:%M')
    subject = f"[Grafana] {date_time_str} {old_icon} {nb_old}/{nb_total} alerte anciennes (>24h), {empty_icon} {nb_empty}/{nb_total} vides et {large_icon} {nb_too_large}/{nb_total} trop grosses (>{BACKUP_MAX_SIZE_MB}Mo)"
    
    if send_email:
        print(f"{subject} - {reason}")
        send_summary_email(backups, alerts)
        
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
