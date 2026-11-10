"""Da contrasena (y segundo factor) a las cuentas de prueba de db/semilla.sql.

    python db/credenciales_prueba.py                 todas las de la semilla
    python db/credenciales_prueba.py dg pa           solo esas
    python db/credenciales_prueba.py --sin-totp      sin activar el segundo
                                                     factor: cada quien lo
                                                     activa al entrar, con QR

El enunciado pide "credenciales de prueba para cada rol" (§5, entregable 1).
La semilla crea las once cuentas pero deja vacia la tabla credenciales,
porque el hash Argon2id es de este frente.

Las contrasenas se GENERAN aqui, al azar, y se imprimen una sola vez en la
terminal. No estan en ningun archivo del repositorio, ni deben estarlo: §7.1
quita los 12 puntos de secretos por una credencial versionada, y una de
prueba sigue siendo una credencial que abre el sistema desplegado. Guardelas
en el gestor de contrasenas del grupo y paselas al profesor por un canal
privado.

Tambien registra los datos personales (cifrados) de los dos duenos de finca,
con cedulas inventadas.

Corre como app_rw, con la VERDEAZUL_DB_URL del .env. Usa las mismas llaves que
el backend desplegado: LLAVE_CIFRADO_DATOS y LLAVE_BUSQUEDA_CEDULA del .env
tienen que ser IGUALES a las de Secret Manager, o el sistema en la nube no va
a poder descifrar lo que este script guarde.
"""

import pathlib
import secrets
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "services" / "api"))

from app import bd, config  # noqa: E402
from app.auth import contrasenas, totp  # noqa: E402
from app.bitacora import registrar  # noqa: E402
from app.personas import cedula as ced  # noqa: E402

SEMILLA = ("dg", "dc", "pa", "tc1", "tc2", "vf1", "vf2", "ae", "df1", "df2", "ta")

# Cedulas inventadas, con el formato real. No son de nadie.
DUENOS = {
    "df1": ("Delia Fallas Mora", "1-0901-0234", "+506 8800-0001"),
    "df2": ("Daniel Fuentes Rojas", "1-0902-0567", "+506 8800-0002"),
}


def clave_nueva(usuario: str, nombre: str) -> str:
    while True:
        clave = secrets.token_urlsafe(18)
        if not contrasenas.problemas(clave, usuario, nombre):
            return clave


def main(argumentos: list[str]) -> None:
    sin_totp = "--sin-totp" in argumentos
    pedidos = [a for a in argumentos if not a.startswith("--")] or list(SEMILLA)

    if config.BD_URL is None:
        sys.exit("Falta VERDEAZUL_DB_URL en el .env.")
    if config.LLAVE_CIFRADO_DATOS is None or config.LLAVE_BUSQUEDA_CEDULA is None:
        sys.exit("Faltan LLAVE_CIFRADO_DATOS o LLAVE_BUSQUEDA_CEDULA en el .env.")

    bd.arrancar()
    filas = []
    try:
        with bd.transaccion() as cur:
            cur.execute("SELECT id, usuario, nombre, rol::text AS rol "
                        "FROM cuentas WHERE usuario = ANY(%s) ORDER BY id",
                        (pedidos,))
            cuentas = cur.fetchall()
            faltan = set(pedidos) - {c["usuario"] for c in cuentas}
            if faltan:
                sys.exit("No existen en la base: %s. Corre primero "
                         "python db/migrar.py semilla" % ", ".join(sorted(faltan)))

            for c in cuentas:
                clave = clave_nueva(c["usuario"], c["nombre"])
                secreto = None
                if not sin_totp and c["rol"] in totp.ROLES_OBLIGADOS:
                    secreto = totp.nuevo_secreto()
                cur.execute(
                    "INSERT INTO credenciales (cuenta, hash_argon2, totp_secreto, "
                    "  totp_activo, debe_cambiar) VALUES (%s, %s, %s, %s, false) "
                    "ON CONFLICT (cuenta) DO UPDATE SET "
                    "  hash_argon2 = EXCLUDED.hash_argon2, "
                    "  totp_secreto = EXCLUDED.totp_secreto, "
                    "  totp_activo = EXCLUDED.totp_activo, "
                    "  totp_ultimo_paso = NULL, codigos_recuperacion = '{}', "
                    "  debe_cambiar = false, cambiada_en = now()",
                    (c["id"], contrasenas.hashear(clave),
                     totp.cifrar_secreto(secreto, c["id"]) if secreto else None,
                     secreto is not None))
                cur.execute("UPDATE cuentas SET intentos_fallidos = 0, "
                            "bloqueada_hasta = NULL WHERE id = %s", (c["id"],))
                registrar(accion="CREDENCIAL_DE_PRUEBA_CARGADA",
                          sujeto="SISTEMA", objeto="O10:%d" % c["id"],
                          resultado="PERMITIDO",
                          detalle={"segundo_factor": secreto is not None})
                filas.append((c, clave, secreto))

                if c["usuario"] in DUENOS:
                    nombre, cedula, telefono = DUENOS[c["usuario"]]
                    normal = ced.normalizar(cedula)
                    cur.execute(
                        "INSERT INTO datos_personales (cuenta, nombre_completo, "
                        " cedula_cifrada, cedula_busqueda, telefono_cifrado) "
                        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (cuenta) DO NOTHING",
                        (c["id"], nombre, ced.cifrar_cedula(normal, c["id"]),
                         ced.huella_busqueda(normal),
                         ced.cifrar_telefono(ced.normalizar_telefono(telefono),
                                             c["id"])))
    finally:
        bd.cerrar()

    print()
    print("  Credenciales de prueba. Se muestran UNA vez: guardalas en el gestor")
    print("  de contrasenas del grupo. Nunca en un archivo del repositorio.")
    print()
    for c, clave, secreto in filas:
        print("  %-5s %-24s %s" % (c["usuario"], c["rol"], clave))
        if secreto:
            print("        TOTP: %s" % totp.uri(secreto, c["usuario"]))
    print()
    if any(s for _, _, s in filas):
        print("  Las lineas otpauth:// se pegan en la aplicacion autenticadora")
        print("  (o se convierten en QR) para generar los codigos de esas cuentas.")
        print()


if __name__ == "__main__":
    main(sys.argv[1:])
