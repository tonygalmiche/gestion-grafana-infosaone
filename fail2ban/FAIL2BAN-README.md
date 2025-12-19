# Configuration Fail2ban Anti-Bots pour Nginx

## 📋 Fichiers créés

### 1. Configuration Jail (prisons)
**Fichier**: `fail2ban-jail-nginx-bad-bots.conf`
**Destination**: `/etc/fail2ban/jail.d/nginx-bad-bots.conf`

Contient 3 jails :
- **nginx-meta-abuse** : Bloque Meta/Facebook (ban 7 jours après 10 requêtes)
- **nginx-bad-bots** : Bloque les bots malveillants (ban 24h après 3 tentatives)
- **nginx-scanner** : Bloque les scanners (ban 48h après 20 URLs)

### 2. Filtres de détection

#### Filtre Meta/Facebook
**Fichier**: `fail2ban-filter-meta-abuse.conf`
**Destination**: `/etc/fail2ban/filter.d/nginx-meta-abuse.conf`

Détecte :
- User-agents : `meta-externalagent`, `facebookexternalagent`, etc.
- Plages IP Meta : 57.141.x.x, 69.63.x.x, etc.

#### Filtre Scanner
**Fichier**: `fail2ban-filter-scanner.conf`
**Destination**: `/etc/fail2ban/filter.d/nginx-scanner.conf`

Détecte :
- Requêtes multiples vers /blog avec tags
- Codes 302, 429 répétés

#### Filtre Bad Bots (existant)
**Fichier**: `fail2ban-nginx-bad-bots.conf`
**Destination**: `/etc/fail2ban/filter.d/nginx-bad-bots.conf`

Détecte :
- Accès fichiers sensibles (.env, .git, .sql)
- Scripts PHP (votre site n'est pas en PHP)
- Erreurs 404, 403, 400, 429
- User-agents suspects (sqlmap, nikto, curl, etc.)

## 🚀 Installation

### Méthode automatique (recommandée)

```bash
# Copier les fichiers vers le serveur
scp fail2ban-*.conf root@votre-serveur:/root/MesDocuments/gestion-grafana-infosaone/
scp installer-fail2ban-anti-bots.sh root@votre-serveur:/root/MesDocuments/gestion-grafana-infosaone/

# Sur le serveur, exécuter le script
sudo bash /root/MesDocuments/gestion-grafana-infosaone/installer-fail2ban-anti-bots.sh
```

### Méthode manuelle

```bash
# 1. Copier la jail
sudo cp fail2ban-jail-nginx-bad-bots.conf /etc/fail2ban/jail.d/nginx-bad-bots.conf

# 2. Copier les filtres
sudo cp fail2ban-filter-meta-abuse.conf /etc/fail2ban/filter.d/nginx-meta-abuse.conf
sudo cp fail2ban-filter-scanner.conf /etc/fail2ban/filter.d/nginx-scanner.conf
sudo cp fail2ban-nginx-bad-bots.conf /etc/fail2ban/filter.d/nginx-bad-bots.conf

# 3. Tester les filtres
sudo fail2ban-regex /var/log/nginx/odoo.access.log /etc/fail2ban/filter.d/nginx-meta-abuse.conf

# 4. Redémarrer fail2ban
sudo systemctl restart fail2ban

# 5. Vérifier le statut
sudo fail2ban-client status
```

## 📊 Surveillance

### Script de surveillance
```bash
# Rendre exécutable
chmod +x surveiller-fail2ban.sh

# Exécuter
sudo ./surveiller-fail2ban.sh
```

### Commandes utiles

```bash
# Statut général
sudo fail2ban-client status

# Statut d'une jail spécifique
sudo fail2ban-client status nginx-meta-abuse
sudo fail2ban-client status nginx-bad-bots
sudo fail2ban-client status nginx-scanner

# Voir les IPs bannies
sudo fail2ban-client status nginx-meta-abuse | grep "Banned IP list"

# Logs en temps réel
sudo tail -f /var/log/fail2ban.log

# Débannir une IP
sudo fail2ban-client set nginx-meta-abuse unbanip 57.141.0.15

# Bannir manuellement une IP
sudo fail2ban-client set nginx-meta-abuse banip 57.141.0.15
```

## 🎯 Résultats attendus

D'après votre analyse de logs, voici ce qui devrait être bloqué :

### Meta/Facebook (39192 requêtes)
- Toutes les IPs 57.141.0.x seront bannies pour 7 jours
- Exemple : 57.141.0.15 (636 req), 57.141.0.9 (619 req), etc.

### Bad Bots malveillants
- 176.65.149.253 (tentative .env)
- 4.197.248.250 (tentatives .php)
- 52.169.5.4 (tentatives wordpress)

### Scanners
- 207.46.13.102 (706 requêtes, 374 URLs)
- Autres IPs avec nombreuses URLs différentes

## ⚙️ Ajustements possibles

### Rendre le ban Meta permanent
Dans `fail2ban-jail-nginx-bad-bots.conf` :
```ini
[nginx-meta-abuse]
bantime  = -1  # Ban permanent
```

### Rendre le filtre Meta plus strict
Dans `fail2ban-filter-meta-abuse.conf` :
```ini
maxretry = 1  # Bannir dès la première requête
```

### Bloquer d'autres bots
Dans `fail2ban-filter-meta-abuse.conf`, ajouter :
```ini
failregex = ^<HOST>.*AmazonBot.*$
            ^<HOST>.*TikTokBot.*$
```

## 🔧 Dépannage

### Fail2ban ne démarre pas
```bash
# Vérifier la syntaxe
sudo fail2ban-client -t

# Voir les erreurs
sudo journalctl -u fail2ban -n 50
```

### Un filtre ne fonctionne pas
```bash
# Tester avec un vrai log
sudo fail2ban-regex /var/log/nginx/odoo.access.log /etc/fail2ban/filter.d/nginx-meta-abuse.conf

# Mode debug
sudo fail2ban-client -vvv start
```

### Débannir toutes les IPs Meta pour test
```bash
# Lister les IPs bannies
sudo fail2ban-client status nginx-meta-abuse

# Débannir
sudo fail2ban-client set nginx-meta-abuse unbanip 57.141.0.15
# (répéter pour chaque IP)

# Ou redémarrer la jail
sudo fail2ban-client reload nginx-meta-abuse
```

## 📈 Monitoring avec Grafana

Vous pouvez créer un dashboard Grafana pour visualiser :
- Nombre de bans par jour/heure
- Top IPs bannies
- Évolution du trafic Meta

Les données sont dans `/var/log/fail2ban.log`

## ⚠️ Important

1. **Google et Bing ne sont PAS bloqués** (importants pour le SEO)
2. **Meta/Facebook sera fortement limité** (7 jours de ban)
3. **Le trafic légitime n'est pas affecté**
4. **Les bans sont au niveau firewall** (iptables), très efficace

## 🆘 Support

En cas de problème :
1. Vérifier les logs : `/var/log/fail2ban.log`
2. Tester les regex avec `fail2ban-regex`
3. Vérifier les jails actives : `fail2ban-client status`
