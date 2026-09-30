#!/usr/bin/env python3
"""
Script autonome de surveillance portsentry - SANS Grafana Alerting
Interroge directement TimescaleDB et envoie des emails

Fonctionnement (destiné à être lancé périodiquement, ex. via cron) :
1. La période analysée va de la fin de la période précédente (sauvegardée dans
   STATE_FILE) jusqu'à maintenant moins PORTSENTRY_DELAY_MINUTES (marge pour
   les données Telegraf pas encore arrivées). Un scan survenu pendant une
   plage où le cron ne tourne pas (la nuit) est donc signalé au passage suivant.
   Premier lancement : PORTSENTRY_FIRST_RUN_MINUTES ; après un long arrêt, la
   période est limitée à PORTSENTRY_MAX_WINDOW_HOURS.
2. get_portsentry_data() fait une seule requête sur la table portsentry : pour
   chaque host, le dernier relevé reçu et les relevés > 0 de la période (pic,
   nombre, première et dernière détection). Chaque relevé compte les scans de
   la minute écoulée (script Telegraf à 60 s) ; on utilise max() pour le pic.
3. get_active_hosts() liste les hosts qui envoient des données dans system :
   un host qui a déjà envoyé du portsentry, qui est actif, mais dont la
   remontée portsentry s'est arrêtée (> PORTSENTRY_NO_DATA_MINUTES) est
   signalé (script de collecte en erreur, portsentry arrêté...). Un host
   complètement arrêté est déjà signalé par surveiller-disk-autonome.py.
4. Par défaut (--mail auto), un email est envoyé uniquement si des scans ont
   été détectés sur la période, ou si la liste des hosts sans remontée
   portsentry a changé (nouvelle panne ou retour à la normale).
5. La fin de période n'est sauvegardée que si la requête a abouti et, en cas
   de scans, si l'email est parti : sinon la même période est reprise au
   passage suivant.

Options :
  --heures N    analyse les N dernières heures au lieu de repartir de l'état
                sauvegardé (ex. --heures 24 chaque nuit)
  --mail auto   (défaut) email seulement si scans ou changement de remontée
  --mail oui    email dans tous les cas (ex. rapport de la nuit avec --heures 24)
  --mail non    affiche le résultat sans envoyer d'email ni sauvegarder l'état
"""

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import argparse
import config
from config import (
    GRAFANA_URL, API_TOKEN, SMTP_SERVER, SMTP_PORT, SMTP_USE_TLS,
    SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL, TO_EMAIL
)
from grafana_utils import get_datasources, find_default_datasource, query_timescale, send_email_report
import json
import os

STATE_FILE = "/tmp/surveiller-portsentry-state.json"

# Paramètres optionnels dans config.py (valeurs par défaut sinon)
PORTSENTRY_EXCLUDED_HOSTS    = getattr(config, 'PORTSENTRY_EXCLUDED_HOSTS', [])
PORTSENTRY_NO_DATA_MINUTES   = getattr(config, 'PORTSENTRY_NO_DATA_MINUTES', 10)
PORTSENTRY_DELAY_MINUTES     = getattr(config, 'PORTSENTRY_DELAY_MINUTES', 1)
PORTSENTRY_FIRST_RUN_MINUTES = getattr(config, 'PORTSENTRY_FIRST_RUN_MINUTES', 15)
PORTSENTRY_MAX_WINDOW_HOURS  = getattr(config, 'PORTSENTRY_MAX_WINDOW_HOURS', 72)

SQL_FORMAT = '%Y-%m-%d %H:%M:%S'


def load_state():
    """Charge l'état de l'exécution précédente (fin de période, hosts sans remontée)"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
            return {
                'last_until': datetime.fromisoformat(state['last_until']),
                'silent_hosts': state.get('silent_hosts', []),
            }
        except Exception as e:
            print(f"Erreur lecture état {STATE_FILE} : {e}")
    return {'last_until': None, 'silent_hosts': []}


def save_state(until, silent_hosts):
    """Sauvegarde la fin de la période analysée et les hosts sans remontée"""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({'last_until': until.isoformat(), 'silent_hosts': sorted(silent_hosts)}, f)
    except Exception as e:
        print(f"Erreur sauvegarde état {STATE_FILE} : {e}")


def positive_hours(text):
    """Nombre d'heures strictement positif (option --heures)"""
    try:
        hours = float(text.replace(',', '.'))
    except ValueError:
        hours = 0
    if hours <= 0:
        raise argparse.ArgumentTypeError(f"nombre d'heures invalide : {text!r}")
    return hours


def get_period(state, hours=None):
    """Retourne (since, until) en UTC pour la période à analyser"""
    until = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=PORTSENTRY_DELAY_MINUTES)
    if hours:
        # Période demandée explicitement : pas de limite de durée
        return until - timedelta(hours=hours), until
    since = state['last_until'] or until - timedelta(minutes=PORTSENTRY_FIRST_RUN_MINUTES)
    since = max(since, until - timedelta(hours=PORTSENTRY_MAX_WINDOW_HOURS))
    return since, until


def to_datetime(ms):
    """Convertit un timestamp Grafana (millisecondes) en datetime UTC"""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc) if ms is not None else None


def get_portsentry_data(datasource_uid, since, until):
    """Récupère, par host, le dernier relevé reçu et les détections de la période.
    Retourne None si la requête a échoué."""
    # Dates en UTC : valable pour une colonne time en timestamp sans fuseau (UTC)
    # comme en timestamptz (fuseau de la session PostgreSQL : Etc/UTC)
    since_sql = since.strftime(SQL_FORMAT)
    until_sql = until.strftime(SQL_FORMAT)
    # Les hosts qui ont remonté du portsentry dans les dernières 24h servent de référence
    window_sql = min(since, until - timedelta(days=1)).strftime(SQL_FORMAT)
    period = f"time > '{since_sql}' AND time <= '{until_sql}' AND value > 0"

    sql = f"""
    SELECT
        host,
        max(time) AS last_seen,
        max(value) FILTER (WHERE {period}) AS peak,
        count(*)   FILTER (WHERE {period}) AS nb,
        min(time)  FILTER (WHERE {period}) AS first_scan,
        max(time)  FILTER (WHERE {period}) AS last_scan
    FROM portsentry
    WHERE time > '{window_sql}'
    GROUP BY host
    ORDER BY host
    """

    results = query_timescale(GRAFANA_URL, API_TOKEN, datasource_uid, sql)

    if not results or 'results' not in results:
        return None

    hosts = []
    for result in results.get('results', {}).values():
        if 'error' in result:
            print(f"Erreur requête portsentry : {result['error']}")
            return None
        for frame in result.get('frames', []):
            data_values = frame.get('data', {}).get('values', [])

            if len(data_values) >= 6:
                for i in range(len(data_values[0])):
                    hosts.append({
                        'host': data_values[0][i],
                        'last_seen': to_datetime(data_values[1][i]),
                        'peak': data_values[2][i],
                        'nb': data_values[3][i] or 0,
                        'first_scan': to_datetime(data_values[4][i]),
                        'last_scan': to_datetime(data_values[5][i]),
                    })

    return hosts


def get_active_hosts(datasource_uid):
    """Retourne les hosts qui envoient des données dans system (None si erreur)"""
    sql = f"""
    SELECT DISTINCT host
    FROM system
    WHERE time >= now() - INTERVAL '{PORTSENTRY_NO_DATA_MINUTES} minutes'
    """

    results = query_timescale(GRAFANA_URL, API_TOKEN, datasource_uid, sql)

    if not results or 'results' not in results:
        return None

    active = set()
    for result in results.get('results', {}).values():
        for frame in result.get('frames', []):
            data_values = frame.get('data', {}).get('values', [])
            if data_values:
                active.update(data_values[0])

    return active


def format_paris(dt, fmt='%d/%m %H:%M'):
    """Formate une date UTC en heure de Paris"""
    return dt.astimezone(ZoneInfo('Europe/Paris')).strftime(fmt) if dt else "-"


def build_subject(scanned, silent_hosts, recovered_hosts, nb_hosts):
    """Construit le sujet de l'email"""
    date_time_str = datetime.now(ZoneInfo('Europe/Paris')).strftime('%d/%m %H:%M')
    subject_parts = [f"[Grafana Portsentry] {date_time_str}"]

    if scanned:
        names = ', '.join(h['host'] for h in scanned)
        subject_parts.append(f"🔴 {len(scanned)} host(s) scanné(s) ({names})")
    if silent_hosts:
        subject_parts.append(f"🟠 {len(silent_hosts)} sans remontée portsentry")
    if recovered_hosts and not scanned and not silent_hosts:
        subject_parts.append("✅ remontée portsentry rétablie")
    if not scanned and not silent_hosts and not recovered_hosts:
        subject_parts.append(f"✅ aucun scan sur {nb_hosts} hosts")

    return " ".join(subject_parts)


def all_hosts_table(hosts_by_name, silent_hosts):
    """Tableau HTML et texte de tous les hosts triés par nom, statut ✅/🔴 en dernière colonne
    (option --mail oui)"""
    red = 'style="text-align: right; background-color: red; color: white; font-weight: bold;"'
    html = """
    <h3>Tous les hosts</h3>
    <table>
        <tr>
            <th>Serveur</th>
            <th>Première détection</th>
            <th>Dernière détection</th>
            <th style="text-align: right;">Pic</th>
            <th style="text-align: right;">Relevés &gt; 0</th>
            <th>Dernier relevé</th>
            <th style="text-align: center;">Statut</th>
        </tr>
"""
    text = "Tous les hosts :\n"
    for name in sorted(hosts_by_name):
        h = hosts_by_name[name]
        is_scan = h['nb'] > 0
        is_silent = name in silent_hosts
        status = "🔴" if is_scan or is_silent else "✅"
        last_seen_style = 'style="background-color: red; color: white; font-weight: bold;"' if is_silent else ''
        html += f"""
        <tr>
            <td>{name}</td>
            <td>{format_paris(h['first_scan'])}</td>
            <td>{format_paris(h['last_scan'])}</td>
            <td {red if is_scan else 'style="text-align: right;"'}>{h['peak'] if is_scan else ''}</td>
            <td style="text-align: right;">{h['nb'] if is_scan else ''}</td>
            <td {last_seen_style}>{format_paris(h['last_seen'])}</td>
            <td style="text-align: center;">{status}</td>
        </tr>
"""
        scan_str = (f"{format_paris(h['first_scan'])} -> {format_paris(h['last_scan'])}  pic {h['peak']}"
                    if is_scan else "")
        silent_str = f"  remontée arrêtée depuis {format_paris(h['last_seen'])}" if is_silent else ""
        text += f"{name:<30} {scan_str}{silent_str}  {status}\n"
    html += """
    </table>
"""
    return html, text


def send_summary_email(scanned, silent_hosts, recovered_hosts, hosts_by_name, since, until, all_hosts=False):
    """Envoie l'email récapitulatif (all_hosts : tableau de tous les hosts, option --mail oui)"""
    subject = build_subject(scanned, silent_hosts, recovered_hosts, len(hosts_by_name))
    period_str = f"du {format_paris(since)} au {format_paris(until)}"

    html_body = f"""
<html>
<head>
    <style>
        body {{ font-family: sans-serif; font-size: 14px; }}
        h2 {{ color: #333; font-size: 16px; margin-bottom: 10px; }}
        h3 {{ color: #333; font-size: 14px; margin-top: 20px; }}
        table {{ border-collapse: collapse; width: 700px; margin-top: 10px; font-size: 12px; }}
        th {{ background-color: #4CAF50; color: white; padding: 3px; text-align: left; font-size: 14px; }}
        td {{ padding: 3px; border-bottom: 1px solid #ddd; }}
        .summary {{ background-color: #f0f0f0; padding: 6px; border-radius: 5px; margin-bottom: 10px; font-size: 12px; }}
    </style>
</head>
<body>
    <h2>🛡️ Rapport portsentry</h2>

    <div class="summary">
        <strong>Période analysée :</strong> {period_str}<br>
        Hosts avec scans détectés : <strong style="color: red;">{len(scanned)}</strong><br>
        Hosts sans remontée portsentry (>{PORTSENTRY_NO_DATA_MINUTES}min) : <strong style="color: orange;">{len(silent_hosts)}</strong>
    </div>
"""

    text_body = f"Rapport portsentry\n{'='*50}\n\nPériode analysée : {period_str}\n\n"

    if all_hosts:
        table_html, table_text = all_hosts_table(hosts_by_name, silent_hosts)
        html_body += table_html
        text_body += table_text + "\n"
    elif scanned:
        html_body += """
    <h3>Scans détectés</h3>
    <table>
        <tr>
            <th>Serveur</th>
            <th>Première détection</th>
            <th>Dernière détection</th>
            <th style="text-align: right;">Pic</th>
            <th style="text-align: right;">Relevés &gt; 0</th>
        </tr>
"""
        text_body += "Scans détectés :\n"
        for h in scanned:
            html_body += f"""
        <tr>
            <td>{h['host']}</td>
            <td>{format_paris(h['first_scan'])}</td>
            <td>{format_paris(h['last_scan'])}</td>
            <td style="text-align: right; background-color: red; color: white; font-weight: bold;">{h['peak']}</td>
            <td style="text-align: right;">{h['nb']}</td>
        </tr>
"""
            text_body += (f"🔴 {h['host']:<30} {format_paris(h['first_scan'])} -> {format_paris(h['last_scan'])}"
                          f"  pic {h['peak']}  ({h['nb']} relevés)\n")
        html_body += """
    </table>
"""

    if scanned:
        html_body += """
    <p style="color: #666; font-size: 12px;">
        Pic = nombre maximal de scans détectés en une minute. Détail (IP source, ports) sur le host :
        <code>journalctl -t portsentry | grep -E "from host|Scan from"</code>
    </p>
"""
        text_body += "\nDétail sur le host : journalctl -t portsentry | grep -E \"from host|Scan from\"\n\n"

    if not all_hosts and (silent_hosts or recovered_hosts):
        html_body += """
    <h3>Remontée portsentry</h3>
    <table>
        <tr>
            <th>Statut</th>
            <th>Serveur</th>
            <th>Dernier relevé portsentry</th>
        </tr>
"""
        text_body += "Remontée portsentry :\n"
        for name in sorted(silent_hosts):
            last_seen = format_paris(hosts_by_name[name]['last_seen'])
            html_body += f"""
        <tr>
            <td style="color: orange;">🟠 arrêtée</td>
            <td>{name}</td>
            <td style="background-color: red; color: white; font-weight: bold;">{last_seen}</td>
        </tr>
"""
            text_body += f"🟠 arrêtée  {name:<30} dernier relevé {last_seen}\n"
        for name in sorted(recovered_hosts):
            html_body += f"""
        <tr>
            <td style="color: green;">✅ rétablie</td>
            <td>{name}</td>
            <td></td>
        </tr>
"""
            text_body += f"✅ rétablie {name}\n"
        html_body += """
    </table>
"""

    html_body += """
    <p style="margin-top: 20px; color: #666; font-size: 12px;">
        Ce rapport est généré automatiquement par le système de surveillance portsentry.
    </p>
</body>
</html>
"""

    return subject, send_email_report(
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


def print_summary(scanned, silent_hosts, recovered_hosts, hosts_by_name, since, until):
    """Affiche le résultat en console (option --mail non)"""
    print(f"{build_subject(scanned, silent_hosts, recovered_hosts, len(hosts_by_name))} - mode --mail non")
    print(f"Période analysée : du {format_paris(since)} au {format_paris(until)}")
    for h in scanned:
        print(f"  🔴 {h['host']:<30} {format_paris(h['first_scan'])} -> {format_paris(h['last_scan'])}"
              f"  pic {h['peak']}  ({h['nb']} relevés)")
    for name in silent_hosts:
        print(f"  🟠 {name:<30} remontée arrêtée, dernier relevé {format_paris(hosts_by_name[name]['last_seen'])}")
    for name in recovered_hosts:
        print(f"  ✅ {name:<30} remontée rétablie")


def main():
    """Fonction principale"""
    parser = argparse.ArgumentParser(description="Surveillance portsentry : alerte par email en cas de scan")
    parser.add_argument('--heures', type=positive_hours, metavar='N',
                        help="analyse les N dernières heures (ex. 24) au lieu de repartir de l'état sauvegardé")
    parser.add_argument('--mail', choices=['auto', 'oui', 'non'], default='auto',
                        help="auto (défaut) : email seulement si scans ou changement de remontée ; "
                             "oui : email dans tous les cas ; "
                             "non : affichage seul, sans email ni sauvegarde de l'état")
    args = parser.parse_args()

    datasources = get_datasources(GRAFANA_URL, API_TOKEN)
    default_ds = find_default_datasource(datasources)

    if not default_ds:
        print("Erreur : Aucune datasource trouvée")
        return

    state = load_state()
    since, until = get_period(state, args.heures)

    hosts_data = get_portsentry_data(default_ds.get('uid'), since, until)
    active_hosts = get_active_hosts(default_ds.get('uid'))

    if hosts_data is None or active_hosts is None:
        # Période non sauvegardée : elle sera reprise au prochain passage
        print(f"[Grafana Portsentry] Erreur de requête, période du {format_paris(since)} reprise au prochain passage")
        return

    hosts_data = [h for h in hosts_data if h['host'] not in PORTSENTRY_EXCLUDED_HOSTS]
    hosts_by_name = {h['host']: h for h in hosts_data}

    # Hosts avec au moins un relevé > 0 sur la période, détection la plus récente en premier
    scanned = sorted((h for h in hosts_data if h['nb'] > 0), key=lambda h: h['last_scan'], reverse=True)

    # Hosts actifs (system) dont la remontée portsentry s'est arrêtée
    now = datetime.now(timezone.utc)
    silent_hosts = sorted(
        h['host'] for h in hosts_data
        if h['host'] in active_hosts
        and (now - h['last_seen']).total_seconds() > PORTSENTRY_NO_DATA_MINUTES * 60
    )
    previous_silent = set(state['silent_hosts'])
    new_silent = set(silent_hosts) - previous_silent
    # Rétabli = relevé portsentry récent (un host complètement arrêté n'est pas "rétabli")
    recovered_hosts = sorted(
        name for name in previous_silent - set(silent_hosts)
        if name in hosts_by_name
        and (now - hosts_by_name[name]['last_seen']).total_seconds() <= PORTSENTRY_NO_DATA_MINUTES * 60
    )

    if args.mail == 'non':
        print_summary(scanned, silent_hosts, recovered_hosts, hosts_by_name, since, until)
        return

    if args.mail == 'oui' or scanned or new_silent or recovered_hosts:
        subject, sent = send_summary_email(scanned, silent_hosts, recovered_hosts, hosts_by_name, since, until,
                                           all_hosts=(args.mail == 'oui'))
        if not sent:
            # Email non parti : on garde l'ancien état pour renvoyer au prochain passage
            print(f"{subject} - Erreur envoi email, période reprise au prochain passage")
            return
        print(f"{subject} - Email envoyé")
    else:
        silent_str = f", {len(silent_hosts)} sans remontée (déjà signalés)" if silent_hosts else ""
        print(f"[Grafana Portsentry] {format_paris(until)} ✅ aucun scan sur {len(hosts_data)} hosts"
              f"{silent_str} - Email non envoyé")

    save_state(until, silent_hosts)


if __name__ == "__main__":
    main()
