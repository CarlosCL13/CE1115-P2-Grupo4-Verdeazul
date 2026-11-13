"""El punto de entrada: que tarea responde que, sin abrir ninguna base."""

import pytest
from fastapi.testclient import TestClient

from app import bd, eslabon, main


@pytest.fixture
def cliente():
    return TestClient(main.app, raise_server_exceptions=False)


def test_tarea_desconocida(cliente):
    assert cliente.post("/tareas/borrar").status_code == 404


def test_las_cuatro_tareas_estan_escritas():
    assert set(main.IMPLEMENTADAS) == set(main.TAREAS)


def test_volcado_sin_deposito_es_503(cliente, monkeypatch):
    from app import almacen

    def falla():
        raise almacen.SinDeposito("x")
    monkeypatch.setitem(main.IMPLEMENTADAS, "volcado", falla)
    assert cliente.post("/tareas/volcado").status_code == 503


def test_una_cadena_rota_responde_409_con_el_informe(cliente, monkeypatch):
    informe = {"tarea": "cadena", "intacta": False, "rotos": 1,
               "primer_roto": 42}
    monkeypatch.setitem(main.IMPLEMENTADAS, "cadena", lambda: informe)
    r = cliente.post("/tareas/cadena")
    assert r.status_code == 409
    assert r.json() == informe


def test_una_cadena_intacta_responde_200(cliente, monkeypatch):
    monkeypatch.setitem(main.IMPLEMENTADAS, "cadena",
                        lambda: {"tarea": "cadena", "intacta": True})
    assert cliente.post("/tareas/cadena").status_code == 200


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
