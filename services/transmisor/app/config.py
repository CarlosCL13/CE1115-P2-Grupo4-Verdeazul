"""
Lee el entorno del transmisor, lo valida y lo reparte.

Igual que el config.py del backend: falla al importarse si falta algo en la
nube, para que Cloud Run no deje sirviendo una revision a medias. En local las
variables salen del .env de la raiz del repositorio.

El transmisor usa tres cosas y ninguna mas: outbox_rw en la base principal,
log_writer en la bitacora y la llave del HMAC de la cadena. No tiene app_rw:
no puede tocar fincas, cuentas ni certificados.
"""

import os
import pathlib

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
    Lee el .env si lo encuentra subiendo desde este archivo.

    Se busca hacia arriba en vez de contar carpetas porque la profundidad no
    es la misma en los dos lados: en el repo este archivo vive en
    services/api/app/ y en el contenedor en /app/app/.

    Si no aparece, no pasa nada: en el contenedor las variables las pasa
    docker compose, y en Cloud Run las inyecta Secret Manager.
    """
    archivo = None
    for carpeta in pathlib.Path(__file__).resolve().parents:
        if (carpeta / ".env").is_file():
            archivo = carpeta / ".env"
            break
    if archivo is None:
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
    bien. En local se deja levantar sin el, para poder probar una tarea sin
    tener todas las cadenas; la tarea que lo necesite falla al usarlo.
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

VERSION = _texto("APP_VERSION", "dev")

# K_SERVICE la pone Cloud Run y nadie mas.
ENTORNO = "nube" if os.environ.get("K_SERVICE") else "local"


# --- Bases de datos ---------------------------------------------------------

# outbox_rw en verdeazul-app. Lee eventos_pendientes y solo puede cambiar
# enviado_en y eslabon (migraciones 010 y 012). Nada mas de esa base.
BANDEJA_URL = _conexion("VERDEAZUL_OUTBOX_URL")

# log_writer en verdeazul-bitacora. INSERT sobre eventos y nada mas: ni lee
# ni modifica. El eslabon anterior lo saca de la bandeja, no de aqui.
BITACORA_URL = _conexion("VERDEAZUL_BITACORA_URL")

TIEMPO_LIMITE_CONSULTA_MS = _entero("TIEMPO_LIMITE_CONSULTA_MS", 30_000)


# --- La cadena --------------------------------------------------------------

# Llave del HMAC con que se calcula cada eslabon. 32 bytes en base64 url, como
# las demas llaves. Vive solo aqui: ni la API ni la base la tienen, y por eso
# quien comprometa la base no puede rehacer la cadena (D-03).
LLAVE_CADENA = _secreto("LLAVE_CADENA_BITACORA")

# Tope de eventos por corrida. Una corrida acotada termina siempre, y la
# siguiente sigue donde quedo esta: nada de bucles hasta vaciar (§3.1).
EVENTOS_POR_CORRIDA = _entero("EVENTOS_POR_CORRIDA", 500)


def resumen() -> dict:
    """Lo que se puede mostrar en /salud o en un registro. Sin secretos."""
    return {
        "version": VERSION,
        "entorno": ENTORNO,
        "bandeja_configurada": BANDEJA_URL is not None,
        "bitacora_configurada": BITACORA_URL is not None,
        "llave_cadena_configurada": LLAVE_CADENA is not None,
        "eventos_por_corrida": EVENTOS_POR_CORRIDA,
    }
