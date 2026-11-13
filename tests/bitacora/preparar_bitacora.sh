#!/usr/bin/env bash
# Arma una base PostgreSQL DESECHABLE igual a verdeazul-bitacora, para las
# pruebas de O11. Nunca apuntar esto a Neon.
#
#   bash tests/identidad/preparar_bd.sh          # primero la base principal
#   bash tests/bitacora/preparar_bitacora.sh     # despues esta
#
# Va en el mismo servidor que la base principal de pruebas, pero en otra base
# (bitacora_pruebas), igual que en Neon son dos proyectos. Aplica el mismo
# db/bitacora/001_bitacora.sql y deja entrar a log_reader y log_writer sin
# contrasena, porque la autenticacion de esta base es trust.

set -euo pipefail

RAIZ=$(cd "$(dirname "$0")/../.." && pwd)
export PGHOST="${PGHOST:-localhost}" PGPORT="${PGPORT:-5432}" PGUSER="${PGUSER:-neondb_owner}"

sql() { psql -X -q -v ON_ERROR_STOP=1 "$@"; }

if ! sql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'bitacora_pruebas'" | grep -q 1; then
  sql -d postgres -c "CREATE DATABASE bitacora_pruebas"
fi

if ! sql -d bitacora_pruebas -tAc "SELECT 1 FROM pg_tables WHERE tablename = 'eventos'" | grep -q 1; then
  # 001 nombra la base neondb en sus GRANT, que en Neon es como se llama.
  # Aqui esa base es la principal de pruebas, que ya existe; el permiso de
  # conectarse a esta se da abajo.
  sql -d bitacora_pruebas -1 -f "$RAIZ/db/bitacora/001_bitacora.sql"
  echo "  aplicada    bitacora/001_bitacora.sql"
else
  echo "  ya estaba   bitacora/001_bitacora.sql"
fi

sql -d bitacora_pruebas \
    -c "REVOKE ALL ON DATABASE bitacora_pruebas FROM PUBLIC" \
    -c "GRANT CONNECT ON DATABASE bitacora_pruebas TO log_reader, log_writer" \
    -c "ALTER ROLE log_reader LOGIN" \
    -c "ALTER ROLE log_writer LOGIN"
