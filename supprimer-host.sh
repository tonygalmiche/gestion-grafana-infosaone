#!/bin/bash
# Supprime d'un host toutes ses données dans timescaledb2 (toutes les tables du schéma public qui ont
# une colonne host), par exemple pour un ancien serveur qui n'existe plus et qui reste affiché dans
# Grafana.
#
# À lancer en root sur le serveur Grafana (grafana12) :
#   ./supprimer-host.sh <host>          affiche le nombre de lignes par table, puis demande confirmation
#   ./supprimer-host.sh <host> --oui    supprime sans demander confirmation
#
# Le nom du host doit être exact (colonne host des tables, ex. "vm-passerelle-proxmox").

BASE="timescaledb2"

if [ -z "$1" ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
fi
HOST="$1"
CONFIRME="$2"

# psql en tant que postgres, avec le host passé en variable (:'host') pour éviter toute injection
psql_base() {
    (cd /tmp && runuser -u postgres -- psql -d "$BASE" -X -At -v ON_ERROR_STOP=1 -v host="$HOST" "$@")
}

# Tables du schéma public qui ont une colonne host
TABLES=$(psql_base <<'SQL'
SELECT c.table_name
FROM information_schema.columns c
JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
WHERE c.table_schema = 'public' AND c.column_name = 'host' AND t.table_type = 'BASE TABLE'
ORDER BY 1;
SQL
) || { echo "Erreur : impossible de lire la liste des tables de $BASE"; exit 1; }

# Nombre de lignes du host par table
echo "Lignes du host '$HOST' dans $BASE :"
TOTAL=0
A_SUPPRIMER=()
for TABLE in $TABLES; do
    NB=$(psql_base <<SQL
SELECT count(*) FROM public."$TABLE" WHERE host = :'host';
SQL
    ) || { echo "Erreur de lecture sur la table $TABLE"; exit 1; }
    if [ "$NB" -gt 0 ]; then
        printf "  %-20s %12s\n" "$TABLE" "$NB"
        TOTAL=$((TOTAL + NB))
        A_SUPPRIMER+=("$TABLE")
    fi
done

if [ "$TOTAL" -eq 0 ]; then
    echo "  aucune ligne : rien à supprimer (vérifier l'orthographe exacte du host)"
    exit 0
fi
printf "  %-20s %12s\n" "TOTAL" "$TOTAL"

if [ "$CONFIRME" != "--oui" ]; then
    read -r -p "Supprimer ces $TOTAL lignes du host '$HOST' ? (oui/non) " REPONSE
    [ "$REPONSE" = "oui" ] || { echo "Abandon, rien n'a été supprimé."; exit 0; }
fi

# Suppression table par table
for TABLE in "${A_SUPPRIMER[@]}"; do
    RESULTAT=$(psql_base <<SQL
DELETE FROM public."$TABLE" WHERE host = :'host';
SQL
    ) || { echo "Erreur lors de la suppression dans $TABLE (tables suivantes non traitées)"; exit 1; }
    printf "  %-20s %s\n" "$TABLE" "$RESULTAT"
done
echo "Host '$HOST' supprimé de $BASE."
