"""
Las dos conexiones del transmisor. Ninguna otra parte del transmisor abre
conexiones.

    from app import bd

    with bd.bandeja() as cur:       # outbox_rw en verdeazul-app
        cur.execute("SELECT ... FROM eventos_pendientes WHERE ...")

    with bd.bitacora() as cur:      # log_writer en verdeazul-bitacora
        cur.execute("INSERT INTO eventos (...) VALUES (%s, ...)", (...))

Cada bloque es una transaccion: se confirma si termina bien y se revierte si
algo lanza. Son dos bases distintas, asi que ninguna transaccion cubre las dos
a la vez: ver el README del transmisor, "Como deberia funcionar transmitir".

No hay grupo de conexiones. El transmisor corre cada media hora o mas, y una
conexion guardada entre corridas estaria muerta: Neon suspende el computo a
los cinco minutos. Se abre, se trabaja y se cierra.
"""

import contextlib

import certifi
import psycopg
from psycopg.rows import dict_row

from app import config


class SinConexion(RuntimeError):
    """Falta la cadena de conexion. En local va en el .env."""


@contextlib.contextmanager
def _transaccion(secreto, variable: str):
    if secreto is None:
        raise SinConexion("Falta %s en el .env." % variable)
    with psycopg.connect(secreto.revelar(), sslrootcert=certifi.where(),
                         row_factory=dict_row) as conexion:
        # Neon no acepta statement_timeout en los parametros de arranque.
        conexion.execute("SET statement_timeout = %d"
                         % config.TIEMPO_LIMITE_CONSULTA_MS)
        with conexion.cursor() as cur:
            yield cur


def bandeja():
    """outbox_rw sobre verdeazul-app. Solo ve eventos_pendientes."""
    return _transaccion(config.BANDEJA_URL, "VERDEAZUL_OUTBOX_URL")


def bitacora():
    """log_writer sobre verdeazul-bitacora. Solo puede insertar en eventos."""
    return _transaccion(config.BITACORA_URL, "VERDEAZUL_BITACORA_URL")
