#!/usr/bin/env bash
# Arma una base PostgreSQL DESECHABLE igual a verdeazul-app, para las pruebas
# de integracion de identidad. Nunca apuntar esto a Neon.
#
#   PGHOST=localhost PGPORT=5432 PGUSER=neondb_owner bash tests/identidad/preparar_bd.sh
#
# Necesita un PostgreSQL con PostGIS y autenticacion trust (la base es
# desechable y no lleva contrasenas: asi ninguna credencial entra al
# repositorio, ni siquiera una de prueba). En el CI es el contenedor
# postgis/postgis; en local, cualquiera con PostGIS instalado.
#
# Hace lo mismo que db/migrar.py roles + app, en el mismo orden y con los
# mismos roles, y anota cada archivo en migraciones_aplicadas para poder
# correrse dos veces sin repetir nada.

set -euo pipefail

RAIZ=$(cd "$(dirname "$0")/../.." && pwd)
export PGHOST="${PGHOST:-localhost}" PGPORT="${PGPORT:-5432}" PGUSER="${PGUSER:-neondb_owner}"

sql() { psql -X -q -v ON_ERROR_STOP=1 "$@"; }

if ! sql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'neondb'" | grep -q 1; then
  sql -d postgres -c "CREATE DATABASE neondb"
fi

sql -d neondb -c "CREATE TABLE IF NOT EXISTS migraciones_aplicadas (
    archivo text PRIMARY KEY, huella text NOT NULL,
    aplicada_en timestamptz NOT NULL DEFAULT now())"

ya_aplicada() {
  sql -d neondb -tAc "SELECT 1 FROM migraciones_aplicadas WHERE archivo = '$1'" | grep -q 1
}

anotar() {
  sql -U "$2" -d neondb -c "INSERT INTO migraciones_aplicadas (archivo, huella) VALUES ('$1', 'pruebas')"
}

if ! ya_aplicada roles/001_roles.sql; then
  sql -d neondb -1 -f "$RAIZ/db/roles/001_roles.sql"
  # Sin contrasena: la autenticacion de esta base es trust.
  sql -d neondb -c "ALTER ROLE app_migrate LOGIN" -c "ALTER ROLE app_rw LOGIN" \
                -c "ALTER ROLE outbox_rw LOGIN"
  anotar roles/001_roles.sql "$PGUSER"
  echo "  aplicada    roles/001_roles.sql"
fi

for archivo in "$RAIZ"/db/migrations/*.sql; do
  nombre="migrations/$(basename "$archivo")"
  if ya_aplicada "$nombre"; then
    echo "  ya estaba   $nombre"
    continue
  fi
  sql -U app_migrate -d neondb -1 -f "$archivo"
  anotar "$nombre" app_migrate
  echo "  aplicada    $nombre"
done
