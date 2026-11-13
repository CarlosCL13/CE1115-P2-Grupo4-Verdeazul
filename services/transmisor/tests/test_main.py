"""El punto de entrada: que tarea responde que, sin abrir ninguna base."""

import pytest
from fastapi.testclient import TestClient

from app import bd, eslabon, main


@pytest.fixture
def cliente():
    return TestClient(main.app, raise_server_exceptions=False)


def test_tarea_desconocida(cliente):
    assert cliente.post("/tareas/borrar").status_code == 404


@pytest.mark.parametrize("nombre", ["vencer", "cadena", "volcado"])
def test_las_que_faltan_responden_501(cliente, nombre):
    assert cliente.post(f"/tareas/{nombre}").status_code == 501


def test_transmitir_devuelve_lo_que_hizo(cliente, monkeypatch):
    monkeypatch.setitem(main.IMPLEMENTADAS, "transmitir",
                        lambda: {"tarea": "transmitir", "transmitidos": 3})
    r = cliente.post("/tareas/transmitir")
    assert r.status_code == 200
    assert r.json()["transmitidos"] == 3


@pytest.mark.parametrize("error", [bd.SinConexion("x"), eslabon.LlaveInvalida("x")])
def test_sin_configuracion_es_503(cliente, monkeypatch, error):
    def falla():
        raise error
    monkeypatch.setitem(main.IMPLEMENTADAS, "transmitir", falla)
    r = cliente.post("/tareas/transmitir")
    assert r.status_code == 503
    assert r.json() == {"detail": "transmitir: sin configurar"}


def test_un_fallo_no_filtra_detalles(cliente, monkeypatch):
    def falla():
        raise RuntimeError("password=supersecreta host=ep-algo.neon.tech")
    monkeypatch.setitem(main.IMPLEMENTADAS, "transmitir", falla)
    r = cliente.post("/tareas/transmitir")
    assert r.status_code == 500
    assert "secreta" not in r.text and "neon" not in r.text
