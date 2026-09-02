# Optimisation de `surveiller-disk-autonome.py`

## Constat

Exécution mesurée : **1m14s** pour un script qui ne devrait prendre que quelques secondes.

## Analyse

### Cause racine : absence d'index composite sur la table `system`

La table `system` (hypertable TimescaleDB, 38 chunks) ne possède que des index séparés :
```
idx_system_host   btree (host)
system_time_idx   btree (time DESC)
```
Aucun index composite `(host, time DESC)`.

La fonction `get_all_known_hosts()` du script exécute :
```sql
SELECT DISTINCT ON (host)
    host,
    time
FROM system
ORDER BY host, time DESC
```
sans limite de temps, afin de garder trace de tous les hosts connus (y compris ceux qui ne remontent plus de données).

- Sur les **37 chunks compressés** (anciens), TimescaleDB exploite un skip-scan sur les métadonnées de compression : ~2 ms par chunk, quasi gratuit.
- Sur le **chunk courant** (non compressé, celui qui reçoit les données en continu, ~5,4 millions de lignes) : aucun index ne permet de satisfaire `ORDER BY host, time DESC` → PostgreSQL fait un **Seq Scan complet** puis un **tri externe sur disque de 259 Mo**.

Mesuré en direct sur la base (`EXPLAIN ANALYZE`) : cette seule requête prend **14,4 s**, sur un total de 14,5 s pour les 3 requêtes du script.

### Effet d'amplification : contention entre exécutions

Le script tourne toutes les 15 minutes via cron (`*/15 4-22 * * *`), et `surveiller-temperature-autonome.py` toutes les 5 minutes. En rejouant les fonctions du script via l'API Grafana (au lieu d'un accès direct à la base), les mêmes requêtes deviennent beaucoup plus lentes et irrégulières :

| Requête | Direct psql | Via API Grafana (test) |
|---|---|---|
| `get_all_known_hosts()` | 14,4 s | 73,7 s |
| `get_load_averages()` (triviale) | 60 ms | 60 s |

Les logs Grafana (`journalctl -u grafana-server`) confirment des durées très irrégulières pour le plugin postgres (de 4 ms à 14,5 s) sur quelques minutes. Explication : chaque exécution de `get_all_known_hosts()` génère un tri disque de 259 Mo qui consomme CPU/IO. Quand plusieurs exécutions (cron toutes les 15 min, éventuellement en parallèle d'autres requêtes) se chevauchent, elles se mettent à attendre les unes derrière les autres côté PostgreSQL — une requête normalement anodine (60 ms) se retrouve alors à 60 s simplement parce qu'elle patiente derrière les scans/tris coûteux des autres.

### Points vérifiés et écartés

- Connexions DB : 43/100 utilisées au moment du test (pas de saturation).
- Pool Grafana : `maxOpenConns=100`, `maxIdleConns=100` — pas de goulot d'étranglement.
- Jobs de compression TimescaleDB : rapides (~20-35 ms), planifiés toutes les 12h — pas la cause directe.

## Ce qu'il faut faire

### 1. Ajouter un index composite (correctif principal)

⚠️ TimescaleDB **ne supporte pas** `CREATE INDEX CONCURRENTLY` directement sur une hypertable (erreur : `hypertables do not support concurrent index creation`). Deux façons de procéder :

**Option A — la plus simple, un court verrou en écriture** :
```sql
CREATE INDEX ON system (host, time DESC);
```
Sur les 38 chunks de `system`, seul le chunk courant (non compressé, ~5,4M lignes) n'a pas encore cet index — les 37 chunks compressés ne sont pas concernés par une construction lourde. La création prend donc probablement quelques secondes, pendant lesquelles les écritures de `telegraf` sur ce chunk seront bloquées (mises en attente, pas perdues). À lancer si possible en dehors d'un pic de charge.

**Option B — sans aucun verrou, en ciblant directement le chunk courant** :
```sql
-- 1. Identifier le chunk courant (non compressé) de system
SELECT show_chunks('system', older_than => now() - interval '1 day')::text
EXCEPT
SELECT show_chunks('system')::text;
-- ou plus simple : le dernier chunk listé par show_chunks('system') triée par nom/plage de temps

-- 2. Créer l'index en CONCURRENTLY directement sur ce chunk (c'est une table normale)
CREATE INDEX CONCURRENTLY ON _timescaledb_internal._hyper_14_XXX_chunk (host, time DESC);
```
Cette option évite tout verrou mais ne couvre que le chunk courant : quand TimescaleDB créera le prochain chunk (rotation), il n'aura pas l'index tant que l'option A n'aura pas été appliquée une fois sur l'hypertable (`CREATE INDEX ON system (...)`, qui elle-même se fera vite car les chunks compressés n'ont pas besoin de reconstruction et le nouveau chunk sera minuscule au moment de la rotation).

Effet attendu (les deux options) : le chunk courant pourra utiliser un skip-scan comme les chunks compressés, éliminant le Seq Scan + tri disque. `get_all_known_hosts()` devrait passer de ~14 s à quelques ms, ce qui casse aussi la boucle de contention entre exécutions successives du cron.

**Recommandation** : Option A (`CREATE INDEX ON system (host, time DESC);`), plus simple et suffisante — le blocage en écriture est bref (quelques secondes sur un seul chunk) et l'index sera automatiquement hérité par tous les futurs chunks.

### 2. (Optionnel) Même index sur `disk` si besoin

Si un usage similaire (tri par `host, time`) apparaît un jour sur la table `disk`, appliquer le même correctif :
```sql
CREATE INDEX CONCURRENTLY ON disk (host, time DESC);
```
Non nécessaire actuellement : la requête `get_disk_usage()` filtre déjà sur une fenêtre de 10 minutes et s'exécute en ~90 ms.

### 3. (Mineur) Dédupliquer les appels à `get_datasources()`

Le script appelle `get_datasources()` (requête HTTP vers l'API Grafana) 3 fois — une fois dans `get_all_known_hosts()`, une fois dans `get_disk_usage()`, une fois dans `get_load_averages()`. Récupérer `default_ds` une seule fois dans `main()` et le passer aux 3 fonctions évite des round-trips réseau superflus. Impact mineur comparé aux points 1 et 4, mais simple à faire.

### 4. Cause principale du temps restant (~1 minute) : connexions HTTPS "à froid" vers Grafana

Après l'ajout de l'index (point 1), la partie base de données est redevenue rapide (0,42 s), mais le script complet mettait toujours ~1 minute. Diagnostic :

- `grafana_utils.make_grafana_request()` ouvrait une **nouvelle connexion HTTPS à chaque appel** (`requests.get`/`requests.post` sans session), et le script fait **6 appels** au total (3× `get_datasources()` + 3× `query_timescale()`).
- Une connexion HTTPS neuve vers l'URL publique de Grafana a environ **1 chance sur 4 à 6 de rester bloquée ~60 secondes** avant d'aboutir — confirmé en testant en boucle, **y compris directement depuis le serveur Grafana lui-même**. Symptôme classique de hairpin NAT : le serveur résout son propre nom de domaine public vers sa propre IP publique, sort vers l'extérieur puis revient sur lui-même, et ce trajet échoue silencieusement par intermittence (perte du paquet SYN, attente du timeout TCP avant qu'une retransmission aboutisse).
- Avec 6 connexions neuves par exécution et ~1 risque sur 4-6 par connexion, il est statistiquement quasi certain qu'au moins une des 6 tombe dans ce trou de 60 s à chaque run — ce qui explique le 1m1s à 1m14s mesuré, indépendamment de la base de données.

**Corrigé dans `grafana_utils.py`** : `make_grafana_request()` utilise désormais une `requests.Session()` partagée (connexion garder-en-vie/keep-alive réutilisée), ce qui ramène le nombre de connexions "à risque" de 6 à 1 par exécution du script.

**À faire en complément, uniquement dans le `config.py` déployé sur le serveur Grafana lui-même** (pas dans celui d'un poste de dev distant) : remplacer l'URL publique de Grafana par son adresse locale, pour éviter complètement le hairpin NAT (Grafana écoute en local sur le port 3000, confirmé dans ses logs) :
```python
GRAFANA_URL = "http://127.0.0.1:3000"
```
Une connexion locale prend <1 ms, sans TLS, et ne peut pas subir ce problème réseau. Les scripts lancés depuis ailleurs (poste de dev) doivent en revanche continuer à utiliser l'URL publique habituelle.

## Statut

✅ **Index créé le 2026-09-02** sur le serveur Grafana :
```sql
CREATE INDEX ON system (host, time DESC);
```
Résultat vérifié (EXPLAIN ANALYZE) : le chunk courant utilise désormais un `SkipScan` + `Index Only Scan` au lieu du Seq Scan + tri disque de 259 Mo.

| | Avant | Après |
|---|---|---|
| Requête `get_all_known_hosts()` (direct DB) | 14,4 s | **0,42 s** |

✅ **`grafana_utils.py` corrigé** : ajout d'une `requests.Session()` partagée pour réutiliser les connexions HTTP entre les appels à l'API Grafana.

⏳ **À faire manuellement sur le serveur** : mettre `GRAFANA_URL = "http://127.0.0.1:3000"` dans le `config.py` déployé sur le serveur Grafana (voir point 4 ci-dessus). Pas encore appliqué.

Point 3 (dédoublonnage de `get_datasources()` dans le script) reste optionnel et n'a pas été appliqué.
