#!/usr/bin/env python3
"""
Script pour envoyer un rapport par email des alertes disk actives avec les % réels
À exécuter en cron toutes les heures par exemple
"""

import sys
from datetime import datetime
from config import GRAFANA_URL, API_TOKEN, DISK_USAGE_THRESHOLD
from grafana_utils import (
    make_grafana_request,
    get_datasources,
    find_default_datasource,
    query_timescale
)


def get_current_disk_usage_for_host(grafana_url: str, api_token: str, datasource_uid: str, host: str):
    """
    Récupère l'utilisation disque actuelle d'un host
    """
    sql_query = f"""
SELECT MAX(used_percent) as current_usage
FROM disk 
WHERE host = '{host}'
  AND time > NOW() - INTERVAL '24 hours'
"""
    
    results = query_timescale(grafana_url, api_token, datasource_uid, sql_query)
    
    if not results:
        return None
    
    try:
        for result in results.get('results', {}).values():
            for frame in result.get('frames', []):
                data = frame.get('data', {})
                values = data.get('values', [])
                
                if values and len(values) > 0 and len(values[0]) > 0:
                    usage = values[0][0]
                    if usage is not None:
                        return float(usage)
    except (KeyError, IndexError, TypeError):
        return None
    
    return None


def generate_email_text(alerts_data):
    """
    Génère le contenu de l'email
    """
    if not alerts_data:
        return None
    
    subject = f"🔴 [{len(alerts_data)}] Alertes disque actives - Grafana"
    
    body = f"""Rapport des alertes disque actives
Généré le : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Seuil configuré : {DISK_USAGE_THRESHOLD}%
Nombre d'alertes : {len(alerts_data)}

{'='*80}
{'Host':<45} {'Usage':<10} {'État':<15} {'Depuis'}
{'-'*80}
"""
    
    for alert in sorted(alerts_data, key=lambda x: x['usage'] if x['usage'] else 0, reverse=True):
        host = alert['host']
        usage = f"{alert['usage']:.1f}%" if alert['usage'] else "N/A"
        state = alert['state']
        starts_at = alert['starts_at'][:19] if len(alert['starts_at']) > 19 else alert['starts_at']
        
        emoji = "🔴" if alert['usage'] and alert['usage'] > 50 else "⚠️"
        body += f"{emoji} {host:<43} {usage:<10} {state:<15} {starts_at}\n"
    
    body += f"""
{'='*80}

Détails dans Grafana : {GRAFANA_URL}/alerting/list

---
Ce rapport est généré automatiquement par le script envoyer-rapport-alertes.py
"""
    
    return subject, body


def main():
    """
    Fonction principale
    """
    # Récupérer la datasource
    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    default_ds = find_default_datasource(datasources)
    
    if not default_ds:
        print("✗ Datasource non trouvée.")
        sys.exit(1)
    
    # Récupérer les alertes actives
    instances = make_grafana_request(
        grafana_url=GRAFANA_URL,
        endpoint="/api/alertmanager/grafana/api/v2/alerts",
        api_token=API_TOKEN
    )
    
    if not instances:
        print("ℹ️  Aucune alerte active.")
        return
    
    # Filtrer les alertes disk
    disk_alerts = [
        alert for alert in instances 
        if alert.get('labels', {}).get('type') == 'disk_monitoring'
    ]
    
    if not disk_alerts:
        print("ℹ️  Aucune alerte disk active.")
        return
    
    # Récupérer les valeurs actuelles
    alerts_data = []
    for alert in disk_alerts:
        labels = alert.get('labels', {})
        host = labels.get('host', 'N/A')
        
        current_usage = get_current_disk_usage_for_host(
            GRAFANA_URL, 
            API_TOKEN, 
            default_ds.get('uid'), 
            host
        )
        
        alerts_data.append({
            'host': host,
            'usage': current_usage,
            'state': alert.get('status', {}).get('state', 'N/A'),
            'starts_at': alert.get('startsAt', 'N/A')
        })
    
    # Générer l'email
    result = generate_email_text(alerts_data)
    
    if result:
        subject, body = result
        
        # Afficher dans le terminal
        print("=" * 80)
        print(f"SUJET: {subject}")
        print("=" * 80)
        print(body)
        print("=" * 80)
        
        # Pour envoyer réellement l'email, décommentez et configurez ci-dessous:
        """
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # Configuration SMTP
        smtp_server = "smtp.example.com"
        smtp_port = 587
        smtp_user = "votre@email.com"
        smtp_password = "votre_mot_de_passe"
        to_email = "destinataire@example.com"
        
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        print(f"✓ Email envoyé à {to_email}")
        """


if __name__ == "__main__":
    main()
