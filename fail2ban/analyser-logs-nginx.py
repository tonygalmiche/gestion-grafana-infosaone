#!/usr/bin/env python3
"""
Script d'analyse des logs Nginx pour détecter les attaques potentielles
"""

import re
from collections import defaultdict, Counter
from datetime import datetime
from typing import Dict, List, Tuple
import sys


class NginxLogAnalyzer:
    def __init__(self, log_file: str):
        self.log_file = log_file
        self.log_entries = []
        self.ip_requests = defaultdict(list)
        self.user_agents = defaultdict(int)
        self.status_codes = Counter()
        self.suspicious_ips = set()
        
        # Pattern pour parser les logs Nginx
        self.log_pattern = re.compile(
            r'(?P<ip>[\d\.]+) - - \[(?P<date>[^\]]+)\] '
            r'"(?P<method>\w+) (?P<url>[^"]+) HTTP/[\d\.]+" '
            r'(?P<status>\d+) (?P<size>\d+) "(?P<referer>[^"]*)" "(?P<user_agent>[^"]*)"'
        )
        
        # Bots connus (légitimes mais à surveiller)
        self.known_bots = [
            'googlebot', 'bingbot', 'amazonbot', 'facebookexternalagent',
            'tiktokspider', 'ahrefsbot', 'meta-externalagent'
        ]
        
        # Patterns suspects dans les URLs
        self.suspicious_patterns = [
            r'\.php', r'\.asp', r'\.env', r'wp-admin', r'wp-login',
            r'phpmyadmin', r'admin', r'login', r'\.git', r'\.sql',
            r'shell', r'hack', r'eval\(', r'base64', r'\.bak',
            r'config\.', r'passwd', r'\.zip', r'\.tar'
        ]

    def parse_logs(self):
        """Parse le fichier de logs"""
        print(f"📖 Lecture du fichier: {self.log_file}")
        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    match = self.log_pattern.match(line)
                    if match:
                        entry = match.groupdict()
                        self.log_entries.append(entry)
                        self.ip_requests[entry['ip']].append(entry)
                        self.user_agents[entry['user_agent'].lower()] += 1
                        self.status_codes[entry['status']] += 1
            
            print(f"✅ {len(self.log_entries)} entrées parsées\n")
        except FileNotFoundError:
            print(f"❌ Erreur: Fichier {self.log_file} introuvable")
            sys.exit(1)

    def detect_high_request_rate(self, threshold: int = 50) -> Dict[str, int]:
        """Détecte les IPs avec un taux de requêtes élevé"""
        suspicious = {}
        for ip, requests in self.ip_requests.items():
            count = len(requests)
            if count >= threshold:
                suspicious[ip] = count
                self.suspicious_ips.add(ip)
        return dict(sorted(suspicious.items(), key=lambda x: x[1], reverse=True))

    def detect_bot_traffic(self) -> Dict[str, int]:
        """Identifie le trafic des bots"""
        bot_traffic = {}
        for ua, count in self.user_agents.items():
            for bot in self.known_bots:
                if bot in ua:
                    bot_traffic[bot] = bot_traffic.get(bot, 0) + count
        return dict(sorted(bot_traffic.items(), key=lambda x: x[1], reverse=True))

    def detect_suspicious_urls(self) -> List[Tuple[str, str, str]]:
        """Détecte les URLs suspectes"""
        suspicious = []
        for entry in self.log_entries:
            url = entry['url'].lower()
            for pattern in self.suspicious_patterns:
                if re.search(pattern, url):
                    suspicious.append((entry['ip'], entry['url'], pattern))
                    self.suspicious_ips.add(entry['ip'])
                    break
        return suspicious

    def detect_scanning_behavior(self) -> Dict[str, List[str]]:
        """Détecte les comportements de scanning (nombreuses URLs différentes)"""
        scanning_ips = {}
        for ip, requests in self.ip_requests.items():
            unique_urls = set(r['url'] for r in requests)
            if len(unique_urls) >= 20:  # Plus de 20 URLs différentes
                scanning_ips[ip] = list(unique_urls)[:10]  # Top 10
                self.suspicious_ips.add(ip)
        return dict(sorted(scanning_ips.items(), key=lambda x: len(x[1]), reverse=True))

    def detect_error_patterns(self) -> Dict[str, int]:
        """Détecte les IPs générant beaucoup d'erreurs"""
        error_ips = defaultdict(int)
        for entry in self.log_entries:
            status = int(entry['status'])
            if status >= 400:  # Erreurs 4xx et 5xx
                error_ips[entry['ip']] += 1
        
        # Ne garder que celles avec plus de 5 erreurs
        suspicious_errors = {ip: count for ip, count in error_ips.items() if count > 5}
        for ip in suspicious_errors:
            self.suspicious_ips.add(ip)
        
        return dict(sorted(suspicious_errors.items(), key=lambda x: x[1], reverse=True))

    def detect_302_redirects(self) -> Dict[str, int]:
        """Détecte les IPs avec beaucoup de redirections 302"""
        redirect_ips = defaultdict(int)
        for entry in self.log_entries:
            if entry['status'] == '302':
                redirect_ips[entry['ip']] += 1
        
        # Plus de 10 redirections = suspect
        suspicious_redirects = {ip: count for ip, count in redirect_ips.items() if count > 10}
        return dict(sorted(suspicious_redirects.items(), key=lambda x: x[1], reverse=True))

    def get_ip_details(self, ip: str) -> Dict:
        """Obtient les détails d'une IP suspecte"""
        requests = self.ip_requests[ip]
        user_agents = set(r['user_agent'] for r in requests)
        urls = [r['url'] for r in requests]
        status_codes = Counter(r['status'] for r in requests)
        
        return {
            'total_requests': len(requests),
            'unique_urls': len(set(urls)),
            'user_agents': list(user_agents),
            'status_codes': dict(status_codes),
            'sample_urls': urls[:5]
        }

    def generate_report(self):
        """Génère le rapport d'analyse"""
        print("=" * 80)
        print("🔍 RAPPORT D'ANALYSE DES LOGS NGINX")
        print("=" * 80)
        print(f"📊 Statistiques générales:")
        print(f"   - Total d'entrées: {len(self.log_entries)}")
        print(f"   - IPs uniques: {len(self.ip_requests)}")
        print(f"   - User-Agents uniques: {len(self.user_agents)}")
        print()

        # Codes de statut
        print("📈 Codes de statut HTTP:")
        for status, count in self.status_codes.most_common(10):
            print(f"   - {status}: {count}")
        print()

        # IPs avec taux de requêtes élevé
        print("🚨 IPs avec taux de requêtes élevé (≥50 requêtes):")
        high_rate = self.detect_high_request_rate()
        for ip, count in list(high_rate.items())[:15]:
            print(f"   - {ip}: {count} requêtes")
        print()

        # Trafic des bots
        print("🤖 Trafic des bots identifiés:")
        bot_traffic = self.detect_bot_traffic()
        total_bot_requests = sum(bot_traffic.values())
        bot_percentage = (total_bot_requests / len(self.log_entries)) * 100
        for bot, count in bot_traffic.items():
            print(f"   - {bot}: {count} requêtes")
        print(f"   📊 Total bots: {total_bot_requests} requêtes ({bot_percentage:.1f}%)")
        print()

        # Redirections 302 suspectes
        print("🔄 IPs avec nombreuses redirections 302:")
        redirects = self.detect_302_redirects()
        for ip, count in list(redirects.items())[:10]:
            print(f"   - {ip}: {count} redirections")
        print()

        # Comportement de scanning
        print("🔎 Comportements de scanning détectés:")
        scanning = self.detect_scanning_behavior()
        for ip, urls in list(scanning.items())[:5]:
            print(f"   - {ip}: {len(urls)} URLs différentes")
            print(f"     Exemples: {', '.join(urls[:3])}")
        print()

        # URLs suspectes
        print("⚠️  URLs suspectes détectées:")
        suspicious_urls = self.detect_suspicious_urls()
        if suspicious_urls:
            for ip, url, pattern in suspicious_urls[:10]:
                print(f"   - {ip}: {url} (pattern: {pattern})")
        else:
            print("   ✅ Aucune URL suspecte détectée")
        print()

        # Erreurs
        print("❌ IPs générant beaucoup d'erreurs:")
        errors = self.detect_error_patterns()
        for ip, count in list(errors.items())[:10]:
            print(f"   - {ip}: {count} erreurs")
        print()

        # Résumé des IPs suspectes
        print("=" * 80)
        print(f"🎯 RÉSUMÉ: {len(self.suspicious_ips)} IPs suspectes identifiées")
        print("=" * 80)
        
        # Top 10 des IPs les plus suspectes
        print("\n🔥 Top 10 des IPs les plus actives et potentiellement dangereuses:\n")
        top_suspicious = sorted(
            [(ip, len(self.ip_requests[ip])) for ip in self.suspicious_ips],
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        for i, (ip, count) in enumerate(top_suspicious, 1):
            print(f"{i}. {ip} - {count} requêtes")
            details = self.get_ip_details(ip)
            print(f"   URLs uniques: {details['unique_urls']}")
            print(f"   User-Agent: {details['user_agents'][0][:80]}...")
            print(f"   Codes statut: {details['status_codes']}")
            print()

        # Recommandations
        print("=" * 80)
        print("💡 RECOMMANDATIONS")
        print("=" * 80)
        
        if total_bot_requests / len(self.log_entries) > 0.7:
            print("⚠️  Plus de 70% du trafic provient de bots!")
            print("   → Considérer l'utilisation de Cloudflare ou fail2ban")
            print("   → Configurer un robots.txt restrictif")
        
        if len(high_rate) > 20:
            print("\n⚠️  Nombreuses IPs avec taux de requêtes élevé")
            print("   → Mettre en place un rate limiting dans Nginx")
            print("   → Exemple: limit_req_zone $binary_remote_addr zone=mylimit:10m rate=10r/s;")
        
        if suspicious_urls:
            print("\n⚠️  URLs suspectes détectées")
            print("   → Bloquer les accès à des chemins sensibles (admin, .env, etc.)")
            print("   → Vérifier les logs pour des tentatives d'exploitation")
        
        print("\n📝 Pour bloquer une IP avec fail2ban:")
        print("   sudo fail2ban-client set nginx-http-auth banip <IP>")
        
        print("\n📝 Pour bloquer une IP directement dans Nginx:")
        print("   Ajouter dans nginx.conf: deny <IP>;")
        print("=" * 80)


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyser-logs-nginx.py <fichier_log>")
        print("Exemple: python analyser-logs-nginx.py /var/log/nginx/access.log")
        sys.exit(1)
    
    log_file = sys.argv[1]
    
    analyzer = NginxLogAnalyzer(log_file)
    analyzer.parse_logs()
    analyzer.generate_report()


if __name__ == "__main__":
    main()
