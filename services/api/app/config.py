"""
Lee el entorno, lo valida y lo reparte. Nadie mas llama a os.getenv.

Falla al importarse, no en la primera peticion: si falta un secreto, el
contenedor no debe llegar a estar sano.

En local las variables salen del .env. En Cloud Run las inyecta Secret
Manager y no hay .env. El mismo codigo sirve en los dos lados.
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
# Cero a proposito: guardar una conexion abierta entre peticiones no sirve
# cuando el otro extremo se duerme. Neon suspende el computo a los cinco
# minutos y la mata, y la siguiente peticion se encuentra una conexion muerta.
CONEXIONES_MIN = _entero("CONEXIONES_MIN", 0)
CONEXIONES_MAX = _entero("CONEXIONES_MAX", 4)

# Cuanto puede quedarse una conexion sin usar antes de cerrarla nosotros.
# Por debajo de los cinco minutos de Neon, para que el cierre sea ordenado.
SEGUNDOS_SIN_USO = _entero("SEGUNDOS_SIN_USO", 120)


# --- Datos personales -------------------------------------------------------

# Llave del HMAC de datos_personales.cedula_busqueda. Vive fuera de la base: si
# estuviera dentro, un volcado entregaria las cedulas.
LLAVE_BUSQUEDA_CEDULA = _secreto("LLAVE_BUSQUEDA_CEDULA")

# Llave AES-256-GCM con la que se cifran cedula, telefono y el secreto TOTP
# antes de guardarlos (LG-05). Distinta de la del HMAC: una sirve para buscar
# y la otra para leer, y quien tenga solo la primera no puede descifrar nada.
LLAVE_CIFRADO_DATOS = _secreto("LLAVE_CIFRADO_DATOS")


# --- Certificados -----------------------------------------------------------

# Llave privada Ed25519 con la que se firman los certificados (2.3.6). Son 32
# bytes en base64 url, el mismo formato que LLAVE_CIFRADO_DATOS, y se leen
# igual: cualquier valor de 32 bytes al azar es una llave Ed25519 valida.
#
#   crudo = base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))
#   privada = Ed25519PrivateKey.from_private_bytes(crudo)
#
# En la nube sale de Secret Manager y no esta en ninguna maquina. En local
# sirve cualquier llave de prueba: la clave publica viaja dentro de cada
# certificado, asi que un certificado firmado en local se verifica igual.
LLAVE_FIRMA_CERTIFICADOS = _secreto("LLAVE_FIRMA_CERTIFICADOS")


# --- Sesiones y contrasenas -------------------------------------------------

# Tope absoluto de una sesion. SE-01 de P1 dice que ninguna dura mas de 12.
SESION_HORAS = _entero("SESION_HORAS", 8)
if not 1 <= SESION_HORAS <= 12:
    raise FaltaConfiguracion("SESION_HORAS tiene que estar entre 1 y 12 (SE-01)")

# Bloqueo tras intentos fallidos, RC-01 de P1: "tras 5 intentos fallidos la
# espera aumenta; tras 10, bloqueo de 30 minutos".
INTENTOS_ESPERA = _entero("INTENTOS_ESPERA", 5)
INTENTOS_BLOQUEO = _entero("INTENTOS_BLOQUEO", 10)
BLOQUEO_MINUTOS = _entero("BLOQUEO_MINUTOS", 30)

# Cuanto dura una reautenticacion antes de la accion grave que la pidio.
REAUTENTICACION_MINUTOS = _entero("REAUTENTICACION_MINUTOS", 5)

# CO-02: consultar si la contrasena nueva aparece en filtraciones conocidas
# (Have I Been Pwned, por k-anonimato: solo salen 5 caracteres del SHA-1). Se
# apaga en local y en las pruebas, que no deben depender de internet.
VERIFICAR_FILTRACIONES = _entero(
    "VERIFICAR_FILTRACIONES", 1 if ENTORNO == "nube" else 0) == 1

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
        "segundos_sin_uso": SEGUNDOS_SIN_USO,
        "base_configurada": BD_URL is not None,
        "sesion_horas": SESION_HORAS,
        "bloqueo": {"espera_desde": INTENTOS_ESPERA,
                    "bloqueo_desde": INTENTOS_BLOQUEO,
                    "minutos": BLOQUEO_MINUTOS},
        "argon2": ARGON2,
    }
