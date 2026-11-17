"""Firma y verificacion de certificados, sin base de datos ni motor.

Son las pruebas del control 2.3.6 y de los 15 puntos de certificados: que un
certificado firmado verifique, que uno alterado falle, y que uno firmado con
otra llave tampoco pase aunque su firma cuadre (el limite de D-10).

No necesitan Neon ni OPA, asi que corren en cualquier maquina:

    pytest tests/certificados/test_firma.py -v
"""

import base64
import copy
import json
import os

import pytest

from app import config
from app.certificados import firma, verificacion


def _llave_nueva() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


LLAVE_VERDEAZUL = _llave_nueva()

CONTENIDO = {
    "emisor": firma.EMISOR,
    "certificado": 12,
    "medicion": 1,
    "finca": 1,
    "finca_nombre": "La Esperanza",
    "zona": "PN",
    "periodo": "2026-Q4",
    "toneladas": "120.500",
    "poligono_wkt": "POLYGON((-85.7 10.6,-85.6 10.6,-85.6 10.7,-85.7 10.7,-85.7 10.6))",
    "registrada_por": 4,
    "aprobada_por": 6,
    "emitido_por": 7,
    "emitido_en": "2026-11-15T18:00:00Z",
}


@pytest.fixture(autouse=True)
def llave(monkeypatch):
    monkeypatch.setattr(config, "LLAVE_FIRMA_CERTIFICADOS",
                        config.Secreto(LLAVE_VERDEAZUL))


@pytest.fixture
def confiables():
    return {firma.huella_verdeazul()}


@pytest.fixture
def documento():
    return firma.firmar(copy.deepcopy(CONTENIDO))


def _texto(documento) -> str:
    return firma.documento_texto(documento)


# ---------------------------------------------------------------------------
# Lo que se muestra en la presentacion
# ---------------------------------------------------------------------------

def test_un_certificado_firmado_verifica(documento, confiables):
    r = verificacion.verificar_texto(_texto(documento), confiables)
    assert r.valido and r.firma_valida and r.llave_de_verdeazul
    assert r.motivo == "valido"
    assert r.contenido == CONTENIDO


@pytest.mark.parametrize("campo, nuevo", [
    ("toneladas", "999.500"),      # inflar el carbono: el fraude de la carta
    ("finca", 2),                  # cambiar de terreno
    ("poligono_wkt", CONTENIDO["poligono_wkt"].replace("-85.7", "-85.8")),
    ("emitido_en", "2026-11-16T18:00:00Z"),
])
def test_un_certificado_alterado_falla(documento, confiables, campo, nuevo):
    documento["contenido"][campo] = nuevo
    r = verificacion.verificar_texto(_texto(documento), confiables)
    assert not r.valido
    assert not r.firma_valida
    assert r.motivo == "firma_invalida"
    assert r.contenido is None


def test_cambiar_una_letra_del_archivo_falla(documento, confiables):
    texto = _texto(documento).replace("La Esperanza", "La Esperanzo")
    assert not verificacion.verificar_texto(texto, confiables).valido


def test_la_sangria_no_afecta_la_firma(documento, confiables):
    """Abrir el archivo y guardarlo con otro formato no lo invalida: se
    firma la forma canonica del contenido, no el texto."""
    compacto = json.dumps(documento, separators=(",", ":"))
    assert verificacion.verificar_texto(compacto, confiables).valido


# ---------------------------------------------------------------------------
# El limite de D-10: la llave en el documento no prueba quien firmo
# ---------------------------------------------------------------------------

def test_firmado_con_otra_llave_no_es_de_verdeazul(monkeypatch, confiables):
    """Alguien genera su propio par de llaves y firma un certificado falso.
    La firma cuadra con la llave que el puso, pero esa llave no es la de
    Verdeazul."""
    monkeypatch.setattr(config, "LLAVE_FIRMA_CERTIFICADOS",
                        config.Secreto(_llave_nueva()))
    falso = firma.firmar(dict(CONTENIDO, toneladas="5000.000"))
    r = verificacion.verificar_texto(_texto(falso), confiables)
    assert r.firma_valida is True
    assert r.llave_de_verdeazul is False
    assert r.valido is False
    assert r.motivo == "llave_desconocida"


def test_cambiar_la_llave_del_documento_no_sirve(documento, confiables):
    """Reemplazar la llave publica por otra rompe la huella o la firma."""
    otra = firma.b64(os.urandom(32))
    documento["firma"]["llave_publica"] = otra
    assert verificacion.verificar_texto(_texto(documento), confiables).motivo \
        == "formato_invalido"
    documento["firma"]["huella_llave"] = firma.huella(firma.desb64(otra))
    assert not verificacion.verificar_texto(_texto(documento), confiables).valido


# ---------------------------------------------------------------------------
# Archivos que no son certificados
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "",
    "no es json",
    "[]",
    "{}",
    '{"formato": "otro", "contenido": {}, "firma": {}}',
    "NaN",
])
def test_lo_que_no_es_un_certificado(texto, confiables):
    r = verificacion.verificar_texto(texto, confiables)
    assert (r.valido, r.motivo) == (False, "formato_invalido")


def test_un_campo_sin_firmar_fuera_del_contenido_se_rechaza(documento,
                                                            confiables):
    """Lo de fuera de `contenido` no esta firmado. Si se aceptara, alguien
    podria agregar "toneladas": "5000" junto a una firma valida."""
    documento["toneladas"] = "5000.000"
    assert verificacion.verificar_texto(_texto(documento), confiables).motivo \
        == "formato_invalido"


def test_una_llave_repetida_se_rechaza(documento, confiables):
    """Dos programas podrian leer valores distintos del mismo archivo."""
    texto = _texto(documento).replace(
        '"toneladas": "120.500"', '"toneladas": "120.500", "toneladas": "9.0"')
    assert verificacion.verificar_texto(texto, confiables).motivo \
        == "formato_invalido"


def test_un_archivo_enorme_se_rechaza(confiables):
    texto = '{"x": "' + "a" * verificacion.MAXIMO_BYTES + '"}'
    assert verificacion.verificar_texto(texto, confiables).motivo \
        == "formato_invalido"


def test_otro_algoritmo_se_rechaza(documento, confiables):
    documento["firma"]["algoritmo"] = "none"
    assert verificacion.verificar_texto(_texto(documento), confiables).motivo \
        == "formato_invalido"


# ---------------------------------------------------------------------------
# La llave
# ---------------------------------------------------------------------------

def test_sin_llave_no_se_firma(monkeypatch):
    monkeypatch.setattr(config, "LLAVE_FIRMA_CERTIFICADOS", None)
    with pytest.raises(firma.SinLlaveFirma):
        firma.firmar(CONTENIDO)


def test_la_llave_privada_no_sale_en_el_documento(documento):
    assert LLAVE_VERDEAZUL not in _texto(documento)


def test_la_huella_publicada_es_la_de_la_llave_que_firma(documento):
    assert documento["firma"]["huella_llave"] == firma.huella_verdeazul()
