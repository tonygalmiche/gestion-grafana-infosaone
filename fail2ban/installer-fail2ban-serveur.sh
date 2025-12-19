#!/bin/bash
# ==============================================================================
# INSTALLATION COMPLÈTE FAIL2BAN - À EXÉCUTER SUR LE SERVEUR
# ==============================================================================

set -e

echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║         INSTALLATION FAIL2BAN ANTI-META/BOTS                              ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""

# 1. Créer le filtre nginx-meta-abuse
echo "📝 Création du filtre nginx-meta-abuse..."
cat > /etc/fail2ban/filter.d/nginx-meta-abuse.conf << 'EOF'
# ==============================================================================
# FAIL2BAN - FILTRE POUR BLOQUER META/FACEBOOK
# ==============================================================================

[Definition]

ignoreregex = 

failregex = ^<HOST>.*meta-externalagent.*$
            ^<HOST>.*facebookexternalagent.*$
            ^<HOST>.*FacebookBot.*$
            ^<HOST>.*facebookplatform.*$
            ^<HOST>.*facebot.*$

[INCLUDES]
before = common.conf
EOF

# 2. Créer le filtre nginx-scanner
echo "📝 Création du filtre nginx-scanner..."
cat > /etc/fail2ban/filter.d/nginx-scanner.conf << 'EOF'
# ==============================================================================
# FAIL2BAN - FILTRE POUR DÉTECTER LES SCANNERS
# ==============================================================================

[Definition]

ignoreregex = ^<HOST>.*(Googlebot|Bingbot|bingbot|Google-InspectionTool).*$

failregex = ^<HOST>.*"GET /blog/.*tag/.*$
            ^<HOST>.*"GET /.*page/\d+.*$
            ^<HOST>.*" 302 
            ^<HOST>.*" 429 

[INCLUDES]
before = common.conf
EOF

# 3. Créer/Mettre à jour le filtre nginx-bad-bots
echo "📝 Création du filtre nginx-bad-bots..."
cat > /etc/fail2ban/filter.d/nginx-bad-bots.conf << 'EOF'
# ==============================================================================
# FAIL2BAN - FILTRE AMÉLIORÉ POUR NGINX
# ==============================================================================

[Definition]

ignoreregex = ^<HOST>.*(Googlebot|Bingbot|bingbot|Google-InspectionTool).*$

failregex = 
    ^<HOST>.*"(GET|POST|HEAD|PUT|DELETE|OPTIONS).*\.(env|git|sql|bak|zip|tar|config|old|swp)".*" \d+
    ^<HOST>.*"(GET|POST|HEAD).*\.php.*" \d+
    ^<HOST>.*" 404 
    ^<HOST>.*" 403 
    ^<HOST>.*" 400 
    ^<HOST>.*" 429 
    ^<HOST>.*"Bot blocked".*" 403
    ^<HOST>.*"(GET|POST).*/(admin|wp-admin|wp-login|phpmyadmin|adminer|console).*" \d+
    ^<HOST>.*"-".*" \d+
    ^<HOST>.*(sqlmap|nikto|nmap|masscan|zgrab|curl|wget|python-requests).*" \d+
EOF

# 4. Créer la configuration jail
echo "📝 Création de la jail..."
cat > /etc/fail2ban/jail.d/nginx-bad-bots.conf << 'EOF'
# ==============================================================================
# FAIL2BAN - JAIL POUR NGINX BAD BOTS
# ==============================================================================

[nginx-meta-abuse]
enabled  = true
port     = http,https
filter   = nginx-meta-abuse
logpath  = /var/log/nginx/odoo.access.log
maxretry = 10
findtime = 300
bantime  = 8640000
action   = iptables-multiport[name=nginx-meta, port="http,https", protocol=tcp]

[nginx-bad-bots]
enabled  = true
port     = http,https
filter   = nginx-bad-bots
logpath  = /var/log/nginx/odoo.access.log
maxretry = 3
findtime = 300
bantime  = 86400
action   = iptables-multiport[name=nginx-bad-bots, port="http,https", protocol=tcp]

[nginx-scanner]
enabled  = true
port     = http,https
filter   = nginx-scanner
logpath  = /var/log/nginx/odoo.access.log
maxretry = 20
findtime = 600
bantime  = 172800
action   = iptables-multiport[name=nginx-scanner, port="http,https", protocol=tcp]
EOF

echo ""
echo "✅ Fichiers créés avec succès"
echo ""
echo "🔍 Test des filtres..."

# Tester le filtre Meta
echo "Test nginx-meta-abuse:"
fail2ban-regex /var/log/nginx/odoo.access.log /etc/fail2ban/filter.d/nginx-meta-abuse.conf | tail -20

echo ""
echo "🔄 Redémarrage de fail2ban..."
systemctl restart fail2ban

sleep 3

echo ""
echo "📊 Statut de fail2ban:"
fail2ban-client status

echo ""
echo "✅ Installation terminée!"
echo ""
echo "📌 Vérifier les jails:"
echo "   fail2ban-client status nginx-meta-abuse"
echo "   fail2ban-client status nginx-bad-bots"
echo "   fail2ban-client status nginx-scanner"
