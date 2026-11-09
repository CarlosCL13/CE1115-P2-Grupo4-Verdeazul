"""
El unico que abre conexiones a la base. Los demas le piden a este.

transaccion() garantiza que la operacion y su evento de auditoria se guarden
juntos. Si se guarda uno y el otro no, queda un certificado sin rastro o un
rastro de algo que no existe.

    from app import bd

    with bd.transaccion() as cur:
        cur.execute("SELECT * FROM fincas WHERE id = %s", (finca_id,))
        fila = cur.fetchone()
        registrar(accion="FINCA_CONSULTADA", ...)   # misma transaccion

Los %s no son formato de Python: los sustituye el servidor. Nunca armes el SQL
concatenando lo que escribe el usuario (§2.3.5).
"""

import contextlib
import contextvars

import certifi
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app import config

# registrar() busca aqui el cursor en vez de recibirlo, porque el contrato 03
# congelo su firma sin cursor.
_cursor_actual: contextvars.ContextVar = contextvars.ContextVar("cursor")

# Eventos que deben sobrevivir a una reversion. El contrato 02 exige que toda
# denegacion quede anotada aunque la operacion se deshaga.
_eventos_a_salvo: contextvars.ContextVar = contextvars.ContextVar("salvados")

_principal: ConnectionPool | None = None
_bitacora: ConnectionPool | None = None


class SinTransaccion(RuntimeError):
    """
    Se uso algo que necesita estar dentro de transaccion().
    """


class Denegado(Exception):
    """
    La autorizacion dijo que no. Revierte la operacion, conserva el evento.
    """

    def __init__(self, decision) -> None:
        super().__init__(getattr(decision, "motivo", "denegado"))
        self.decision = decision


def _preparar(conexion: psycopg.Connection) -> None:
    """
    Prepara cada conexion nueva del grupo.

    El SET no puede ir en los parametros de arranque: el proxy de Neon rechaza
    statement_timeout ahi. Y hay que confirmar, o la conexion vuelve al grupo
    con una transaccion abierta y el grupo la descarta.
    """
    conexion.execute("SET statement_timeout = %d"
                     % config.TIEMPO_LIMITE_CONSULTA_MS)
    conexion.commit()


def _grupo(url: str) -> ConnectionPool:
    return ConnectionPool(
        conninfo=url,
        min_size=config.CONEXIONES_MIN,
        max_size=config.CONEXIONES_MAX,
        kwargs={
            # Windows no expone un almacen de autoridades que OpenSSL
            # encuentre solo, asi que sslrootcert=system no sirve ahi.
            # certifi funciona igual en Windows, en Linux y en el contenedor.
            "sslrootcert": certifi.where(),
            "row_factory": dict_row,
        },
        configure=_preparar,
        open=False,
    )


def arrancar() -> None:
    """
    Abre los grupos de conexiones. Lo llama main.py al levantar.

    Sin cadena de conexion no abre nada y deja que el servicio levante igual.
    Eso solo pasa en local: config.py ya revienta en la nube si falta. Llegar
    aqui sin cadena significa que alguien trabaja sobre las politicas sin base
    de datos, y /salud lo reporta como sin configurar.
    """
    global _principal, _bitacora
    if _principal is None and config.BD_URL is not None:
        _principal = _grupo(config.BD_URL.revelar())
        _principal.open(wait=True, timeout=15)
    if _bitacora is None and config.BITACORA_LECTURA_URL is not None:
        _bitacora = _grupo(config.BITACORA_LECTURA_URL.revelar())
        _bitacora.open(wait=True, timeout=15)


def cerrar() -> None:
    """
    Cierra los grupos. Lo llama main.py al apagar.
    """
    global _principal, _bitacora
    for grupo in (_principal, _bitacora):
        if grupo is not None:
            grupo.close()
    _principal = _bitacora = None


@contextlib.contextmanager
def transaccion():
    """
    Todo lo de adentro se confirma junto, o no queda nada.

    Si el bloque lanza cualquier excepcion, se revierte entero. Los eventos
    marcados con preservar() se reescriben aparte para que la reversion no se
    lleve el rastro.
    """
    if _principal is None:
        raise SinTransaccion(
            "No hay conexion a la base. Falta la cadena en el .env, o no "
            "se llamo a bd.arrancar().")

    salvados: list[dict] = []

    with _principal.connection() as conexion:
        conexion.autocommit = False
        with conexion.cursor() as cur:
            testigo_cursor = _cursor_actual.set(cur)
            testigo_salvados = _eventos_a_salvo.set(salvados)
            try:
                yield cur
            except BaseException:
                conexion.rollback()
                if salvados:
                    _escribir_aparte(salvados)
                raise
            else:
                conexion.commit()
            finally:
                _cursor_actual.reset(testigo_cursor)
                _eventos_a_salvo.reset(testigo_salvados)


def _escribir_aparte(filas: list[dict]) -> None:
    """
    Reescribe en su propia transaccion los eventos que no deben perderse.
    """
    with _principal.connection() as conexion:
        conexion.autocommit = True
        for fila in filas:
            columnas = ", ".join(fila)
            marcas = ", ".join(["%s"] * len(fila))
            conexion.execute(
                "INSERT INTO eventos_pendientes (%s) VALUES (%s)"
                % (columnas, marcas),
                tuple(fila.values()),
            )


def cursor_actual():
    """
    El cursor de la transaccion en curso. Lo usa registrar().
    """
    try:
        return _cursor_actual.get()
    except LookupError:
        raise SinTransaccion(
            "registrar() tiene que llamarse dentro de un bloque "
            "with bd.transaccion(), para que el evento y la operacion se "
            "guarden juntos.") from None


def preservar(fila: dict) -> None:
    """
    Marca un evento para que sobreviva si la transaccion se revierte.

    Lo llama registrar() cuando el resultado es DENEGADO. Las claves son
    columnas de eventos_pendientes.
    """
    try:
        _eventos_a_salvo.get().append(fila)
    except LookupError:
        raise SinTransaccion("preservar() fuera de una transaccion.") from None


@contextlib.contextmanager
def lectura_bitacora():
    """
    Solo lectura sobre la otra base, para las celdas L y X de O11.

    Va aparte porque es otra instancia y otro rol, log_reader. Escribir en la
    bitacora es del transmisor, no de la API.
    """
    if _bitacora is None:
        raise SinTransaccion(
            "No hay conexion a la base. Falta la cadena en el .env, o no "
            "se llamo a bd.arrancar().")
    with _bitacora.connection() as conexion:
        conexion.autocommit = True
        with conexion.cursor() as cur:
            yield cur


def esta_viva() -> bool:
    """
    Para /salud. No lanza: devuelve si la base contesta.
    """
    try:
        with transaccion() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() is not None
    except Exception:
        return False
