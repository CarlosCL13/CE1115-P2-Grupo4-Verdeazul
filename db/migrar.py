"""Aplica las migraciones SQL en orden y anota cual se aplico.

    python db/migrar.py roles       crea roles y permisos   (como dueno)
    python db/migrar.py claves      pone las contrasenas    (como dueno)
    python db/migrar.py app         esquema principal       (como app_migrate)
    python db/migrar.py bitacora    esquema de bitacora     (como dueno)
    python db/migrar.py estado      que esta aplicado y que falta

Sin Alembic porque no hay ORM: sin modelos de SQLAlchemy cada migracion seria
un op.execute() con el mismo SQL crudo, mas una dependencia. Y lo propio de
este esquema (geometry, indices GiST, GRANT por columna, CREATE ROLE) no lo
expresa ningun ORM. El .sql legible es ademas la evidencia que pide §5.2.

Ninguna credencial aparece aqui ni en los .sql. Todo sale del .env, que esta
en .gitignore. En Cloud Run las mismas variables las inyecta Secret Manager.
"""

import hashlib
import os
import pathlib
import sys

import certifi
import psycopg
from psycopg import sql

RAIZ = pathlib.Path(__file__).resolve().parent

# destino -> (carpeta, variable de entorno con la cadena de conexion)
DESTINOS = {
    "roles":    ("roles",      "VERDEAZUL_OWNER_URL"),
    "app":      ("migrations", "VERDEAZUL_MIGRATE_URL"),
    "bitacora": ("bitacora",   "VERDEAZUL_BITACORA_OWNER_URL"),
}

# rol -> (variable con su contrasena, en que proyecto vive)
#
# Los roles de bitacora los crea db/bitacora/001_bitacora.sql, asi que hay que
# correr  migrar.py bitacora  antes que  migrar.py claves.
CLAVES = {
    "app_migrate": ("CLAVE_APP_MIGRATE", "VERDEAZUL_OWNER_URL"),
    "app_rw":      ("CLAVE_APP_RW",      "VERDEAZUL_OWNER_URL"),
    "outbox_rw":   ("CLAVE_OUTBOX_RW",   "VERDEAZUL_OWNER_URL"),
    "log_writer":  ("CLAVE_LOG_WRITER",  "VERDEAZUL_BITACORA_OWNER_URL"),
    "log_reader":  ("CLAVE_LOG_READER",  "VERDEAZUL_BITACORA_OWNER_URL"),
}

TABLA = """
CREATE TABLE IF NOT EXISTS migraciones_aplicadas (
    archivo     text        PRIMARY KEY,
    huella      text        NOT NULL,
    aplicada_en timestamptz NOT NULL DEFAULT now()
)
"""


def cargar_env():
    """Lee el .env. No pisa lo que ya venga del entorno."""
    archivo = RAIZ.parent / ".env"
    if not archivo.exists():
        salir("No existe .env. Copialo de .env.example y llenalo.")
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave, valor = clave.strip(), valor.strip().strip('"').strip("'")
        if valor and clave not in os.environ:
            os.environ[clave] = valor


def url(variable):
    """Devuelve la cadena, quitando el sslrootcert que traiga.

    Esa ruta la pone conectar(): depende de la maquina. En el .env queda solo
    la politica, sslmode=verify-full.
    """
    valor = os.environ.get(variable)
    if not valor:
        salir("Falta %s en el .env." % variable)

    base, _, consulta = valor.partition("?")
    partes = [p for p in consulta.split("&")
              if p and not p.startswith("sslrootcert=")]
    if not any(p.startswith("sslmode=") for p in partes):
        salir("%s no trae sslmode. La Parte 1 prometio verify-full:\n"
              "  ...?sslmode=verify-full" % variable)
    return base + ("?" + "&".join(partes) if partes else "")


def conectar(variable, autocommit=False):
    """Abre la conexion diciendole a libpq con que certificados verificar.

    psycopg[binary] trae libpq 14, y sslrootcert=system aparecio en la 16: las
    anteriores lo toman como nombre de archivo y fallan. En Windows tampoco
    hay un almacen que OpenSSL encuentre solo.

    certifi trae las autoridades de Mozilla, incluida la que firma los
    certificados de Neon, y sirve igual en Windows, en Linux y en el
    contenedor. Asi verify-full funciona sin tener que bajar a require.
    """
    return psycopg.connect(url(variable),
                           autocommit=autocommit,
                           sslrootcert=certifi.where())


def salir(mensaje):
    print("\n  " + mensaje + "\n", file=sys.stderr)
    sys.exit(1)


def huella(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def aplicar(destino):
    carpeta, variable = DESTINOS[destino]
    ruta = RAIZ / carpeta
    archivos = sorted(p for p in ruta.glob("*.sql"))
    if not archivos:
        print("No hay .sql en db/%s todavia." % carpeta)
        return

    with conectar(variable, autocommit=False) as con:
        with con.cursor() as cur:
            cur.execute(TABLA)
        con.commit()

        with con.cursor() as cur:
            cur.execute("SELECT archivo, huella FROM migraciones_aplicadas")
            ya = dict(cur.fetchall())

        for archivo in archivos:
            nombre = "%s/%s" % (carpeta, archivo.name)
            texto = archivo.read_text(encoding="utf-8")
            h = huella(texto)

            if nombre in ya:
                if ya[nombre] != h:
                    # La regla del contrato dice que un archivo aplicado no se
                    # edita nunca. Esto la hace cumplir en vez de confiar.
                    salir("%s cambio despues de haberse aplicado.\n"
                          "  Un archivo ya aplicado no se edita: escribi el "
                          "siguiente." % nombre)
                print("  ya estaba   %s" % nombre)
                continue

            try:
                with con.cursor() as cur:
                    cur.execute(texto)
                    cur.execute(
                        "INSERT INTO migraciones_aplicadas (archivo, huella) "
                        "VALUES (%s, %s)", (nombre, h))
                con.commit()
                print("  aplicada    %s" % nombre)
            except Exception as e:
                con.rollback()
                salir("Fallo %s, no se aplico nada de ese archivo:\n  %s"
                      % (nombre, e))


def poner_claves():
    """ALTER ROLE compuesto en memoria. Nunca toca el disco.

    Unico lugar donde una contrasena entra en una sentencia SQL. Va con
    psycopg.sql.Literal, que la cita bien: concatenar con f-strings abriria
    una inyeccion en el paso mas sensible.
    """
    faltan = [v for v, _ in CLAVES.values() if not os.environ.get(v)]
    if faltan:
        salir("Faltan contrasenas en el .env: %s\n"
              "  Generalas con:\n"
              '  python -c "import secrets; [print(secrets.token_urlsafe(24)) '
              'for _ in range(%d)]"' % (", ".join(faltan), len(faltan)))

    faltantes = []
    for rol, (var_clave, var_url) in CLAVES.items():
        clave = os.environ[var_clave]
        if len(clave) < 16:
            salir("La contrasena de %s es demasiado corta." % rol)
        with conectar(var_url, autocommit=True) as con:
            existe = con.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (rol,)).fetchone()
            if not existe:
                # Los roles los crea su .sql, no este subcomando. Si falta, es
                # que esa migracion todavia no se aplico.
                faltantes.append(rol)
                print("  %-12s todavia no existe" % rol)
                continue
            con.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(rol), sql.Literal(clave)))
        print("  %-12s con login" % rol)

    if faltantes:
        salir("Faltan por crear: %s\n"
              "  Corré primero las migraciones que los crean:\n"
              "    python db/migrar.py roles      (app_rw, app_migrate, "
              "outbox_rw)\n"
              "    python db/migrar.py bitacora   (log_writer, log_reader)\n"
              "  y despues volvé a correr claves." % ", ".join(faltantes))

    print("\n  Listo. Ahora armá en el .env las cadenas de cada rol,")
    print("  cambiando usuario y contrasena sobre la que da Neon.")
    print("  Ojo: log_writer y log_reader usan el host de verdeazul-bitacora,")
    print("  que es distinto al de verdeazul-app.")


def estado():
    for destino, (carpeta, variable) in DESTINOS.items():
        print("\n%s  (db/%s)" % (destino, carpeta))
        if not os.environ.get(variable):
            print("  sin %s en el .env" % variable)
            continue
        archivos = sorted(p.name for p in (RAIZ / carpeta).glob("*.sql"))
        try:
            with conectar(variable) as con:
                with con.cursor() as cur:
                    cur.execute("SELECT to_regclass('migraciones_aplicadas')")
                    if cur.fetchone()[0] is None:
                        ya = {}
                    else:
                        cur.execute("SELECT archivo, aplicada_en "
                                    "FROM migraciones_aplicadas")
                        ya = dict(cur.fetchall())
        except Exception as e:
            print("  no se pudo conectar: %s" % e)
            continue
        for nombre in archivos:
            clave = "%s/%s" % (carpeta, nombre)
            cuando = ya.get(clave)
            print("  %-40s %s" % (
                nombre,
                cuando.strftime("%Y-%m-%d %H:%M") if cuando else "pendiente"))
        if not archivos:
            print("  (sin archivos)")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    orden = sys.argv[1]
    cargar_env()

    if orden == "claves":
        poner_claves()
    elif orden == "estado":
        estado()
    elif orden in DESTINOS:
        aplicar(orden)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
