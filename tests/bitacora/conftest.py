"""Comun a las pruebas de O11 bitacora.

Son de integracion, como las de certificacion: una base principal desechable,
una segunda base desechable igual a verdeazul-bitacora y un OPA real. Se
saltan si falta alguna de las dos bases.

    bash tests/identidad/preparar_bd.sh
    bash tests/bitacora/preparar_bitacora.sh
    opa run --server --addr=127.0.0.1:8181 services/policies/rego &
    VERDEAZUL_PRUEBAS_BD="postgresql://app_rw@localhost:5432/neondb" \
    VERDEAZUL_PRUEBAS_BITACORA="postgresql://log_reader@localhost:5432/bitacora_pruebas" \
    VERDEAZUL_PRUEBAS_BITACORA_DUENO="postgresql://neondb_owner@localhost:5432/bitacora_pruebas" \
        pytest tests/bitacora -v

La API lee la bitacora con log_reader, igual que en Neon. Los eventos de
prueba los mete el dueno de esa base, que es el unico que puede ademas de
log_writer; asi no hace falta correr el transmisor.

Ninguna de las dos bases es NUNCA Neon.
"""

import datetime
import importlib.util
import json
import os
import pathlib
import uuid

import pytest

from app import bd

# Las fixtures de certificacion (cuentas, ventanas, entrar) sirven tal cual.
# Se cargan del archivo porque dos conftest no se importan entre si.
_ruta = pathlib.Path(__file__).parents[1] / "certificacion" / "conftest.py"
_especificacion = importlib.util.spec_from_file_location(
    "conftest_certificacion", _ruta)
_certificacion = importlib.util.module_from_spec(_especificacion)
_especificacion.loader.exec_module(_certificacion)

llaves_de_prueba = _certificacion.llaves_de_prueba
grupo = _certificacion.grupo
fabrica = _certificacion.fabrica
entrar = _certificacion.entrar

URL_LECTURA = os.environ.get("VERDEAZUL_PRUEBAS_BITACORA")
URL_DUENO = os.environ.get("VERDEAZUL_PRUEBAS_BITACORA_DUENO")


@pytest.fixture(scope="session")
def grupo_bitacora():
    """log_reader sobre la bitacora de pruebas, como bd._bitacora en Neon."""
    if not (URL_LECTURA and URL_DUENO):
        pytest.skip("sin VERDEAZUL_PRUEBAS_BITACORA: pruebas de O11 saltadas")

    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(URL_LECTURA, min_size=1, max_size=2,
                          kwargs={"row_factory": dict_row}, open=True)
    yield pool
    pool.close()


@pytest.fixture
def api(grupo, grupo_bitacora, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(bd, "_principal", grupo)
    monkeypatch.setattr(bd, "_bitacora", grupo_bitacora)
    monkeypatch.setattr(bd, "arrancar", lambda: None)
    monkeypatch.setattr(bd, "cerrar", lambda: None)
    with TestClient(app) as cliente:
        yield cliente


class Bitacora:
    """Mete eventos en la bitacora de pruebas, como el dueno de esa base."""

    def evento(self, *, accion, sujeto="1", objeto="O3:1",
               resultado="PERMITIDO", motivo=None, detalle=None,
               momento=None):
        import psycopg

        with psycopg.connect(URL_DUENO) as con:
            con.execute(
                "INSERT INTO eventos (id, momento, accion, sujeto, objeto, "
                "resultado, motivo, detalle, eslabon) "
                "VALUES (%s, coalesce(%s, now()), %s, %s, %s, %s, %s, %s, %s)",
                (uuid.uuid4(), momento, accion, sujeto, objeto, resultado,
                 motivo, json.dumps(detalle) if detalle else None,
                 uuid.uuid4().hex * 2))

    @staticmethod
    def accion_unica() -> str:
        """Una accion que solo usa esta prueba, para filtrar sin ruido."""
        return "PRUEBA_" + uuid.uuid4().hex[:10].upper()


@pytest.fixture
def bitacora(grupo_bitacora):
    return Bitacora()


@pytest.fixture
def hoy():
    return datetime.datetime.now(datetime.timezone.utc).date()
