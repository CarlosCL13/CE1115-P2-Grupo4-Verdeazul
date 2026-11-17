"""Comun a las pruebas de O5 certificados.

test_firma.py es unitaria: no necesita base ni motor y corre siempre.
test_certificados.py es de integracion, con la misma base desechable y el
mismo OPA real que certificacion. Se salta si no hay base.

    bash tests/identidad/preparar_bd.sh
    opa run --server --addr=127.0.0.1:8181 services/policies/rego &
    VERDEAZUL_PRUEBAS_BD="postgresql://app_rw@localhost:5432/neondb" \
        pytest tests/certificados -v

La base de pruebas NUNCA es Neon.
"""

import base64
import importlib.util
import os
import pathlib
import secrets
import uuid

import pytest

from app import config

_ruta = pathlib.Path(__file__).parents[1] / "certificacion" / "conftest.py"
_especificacion = importlib.util.spec_from_file_location(
    "conftest_certificacion", _ruta)
_certificacion = importlib.util.module_from_spec(_especificacion)
_especificacion.loader.exec_module(_certificacion)

llaves_de_prueba = _certificacion.llaves_de_prueba
grupo = _certificacion.grupo
api = _certificacion.api
fabrica = _certificacion.fabrica
entrar = _certificacion.entrar
cabecera = _certificacion.cabecera

# Una llave de firma por corrida. Nunca la de Secret Manager.
_LLAVE_FIRMA = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


@pytest.fixture(autouse=True)
def llave_de_firma(monkeypatch):
    monkeypatch.setattr(config, "LLAVE_FIRMA_CERTIFICADOS",
                        config.Secreto(_LLAVE_FIRMA))


def lugar() -> tuple[float, float]:
    """Una esquina al azar lejos de las demas pruebas y de la semilla, para
    que ningun traslape de una prueba afecte a otra."""
    return (-(100 + secrets.randbelow(5000) / 100),
            20 + secrets.randbelow(500) / 100)


def finca_en(fabrica, propietario, x, y, lado=0.01, zona="PN") -> int:
    """Una finca cuadrada con la esquina en (x, y)."""
    poligono = ("POLYGON((%(x)s %(y)s, %(x2)s %(y)s, %(x2)s %(y2)s, "
                "%(x)s %(y2)s, %(x)s %(y)s))"
                % {"x": x, "y": y, "x2": x + lado, "y2": y + lado})
    return fabrica.sql(
        "INSERT INTO fincas (nombre, zona, propietario, poligono) "
        "VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326)) RETURNING id",
        ("Finca " + uuid.uuid4().hex[:6], zona, propietario["id"],
         poligono))[0]["id"]
