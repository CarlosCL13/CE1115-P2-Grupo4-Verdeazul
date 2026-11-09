"""
Lee el entorno, lo valida y lo reparte. Nadie mas llama a os.getenv.

Falla al importarse, no en la primera peticion: si falta un secreto, el
contenedor no debe llegar a estar sano.

En local las variables salen del .env. En Cloud Run las inyecta Secret
Manager y no hay .env. El mismo codigo sirve en los dos lados.
"""

import os
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[3]


class FaltaConfiguracion(RuntimeError):
    """
    Falta una variable, o tiene un valor que no sirve.
    """


class Secreto:
    """
    Un valor que no debe salir en registros ni en trazas de error.

    Imprimirlo no dice nada. Hay que pedirlo con revelar().
    """

    __slots__ = ("_valor",)

    def __init__(self, valor: str) -> None:
        self._valor = valor

    def revelar(self) -> str:
        return self._valor

    def __repr__(self) -> str:
        return "<secreto oculto>"

    __str__ = __repr__


def _cargar_env() -> None:
    """
    Lee el .env si existe. En Cloud Run no existe.
    """
    archivo = RAIZ / ".env"
    if not archivo.exists():
        return
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave, valor = clave.strip(), valor.strip().strip('"').strip("'")
        if valor and clave not in os.environ:
            os.environ[clave] = valor


def _texto(nombre: str, por_omision: str | None = None) -> str:
    """
    Una variable de texto. Sin valor por omision, es obligatoria.
    """
    valor = os.environ.get(nombre) or por_omision
    if valor is None:
        raise FaltaConfiguracion(
            "Falta %s. En local va en el .env (copialo de .env.example); en "
            "Cloud Run se inyecta desde Secret Manager." % nombre)
    return valor


def _entero(nombre: str, por_omision: int) -> int:
    """
    Una variable numerica, con valor por omision si no esta.
    """
    bruto = os.environ.get(nombre)
    if not bruto:
        return por_omision
    try:
        return int(bruto)
    except ValueError:
        raise FaltaConfiguracion("%s tiene que ser un numero, no %r"
                                 % (nombre, bruto)) from None


def _secreto(nombre: str) -> Secreto | None:
    """Un secreto: obligatorio en la nube, opcional en local.

    Un secreto ausente no puede llegar a produccion fingiendo que todo esta
    bien. Pero en local el ciclo de trabajo sobre las politicas levanta api y
    policies sin base de datos, y exigirlo ahi rompe ese ciclo.
    """
    valor = os.environ.get(nombre)
    if valor:
        return Secreto(valor)
    if ENTORNO == "nube":
        raise FaltaConfiguracion(
            "Falta %s. En Cloud Run se inyecta desde Secret Manager." % nombre)
    return None


def _conexion(nombre: str) -> Secreto | None:
    """Una cadena de conexion, que ademas tiene que exigir verify-full.

    Neon la da terminada en sslmode=require, que cifra pero no verifica contra
    quien se habla. Si alguien la pega tal cual, que se note ahora.
    """
    secreto = _secreto(nombre)
    if secreto is None:
        return None
    if "sslmode=verify-full" not in secreto.revelar():
        raise FaltaConfiguracion(
            "%s no pide verify-full. Cambia el final de la cadena por "
            "?sslmode=verify-full" % nombre)
    return secreto


_cargar_env()


# --- Identidad del servicio -------------------------------------------------

# La inyecta Cloud Run al desplegar.
VERSION = _texto("APP_VERSION", "dev")

# K_SERVICE la pone Cloud Run y nadie mas.
ENTORNO = "nube" if os.environ.get("K_SERVICE") else "local"


# --- Base de datos ----------------------------------------------------------
#
# Aqui no estan VERDEAZUL_OWNER_URL ni VERDEAZUL_MIGRATE_URL, a proposito: la
# aplicacion en ejecucion no debe poder alterar el esquema.

# app_rw: SELECT, INSERT, UPDATE. Sin DELETE.
BD_URL = _conexion("VERDEAZUL_DB_URL")

# log_reader: SELECT sobre eventos, para las celdas L y X de O11.
BITACORA_LECTURA_URL = _conexion("VERDEAZUL_BITACORA_LECTURA_URL")

# Corta una consulta colgada, que ademas mantiene despierto el computo de Neon.
TIEMPO_LIMITE_CONSULTA_MS = _entero("TIEMPO_LIMITE_CONSULTA_MS", 10_000)

# Pequeno a proposito: el plan Free de Neon no da conexiones infinitas y Cloud
# Run puede levantar varias instancias.
CONEXIONES_MIN = _entero("CONEXIONES_MIN", 1)
CONEXIONES_MAX = _entero("CONEXIONES_MAX", 4)


# --- Datos personales -------------------------------------------------------

# Llave del HMAC de datos_personales.cedula_busqueda. Vive fuera de la base: si
# estuviera dentro, un volcado entregaria las cedulas.
LLAVE_BUSQUEDA_CEDULA = _secreto("LLAVE_BUSQUEDA_CEDULA")


# --- Sesiones y contrasenas -------------------------------------------------

SESION_HORAS = _entero("SESION_HORAS", 8)

# Bloqueo tras intentos fallidos (§2.3.1).
INTENTOS_MAXIMOS = _entero("INTENTOS_MAXIMOS", 5)
BLOQUEO_MINUTOS = _entero("BLOQUEO_MINUTOS", 15)

# Fijados en la Parte 1. Bajarlos es una desviacion que hay que justificar.
ARGON2 = {
    "memoria_kib": _entero("ARGON2_MEMORIA_KIB", 19 * 1024),
    "iteraciones": _entero("ARGON2_ITERACIONES", 2),
    "hilos": _entero("ARGON2_HILOS", 1),
}


def resumen() -> dict:
    """
    Lo que se puede mostrar en /salud o en un registro. Sin secretos.
    """
    return {
        "version": VERSION,
        "entorno": ENTORNO,
        "tiempo_limite_consulta_ms": TIEMPO_LIMITE_CONSULTA_MS,
        "conexiones": "%d-%d" % (CONEXIONES_MIN, CONEXIONES_MAX),
        "base_configurada": BD_URL is not None,
        "sesion_horas": SESION_HORAS,
        "argon2": ARGON2,
    }
