#!/bin/bash
# ==============================================================================
# SCRIPT DE SURVEILLANCE FAIL2BAN - AFFICHAGE EN TEMPS RÉEL
# ==============================================================================

echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║            SURVEILLANCE FAIL2BAN - ANTI-BOTS                              ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""

# Fonction pour afficher le statut d'une jail
afficher_jail() {
    local jail=$1
    local nom=$2
    
    if fail2ban-client status "$jail" &>/dev/null; then
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🔒 $nom"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        fail2ban-client status "$jail"
        echo ""
    fi
}

# Statut général
echo "📊 STATUT GÉNÉRAL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fail2ban-client status
echo ""

# Détails de chaque jail
afficher_jail "nginx-meta-abuse" "JAIL META/FACEBOOK (ban 7 jours)"
afficher_jail "nginx-bad-bots" "JAIL BAD BOTS (ban 24h)"
afficher_jail "nginx-scanner" "JAIL SCANNERS (ban 48h)"

# IPs bannies par iptables
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚫 IPTABLES - IPs bannies actuellement"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
iptables -L -n -v | grep -E "f2b|DROP" | head -20
echo ""

# Derniers bans
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔨 DERNIERS BANNISSEMENTS (10 derniers)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
tail -30 /var/log/fail2ban.log | grep "Ban " | tail -10
echo ""

# Compteurs
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📈 STATISTIQUES AUJOURD'HUI"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

TODAY=$(date +%Y-%m-%d)
echo "🔒 Bans Meta:        $(grep "$TODAY" /var/log/fail2ban.log | grep "nginx-meta-abuse" | grep "Ban " | wc -l)"
echo "🔒 Bans Bad Bots:    $(grep "$TODAY" /var/log/fail2ban.log | grep "nginx-bad-bots" | grep "Ban " | wc -l)"
echo "🔒 Bans Scanners:    $(grep "$TODAY" /var/log/fail2ban.log | grep "nginx-scanner" | grep "Ban " | wc -l)"
echo ""

# Top IPs bannies
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 TOP 10 IPs les plus bannies aujourd'hui"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep "$TODAY" /var/log/fail2ban.log | grep "Ban " | awk '{print $NF}' | sort | uniq -c | sort -rn | head -10
echo ""

echo "💡 Pour surveiller en temps réel: tail -f /var/log/fail2ban.log"
