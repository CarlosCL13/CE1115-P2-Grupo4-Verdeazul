"""La subida a Cloud Storage, sin red: que pida lo que tiene que pedir."""

import io
import json

import pytest

from app import almacen, config


class Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.fixture
def pedidos(monkeypatch):
    vistos = []

    def abrir(pedido, timeout):
        vistos.append(pedido)
        return Respuesta(json.dumps({"generation": "7"}).encode())
    monkeypatch.setattr(almacen.urllib.request, "urlopen", abrir)
    return vistos


def test_nunca_pisa_un_objeto_y_manda_el_token(monkeypatch, pedidos):
    monkeypatch.setattr(config, "VOLCADO_DEPOSITO", "verdeazul-g4-volcados")
    monkeypatch.setattr(config, "ENTORNO", "local")
    monkeypatch.setenv("VOLCADO_TOKEN", "token-de-prueba\n")

    r = almacen.subir("bitacora/a b.json", b"{}", "application/json")
    assert r == {"generation": "7"}
    pedido, = pedidos
    assert pedido.get_method() == "POST"
    assert "/b/verdeazul-g4-volcados/o?" in pedido.full_url
    assert "ifGenerationMatch=0" in pedido.full_url
    assert "name=bitacora%2Fa+b.json" in pedido.full_url
    assert pedido.get_header("Authorization") == "Bearer token-de-prueba"


def test_en_la_nube_el_token_sale_de_los_metadatos(monkeypatch, pedidos):
    monkeypatch.setattr(config, "VOLCADO_DEPOSITO", "dep")
    monkeypatch.setattr(config, "ENTORNO", "nube")

    respuestas = iter([b'{"access_token": "de-metadatos"}', b'{"generation": "1"}'])

    def abrir(pedido, timeout):
        pedidos.append(pedido)
        return Respuesta(next(respuestas))
    monkeypatch.setattr(almacen.urllib.request, "urlopen", abrir)

    almacen.subir("x", b"", "application/gzip")
    metadatos, subida = pedidos
    assert metadatos.full_url.startswith("http://metadata.google.internal/")
    assert metadatos.get_header("Metadata-flavor") == "Google"
    assert subida.get_header("Authorization") == "Bearer de-metadatos"


def test_sin_deposito(monkeypatch):
    monkeypatch.setattr(config, "VOLCADO_DEPOSITO", None)
    with pytest.raises(almacen.SinDeposito):
        almacen.subir("x", b"", "application/json")


def test_sin_token_en_local(monkeypatch):
    monkeypatch.setattr(config, "VOLCADO_DEPOSITO", "dep")
    monkeypatch.setattr(config, "ENTORNO", "local")
    monkeypatch.delenv("VOLCADO_TOKEN", raising=False)
    with pytest.raises(almacen.SinDeposito):
        almacen.subir("x", b"", "application/json")
