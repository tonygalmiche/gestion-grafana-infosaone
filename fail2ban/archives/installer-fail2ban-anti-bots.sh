#!/bin/bash
# ==============================================================================
# SCRIPT D'INSTALLATION FAIL2BAN ANTI-BOTS
# ==============================================================================

set -e  # Arrêt en cas d'erreur

echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║         INSTALLATION FAIL2BAN ANTI-BOTS & META                            ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""

# Vérifier que le script est exécuté en root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Ce script doit être exécuté en tant que root (sudo)"
    exit 1
fi

# Vérifier que fail2ban est installé
if ! command -v fail2ban-client &> /dev/null; then
    echo "⚠️  Fail2ban n'est pas installé. Installation..."
    apt update
    apt install -y fail2ban
fi

echo "✅ Fail2ban est installé"
echo ""

# Répertoire des fichiers sources
SOURCE_DIR="/root/MesDocuments/gestion-grafana-infosaone"

# Copier les fichiers de configuration
echo "📋 Installation des fichiers de configuration..."

# 1. Jail (prison)
if [ -f "$SOURCE_DIR/fail2ban-jail-nginx-bad-bots.conf" ]; then
    cp "$SOURCE_DIR/fail2ban-jail-nginx-bad-bots.conf" /etc/fail2ban/jail.d/nginx-bad-bots.conf
    echo "✅ Jail installée: /etc/fail2ban/jail.d/nginx-bad-bots.conf"
else
    echo "❌ Fichier jail introuvable: $SOURCE_DIR/fail2ban-jail-nginx-bad-bots.conf"
    exit 1
fi

# 2. Filtre Meta
if [ -f "$SOURCE_DIR/fail2ban-filter-meta-abuse.conf" ]; then
    cp "$SOURCE_DIR/fail2ban-filter-meta-abuse.conf" /etc/fail2ban/filter.d/nginx-meta-abuse.conf
    echo "✅ Filtre Meta installé: /etc/fail2ban/filter.d/nginx-meta-abuse.conf"
else
    echo "❌ Fichier filtre Meta introuvable"
    exit 1
fi

# 3. Filtre Scanner
if [ -f "$SOURCE_DIR/fail2ban-filter-scanner.conf" ]; then
    cp "$SOURCE_DIR/fail2ban-filter-scanner.conf" /etc/fail2ban/filter.d/nginx-scanner.conf
    echo "✅ Filtre Scanner installé: /etc/fail2ban/filter.d/nginx-scanner.conf"
else
    echo "❌ Fichier filtre Scanner introuvable"
    exit 1
fi

# 4. Filtre Bad Bots (existant)
if [ -f "$SOURCE_DIR/fail2ban-nginx-bad-bots.conf" ]; then
    cp "$SOURCE_DIR/fail2ban-nginx-bad-bots.conf" /etc/fail2ban/filter.d/nginx-bad-bots.conf
    echo "✅ Filtre Bad Bots installé: /etc/fail2ban/filter.d/nginx-bad-bots.conf"
else
    echo "⚠️  Filtre Bad Bots introuvable (optionnel)"
fi

echo ""
echo "🔍 Test des filtres..."

# Tester les filtres
fail2ban-regex /var/log/nginx/odoo.access.log /etc/fail2ban/filter.d/nginx-meta-abuse.conf
echo ""

# Redémarrer fail2ban
echo "🔄 Redémarrage de fail2ban..."
systemctl restart fail2ban

# Attendre que fail2ban démarre
sleep 2

# Vérifier le statut
echo ""
echo "📊 Statut des jails:"
fail2ban-client status

echo ""
echo "✅ Installation terminée!"
echo ""
echo "📌 Commandes utiles:"
echo "   • Statut général:           fail2ban-client status"
echo "   • Statut jail Meta:         fail2ban-client status nginx-meta-abuse"
echo "   • Statut jail Bad Bots:     fail2ban-client status nginx-bad-bots"
echo "   • Statut jail Scanner:      fail2ban-client status nginx-scanner"
echo "   • Débannir une IP:          fail2ban-client set nginx-meta-abuse unbanip <IP>"
echo "   • Bannir manuellement:      fail2ban-client set nginx-meta-abuse banip <IP>"
echo "   • Voir les logs:            tail -f /var/log/fail2ban.log"
echo ""
