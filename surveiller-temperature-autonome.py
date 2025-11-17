#!/usr/bin/env python3
"""
Script autonome de surveillance température - SANS Grafana Alerting
Interroge directement TimescaleDB et envoie des emails
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from config import (
    GRAFANA_URL, API_TOKEN, TEMPERATURE_THRESHOLDS, SENSOR_NO_DATA_MINUTES,
    BATTERY_LOW_THRESHOLD, SMTP_SERVER, SMTP_PORT, SMTP_USE_TLS, SMTP_USERNAME, 
    SMTP_PASSWORD, FROM_EMAIL, TO_EMAIL_TEMPERATURE
)
from grafana_utils import (
    get_datasources, find_default_datasource, query_timescale,
    send_email_report, get_last_ok_report_date, save_ok_report_date,
    clear_ok_report_date, should_send_ok_report
)
import json


TO_EMAIL = TO_EMAIL_TEMPERATURE


LAST_OK_REPORT_FILE = "/tmp/surveiller-temperature-last-ok-report.txt"

def get_temperature_data():
    """Récupère la température moyenne sur 15 minutes et la batterie pour chaque capteur"""
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    default_ds = find_default_datasource(datasources)
    
    if not default_ds:
        return []
    
    # Requête pour obtenir la moyenne de température sur les 15 dernières minutes par capteur
    sql_temp = """
    SELECT 
        capteur, 
        AVG(value) as temperature,
        MAX(time) as time
    FROM sensor_data
    WHERE measurement = 'MI_TEMPERATURE'
      AND time > NOW() - INTERVAL '60 minutes'
      and capteur in ('1','2','3')
    GROUP BY capteur
    ORDER BY capteur
    """
    
    # Requête pour obtenir le dernier niveau de batterie de chaque capteur
    sql_battery = """
    SELECT DISTINCT ON (capteur)
        capteur,
        value as battery
    FROM sensor_data
    WHERE measurement = 'MI_BATTERY'
      and capteur in ('1','2','3')
    ORDER BY capteur, time DESC
    """
    
    results = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql_temp)
    
    if not results or 'results' not in results:
        return []
    
    # Récupérer les données de température
    temp_data = {}
    for result in results.get('results', {}).values():
        if 'frames' in result:
            for frame in result['frames']:
                data_values = frame.get('data', {}).get('values', [])
                
                if len(data_values) >= 3:
                    capteurs = data_values[0]
                    temperatures = data_values[1]
                    timestamps = data_values[2]
                    
                    for i in range(len(capteurs)):
                        ts = timestamps[i] / 1000
                        last_contact = datetime.fromtimestamp(ts, tz=timezone.utc)
                        capteur_id = str(capteurs[i])
                        
                        temp_data[capteur_id] = {
                            'temperature': round(temperatures[i], 1),
                            'last_contact': last_contact
                        }
    
    # Récupérer les données de batterie
    results_battery = query_timescale(GRAFANA_URL, API_TOKEN, default_ds.get('uid'), sql_battery)
    battery_data = {}
    
    if results_battery and 'results' in results_battery:
        for result in results_battery.get('results', {}).values():
            if 'frames' in result:
                for frame in result['frames']:
                    data_values = frame.get('data', {}).get('values', [])
                    
                    if len(data_values) >= 2:
                        capteurs = data_values[0]
                        batteries = data_values[1]
                        
                        for i in range(len(capteurs)):
                            capteur_id = str(capteurs[i])
                            battery_data[capteur_id] = int(batteries[i])
    
    # Combiner température et batterie
    sensors_data = []
    for capteur_id, temp_info in temp_data.items():
        config = TEMPERATURE_THRESHOLDS.get(capteur_id, {"name": f"Capteur {capteur_id}", "min": 10.0, "max": 30.0})
        sensors_data.append({
            'capteur': capteur_id,
            'name': config['name'],
            'temperature': temp_info['temperature'],
            'min_threshold': config['min'],
            'max_threshold': config['max'],
            'battery': battery_data.get(capteur_id, None),
            'last_contact': temp_info['last_contact']
        })
    
    return sensors_data

def send_summary_email(all_sensors, alerts, no_data_minutes):
    """Envoie un email récapitulatif avec toutes les alertes température"""
    
    nb_total = len(all_sensors)
    nb_alerts = len(alerts)
    
    # Calculer le nombre de capteurs sans données récentes
    now = datetime.now(timezone.utc)
    sensors_no_data = [s for s in all_sensors if (now - s['last_contact']).total_seconds() > no_data_minutes * 60]
    nb_no_data = len(sensors_no_data)
    
    # Calculer le nombre d'alertes batterie faible
    battery_alerts = [s for s in all_sensors if s['battery'] is not None and s['battery'] <= BATTERY_LOW_THRESHOLD]
    nb_battery_alerts = len(battery_alerts)
    
    nb_ok = nb_total - nb_alerts - nb_battery_alerts
    
    # Icônes pour le sujet
    temp_icon = "🟠" if nb_alerts > 0 else "✅"
    contact_icon = "🔴" if nb_no_data > 0 else "✅"
    battery_icon = "🟠" if nb_battery_alerts > 0 else "✅"
    
    # Date et heure pour le sujet
    now_paris = datetime.now(ZoneInfo('Europe/Paris'))
    date_time_str = now_paris.strftime('%d/%m %H:%M')
    
    subject = f"[Grafana] {date_time_str} {temp_icon} {nb_alerts}/{nb_total} alerte température, {battery_icon} {nb_battery_alerts}/{nb_total} batterie faible (<={BATTERY_LOW_THRESHOLD}%) et {contact_icon} {nb_no_data}/{nb_total} alerte contact (>{no_data_minutes}mn)"
    
    # Construction du tableau HTML
    html_body = f"""
<html>
<head>
    <style>
        body {{ font-family: sans-serif; font-size: 14px; }}
        h2 {{ color: #333; font-size: 16px; margin-bottom: 10px; }}
        table {{ border-collapse: collapse; width: 700px; margin-top: 10px; font-size: 12px; }}
        th {{ background-color: #2196F3; color: white; padding: 3px; text-align: left; font-size: 14px; }}
        td {{ padding: 3px; border-bottom: 1px solid #ddd; }}
        td:nth-child(4), td:nth-child(5), td:nth-child(6), td:nth-child(7), td:nth-child(8) {{ text-align: right; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .ok {{ color: green; font-size: 14px; }}
        .alert {{ color: red; font-size: 14px; }}
        .no-data {{ color: orange; font-size: 14px; }}
        .summary {{ background-color: #f0f0f0; padding: 6px; border-radius: 5px; margin-bottom: 10px; font-size: 12px; }}
    </style>
</head>
<body>
    <h2>🌡️ Rapport de surveillance température</h2>
    
    <div class="summary">
        <strong>Résumé :</strong><br>
        Total de capteurs surveillés : <strong>{nb_total}</strong><br>
        Capteurs en alerte (température dépassée) : <strong style="color: red;">{nb_alerts}</strong><br>
        Capteurs en alerte (batterie faible <{BATTERY_LOW_THRESHOLD}%) : <strong style="color: orange;">{nb_battery_alerts}</strong><br>
        Capteurs sans données récentes (>{no_data_minutes}min) : <strong style="color: orange;">{nb_no_data}</strong><br>
        Capteurs OK : <strong style="color: green;">{nb_ok}</strong>
    </div>
    
    <table>
        <tr>
            <th>Statut</th>
            <th>Capteur</th>
            <th>Nom</th>
            <th style="text-align: right;">Température</th>
            <th style="text-align: right;">Min</th>
            <th style="text-align: right;">Max</th>
            <th style="text-align: right;">Batterie</th>
            <th style="text-align: right;">Dernier contact</th>
        </tr>
"""
    
    # Trier : de la plus haute à la plus basse température
    sorted_sensors = sorted(all_sensors, key=lambda s: s['temperature'], reverse=True)
    
    for sensor_data in sorted_sensors:
        is_alert = (sensor_data['temperature'] < sensor_data['min_threshold'] or 
                   sensor_data['temperature'] > sensor_data['max_threshold'])
        
        # Vérifier si batterie faible
        is_battery_low = sensor_data['battery'] is not None and sensor_data['battery'] <= BATTERY_LOW_THRESHOLD
        
        # Vérifier si pas de données récentes
        time_diff = (now - sensor_data['last_contact']).total_seconds()
        is_no_data = time_diff > no_data_minutes * 60
        
        # Formater le dernier contact en heure de Paris
        last_contact_paris = sensor_data['last_contact'].astimezone(ZoneInfo('Europe/Paris'))
        last_contact_str = last_contact_paris.strftime('%d/%m %H:%M')
        
        # Icône et style
        if is_no_data:
            status_icon = "🔴"
            row_style = ''
            contact_style = 'style="background-color: red; color: white; font-weight: bold;"'
        elif is_alert or is_battery_low:
            status_icon = "🟠"
            row_style = ''
            contact_style = ''
        else:
            status_icon = "✅"
            row_style = ""
            contact_style = ''
        
        # Style pour la batterie avec fond rouge si faible
        battery_display = f"{sensor_data['battery']}%" if sensor_data['battery'] is not None else "N/A"
        if is_battery_low:
            battery_style = 'style="background-color: red; color: white; font-weight: bold;"'
        else:
            battery_style = ''
        
        # Style pour la température avec fond rouge si alerte
        if is_alert:
            temp_style = 'style="background-color: red; color: white; font-weight: bold;"'
        else:
            temp_style = ''
        
        html_body += f"""
        <tr {row_style}>
            <td class="{'no-data' if is_no_data else ('alert' if (is_alert or is_battery_low) else 'ok')}">{status_icon}</td>
            <td>Capteur {sensor_data['capteur']}</td>
            <td>{sensor_data['name']}</td>
            <td {temp_style}>{sensor_data['temperature']}°C</td>
            <td>{sensor_data['min_threshold']}°C</td>
            <td>{sensor_data['max_threshold']}°C</td>
            <td {battery_style}>{battery_display}</td>
            <td {contact_style}>{last_contact_str}</td>
        </tr>
"""
    
    html_body += """
    </table>
    
    <p style="margin-top: 20px; color: #666; font-size: 12px;">
        Ce rapport est généré automatiquement par le système de surveillance température.
    </p>
</body>
</html>
"""
    
    # Version texte pour les clients email sans HTML
    text_body = f"""
Rapport de surveillance température
{'='*50}

Résumé :
- Total de capteurs surveillés : {nb_total}
- Capteurs en alerte : {nb_alerts}
- Capteurs sans données récentes : {nb_no_data}
- Capteurs OK : {nb_ok}

{'='*50}

Liste des capteurs :

"""
    
    for sensor_data in sorted_sensors:
        is_alert = (sensor_data['temperature'] < sensor_data['min_threshold'] or 
                   sensor_data['temperature'] > sensor_data['max_threshold'])
        is_battery_low = sensor_data['battery'] is not None and sensor_data['battery'] <= BATTERY_LOW_THRESHOLD
        status = "🟠 ALERTE" if (is_alert or is_battery_low) else "✅ OK    "
        battery_str = f"{sensor_data['battery']}%" if sensor_data['battery'] is not None else "N/A"
        text_body += f"{status}  {sensor_data['name']:<20} {sensor_data['temperature']:>6.1f}°C (plage: {sensor_data['min_threshold']}-{sensor_data['max_threshold']}°C) Batterie: {battery_str}\n"
    
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
    sensors_data = get_temperature_data()
    
    if not sensors_data:
        print("Erreur : Aucune donnée trouvée")
        return
    
    # Trouver les alertes (température hors plage min/max)
    alerts = [s for s in sensors_data if s['temperature'] < s['min_threshold'] or s['temperature'] > s['max_threshold']]
    
    # Calculer les anomalies
    now = datetime.now(timezone.utc)
    sensors_no_data = [s for s in sensors_data if (now - s['last_contact']).total_seconds() > SENSOR_NO_DATA_MINUTES * 60]
    battery_alerts = [s for s in sensors_data if s['battery'] is not None and s['battery'] <= BATTERY_LOW_THRESHOLD]
    
    nb_total = len(sensors_data)
    nb_alerts = len(alerts)
    nb_no_data = len(sensors_no_data)
    nb_battery_alerts = len(battery_alerts)
    
    # Déterminer s'il y a des anomalies
    has_anomaly = nb_alerts > 0 or nb_no_data > 0 or nb_battery_alerts > 0
    
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
    temp_icon = "🟠" if nb_alerts > 0 else "✅"
    contact_icon = "🔴" if nb_no_data > 0 else "✅"
    battery_icon = "🟠" if nb_battery_alerts > 0 else "✅"
    
    # Date et heure pour le sujet
    now_paris = datetime.now(ZoneInfo('Europe/Paris'))
    date_time_str = now_paris.strftime('%d/%m %H:%M')
    
    subject = f"[Grafana] {date_time_str} {temp_icon} {nb_alerts}/{nb_total} alerte température, {battery_icon} {nb_battery_alerts}/{nb_total} batterie faible (<={BATTERY_LOW_THRESHOLD}%) et {contact_icon} {nb_no_data}/{nb_total} alerte contact (>{SENSOR_NO_DATA_MINUTES}mn)"
    
    if send_email:
        print(f"{subject} - {reason}")
        send_summary_email(sensors_data, alerts, SENSOR_NO_DATA_MINUTES)
        
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
