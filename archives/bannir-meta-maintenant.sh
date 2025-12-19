#!/bin/bash
# ==============================================================================
# BANNIR IMMÉDIATEMENT TOUTES LES IPs META DÉTECTÉES DANS LES LOGS
# ==============================================================================

echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║         BANNISSEMENT IMMÉDIAT DES IPs META/FACEBOOK                       ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""

LOG_FILE="/var/log/nginx/odoo.access.log"
JAIL_NAME="nginx-meta-abuse"

# Vérifier que fail2ban fonctionne
if ! systemctl is-active --quiet fail2ban; then
    echo "❌ Fail2ban n'est pas actif"
    exit 1
fi

# Vérifier que la jail existe
if ! fail2ban-client status "$JAIL_NAME" &>/dev/null; then
    echo "❌ La jail $JAIL_NAME n'existe pas"
    echo "💡 Installer d'abord avec: sudo bash installer-fail2ban-anti-bots.sh"
    exit 1
fi

echo "🔍 Analyse du fichier de logs: $LOG_FILE"
echo ""

# Extraire toutes les IPs Meta/Facebook des logs
echo "📋 Extraction des IPs Meta/Facebook..."
IPS_META=$(grep -E 'meta-externalagent|facebookexternalagent' "$LOG_FILE" | \
           awk '{print $1}' | \
           sort -u)

# Compter
TOTAL=$(echo "$IPS_META" | wc -l)
echo "✅ $TOTAL IPs Meta/Facebook trouvées"
echo ""

if [ $TOTAL -eq 0 ]; then
    echo "✅ Aucune IP Meta à bannir"
    exit 0
fi

# Afficher les IPs
echo "IPs qui vont être bannies:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$IPS_META"
echo ""

# Confirmation
read -p "Voulez-vous bannir ces $TOTAL IPs? [o/N] " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Oo]$ ]]; then
    echo "❌ Annulé"
    exit 0
fi

# Bannir chaque IP
echo ""
echo "🔨 Bannissement en cours..."
BANNED=0
ALREADY_BANNED=0

while IFS= read -r ip; do
    if [ -n "$ip" ]; then
        # Vérifier si déjà bannie
        if fail2ban-client status "$JAIL_NAME" | grep -q "$ip"; then
            echo "⏭️  Déjà bannie: $ip"
            ((ALREADY_BANNED++))
        else
            # Bannir
            if fail2ban-client set "$JAIL_NAME" banip "$ip" &>/dev/null; then
                echo "✅ Bannie: $ip"
                ((BANNED++))
            else
                echo "❌ Erreur: $ip"
            fi
        fi
    fi
done <<< "$IPS_META"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 RÉSUMÉ"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Total IPs détectées:     $TOTAL"
echo "Nouvelles IPs bannies:   $BANNED"
echo "Déjà bannies:            $ALREADY_BANNED"
echo ""

# Statut de la jail
echo "🔍 Statut de la jail $JAIL_NAME:"
fail2ban-client status "$JAIL_NAME"
echo ""

echo "✅ Terminé!"
echo ""
echo "💡 Commandes utiles:"
echo "   • Voir les bans: fail2ban-client status $JAIL_NAME"
echo "   • Débannir: fail2ban-client set $JAIL_NAME unbanip <IP>"
