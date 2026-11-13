"""El calculo del eslabon, sin base ni secretos de verdad."""

import base64
from datetime import datetime, timedelta, timezone

import pytest

from app import eslabon

LLAVE = bytes(range(32))
OTRA_LLAVE = bytes(range(1, 33))

UTC = timezone.utc
COSTA_RICA = timezone(timedelta(hours=-6))


def evento(**cambios):
    base = {
        "id": eslabon.id_en_bitacora(1),
        "momento": datetime(2026, 11, 12, 15, 30, 0, 123456, tzinfo=UTC),
        "accion": "MEDICION_APROBADA",
        "sujeto": "7",
        "objeto": "O3:5",
        "resultado": "PERMITIDO",
        "motivo": None,
        "detalle": {"periodo": "2", "finca": "3"},
    }
    base.update(cambios)
    return base


# ---------------------------------------------------------------------------
# El vector fijo. Si esta prueba falla, alguien cambio la forma canonica, el
# separador o el espacio de ids, y todos los eventos que ya estan en la
# bitacora dejarian de verificar. No se "arregla" cambiando el valor esperado.
# ---------------------------------------------------------------------------

def test_vector_fijo():
    assert str(eslabon.id_en_bitacora(1)) == VECTOR_ID
    assert eslabon.canonico(evento()) == VECTOR_CANONICO
    assert eslabon.calcular(LLAVE, eslabon.INICIO, evento()) == VECTOR_ESLABON


VECTOR_ID = "f25054da-b0c6-5d1f-b666-557f8c8c4fb9"
VECTOR_CANONICO = (
    b'{"accion":"MEDICION_APROBADA","detalle":{"finca":"3","periodo":"2"},'
    b'"id":"f25054da-b0c6-5d1f-b666-557f8c8c4fb9",'
    b'"momento":"2026-11-12T15:30:00.123456+00:00","motivo":null,'
    b'"objeto":"O3:5","resultado":"PERMITIDO","sujeto":"7"}')
VECTOR_ESLABON = "7e6c083591033401b894620547aef798ad5efe1910882a92847fb4714390a130"


# ---------------------------------------------------------------------------
# Siempre igual
# ---------------------------------------------------------------------------

def test_mismo_evento_mismo_eslabon():
    assert (eslabon.calcular(LLAVE, "", evento())
            == eslabon.calcular(LLAVE, "", evento()))


def test_el_orden_de_las_claves_del_detalle_no_importa():
    a = evento(detalle={"finca": "3", "periodo": "2"})
    b = evento(detalle={"periodo": "2", "finca": "3"})
    assert eslabon.calcular(LLAVE, "", a) == eslabon.calcular(LLAVE, "", b)


def test_el_mismo_instante_en_otra_zona_horaria_da_lo_mismo():
    utc = evento()
    local = evento(momento=utc["momento"].astimezone(COSTA_RICA))
    assert eslabon.canonico(utc) == eslabon.canonico(local)


def test_hora_sin_zona_se_rechaza():
    with pytest.raises(ValueError):
        eslabon.canonico(evento(momento=datetime(2026, 11, 12, 15, 30)))


def test_es_hexadecimal_de_64():
    sello = eslabon.calcular(LLAVE, "", evento())
    assert len(sello) == 64
    int(sello, 16)


# ---------------------------------------------------------------------------
# Cualquier cambio se nota
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("campo, valor", [
    ("id", eslabon.id_en_bitacora(2)),
    ("momento", datetime(2026, 11, 12, 15, 30, 0, 123457, tzinfo=UTC)),
    ("accion", "MEDICION_DEVUELTA"),
    ("sujeto", "8"),
    ("objeto", "O3:6"),
    ("resultado", "DENEGADO"),
    ("motivo", "C3"),
    ("detalle", {"periodo": "2", "finca": "1"}),
    ("detalle", None),
])
def test_cambiar_cualquier_campo_cambia_el_eslabon(campo, valor):
    original = eslabon.calcular(LLAVE, "", evento())
    assert eslabon.calcular(LLAVE, "", evento(**{campo: valor})) != original


def test_otra_llave_da_otro_eslabon():
    assert (eslabon.calcular(LLAVE, "", evento())
            != eslabon.calcular(OTRA_LLAVE, "", evento()))


def test_otro_anterior_da_otro_eslabon():
    a = eslabon.calcular(LLAVE, "", evento())
    assert eslabon.calcular(LLAVE, a, evento()) != a


def test_alterar_un_evento_del_medio_rompe_la_cadena_de_ahi_en_adelante():
    eventos = [evento(id=eslabon.id_en_bitacora(i), objeto=f"O3:{i}")
               for i in range(1, 6)]

    def encadenar(lista):
        anterior, sellos = eslabon.INICIO, []
        for ev in lista:
            anterior = eslabon.calcular(LLAVE, anterior, ev)
            sellos.append(anterior)
        return sellos

    originales = encadenar(eventos)
    eventos[2] = {**eventos[2], "detalle": {"biomasa": "999"}}
    alterados = encadenar(eventos)

    assert alterados[:2] == originales[:2]
    assert all(a != o for a, o in zip(alterados[2:], originales[2:]))


def test_coincide():
    sello = eslabon.calcular(LLAVE, "", evento())
    assert eslabon.coincide(sello, sello)
    assert not eslabon.coincide(sello, "0" * 64)


# ---------------------------------------------------------------------------
# El id en la bitacora
# ---------------------------------------------------------------------------

def test_el_id_se_deriva_siempre_igual():
    assert eslabon.id_en_bitacora(41) == eslabon.id_en_bitacora(41)
    assert eslabon.id_en_bitacora(41) != eslabon.id_en_bitacora(42)


# ---------------------------------------------------------------------------
# La llave
# ---------------------------------------------------------------------------

def _texto(crudo: bytes) -> str:
    # Como secrets.token_urlsafe: base64 url sin relleno.
    return base64.urlsafe_b64encode(crudo).decode().rstrip("=")


def test_llave_como_la_genera_token_urlsafe():
    assert eslabon.llave_desde_texto(_texto(LLAVE)) == LLAVE


def test_llave_con_salto_de_linea_de_powershell():
    assert eslabon.llave_desde_texto(_texto(LLAVE) + "\r\n") == LLAVE


@pytest.mark.parametrize("texto", [None, "", "no es base64 !!", _texto(b"corta")])
def test_llave_invalida(texto):
    with pytest.raises(eslabon.LlaveInvalida):
        eslabon.llave_desde_texto(texto)
