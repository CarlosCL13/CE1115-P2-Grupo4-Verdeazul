"""O5 certificados contra la matriz, con un OPA real y una base desechable.

Esta rama: emitir (Em.C6, solo el verificador) y la verificacion publica.
Listar, ver, anular y exportar con feature/certificados-resto.

Lo que se muestra el 19 de noviembre (§6.4): emitir un certificado firmado,
verificarlo, y que uno alterado falle. Y lo que protege al cliente: que no se emitan dos certificados sobre el mismo terreno (C6).
"""

import datetime
import json

import pytest

from conftest import entrar, finca_en, lugar

HOY = datetime.date.today()


@pytest.fixture
def escena(fabrica):
    """Un dueno, un tecnico que mide, un verificador que aprueba y otro que
    emite, y una medicion aprobada lista para certificar."""
    dueno = fabrica.cuenta("DUENO_FINCA")
    tecnico = fabrica.cuenta("TECNICO_CAMPO", zonas=("PN",))
    aprobador = fabrica.cuenta("VERIFICADOR", zonas=("PN",))
    emisor = fabrica.cuenta("VERIFICADOR", zonas=("PN",))
    x, y = lugar()
    finca = finca_en(fabrica, dueno, x, y)
    periodo = fabrica.periodo("ABIERTO")
    medicion = fabrica.medicion(finca, periodo, tecnico, "APROBADA", aprobador)
    return {"dueno": dueno, "tecnico": tecnico, "aprobador": aprobador,
            "emisor": emisor, "finca": finca, "periodo": periodo,
            "medicion": medicion, "x": x, "y": y}


def _emitir(api, fabrica, quien, medicion):
    h = entrar(api, fabrica, quien, reautenticar=True)
    return api.post("/certificados/%d/emitir" % medicion, headers=h)


def _verificar(api, texto):
    # Sin cabecera de sesion: la verificacion es publica (D-09).
    return api.post("/publico/verificar", json={"archivo": texto})


# ---------------------------------------------------------------------------
# Emitir y verificar (§6.4)
# ---------------------------------------------------------------------------

def test_el_verificador_emite_y_el_certificado_verifica(api, fabrica, escena):
    r = _emitir(api, fabrica, escena["emisor"], escena["medicion"])
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["estado"] == "VIGENTE"
    assert c["huella_llave"].startswith("SHA256:")

    documento = json.loads(c["documento"])
    assert documento["contenido"]["medicion"] == escena["medicion"]
    assert documento["contenido"]["certificado"] == c["id"]
    assert documento["contenido"]["toneladas"] == "10.500"

    v = _verificar(api, c["documento"]).json()
    assert (v["valido"], v["motivo"]) == (True, "valido")

    eventos = fabrica.eventos("CERTIFICADO_EMITIDO", escena["emisor"]["id"])
    assert eventos and eventos[-1]["detalle"]["huella_llave"] == c["huella_llave"]


def test_un_certificado_alterado_falla(api, fabrica, escena):
    texto = _emitir(api, fabrica, escena["emisor"],
                    escena["medicion"]).json()["documento"]
    alterado = texto.replace('"10.500"', '"99.500"')
    assert alterado != texto
    v = _verificar(api, alterado).json()
    assert (v["valido"], v["motivo"]) == (False, "firma_invalida")


def test_emitir_pide_reautenticacion(api, fabrica, escena):
    h = entrar(api, fabrica, escena["emisor"])
    r = api.post("/certificados/%d/emitir" % escena["medicion"], headers=h)
    assert r.status_code == 401
    assert r.json()["detail"] == "reautenticacion_requerida"


# ---------------------------------------------------------------------------
# C6: aprobada, no registrada por quien emite, sin traslape
# ---------------------------------------------------------------------------

def test_quien_registro_la_medicion_no_la_certifica(api, fabrica, escena):
    """Un verificador puede medir (A1), pero no certificar lo que midio."""
    midio = fabrica.cuenta("VERIFICADOR", zonas=("PN",))
    propia = fabrica.medicion(escena["finca"], escena["periodo"], midio,
                              "APROBADA", escena["aprobador"])
    assert _emitir(api, fabrica, midio, propia).status_code == 403
    denegado = fabrica.eventos("ACCESO_DENEGADO", midio["id"])
    assert denegado and denegado[-1]["detalle"]["condicion"] == "C6"


@pytest.mark.parametrize("estado", ["REGISTRADA", "DEVUELTA"])
def test_sin_aprobar_no_se_certifica(api, fabrica, escena, estado):
    otra = fabrica.medicion(escena["finca"], escena["periodo"],
                            escena["tecnico"], estado,
                            escena["aprobador"] if estado == "DEVUELTA" else None)
    assert _emitir(api, fabrica, escena["emisor"], otra).status_code == 403


def test_dos_veces_el_mismo_terreno_no(api, fabrica, escena):
    """Fallo: un certificado emitido dos veces sobre la misma hectarea."""
    assert _emitir(api, fabrica, escena["emisor"],
                   escena["medicion"]).status_code == 201
    # Otra finca que se cruza con la primera, con su medicion aprobada.
    otro_dueno = fabrica.cuenta("DUENO_FINCA")
    encima = finca_en(fabrica, otro_dueno, escena["x"] + 0.005,
                      escena["y"] + 0.005)
    medicion = fabrica.medicion(encima, escena["periodo"], escena["tecnico"],
                                "APROBADA", escena["aprobador"])
    assert _emitir(api, fabrica, escena["emisor"], medicion).status_code == 403
    # Y la misma medicion otra vez, tampoco.
    assert _emitir(api, fabrica, escena["emisor"],
                   escena["medicion"]).status_code == 403


def test_dos_fincas_vecinas_si(api, fabrica, escena):
    """Comparten un lindero, pero no terreno: se certifican las dos (D-20)."""
    assert _emitir(api, fabrica, escena["emisor"],
                   escena["medicion"]).status_code == 201
    vecina = finca_en(fabrica, escena["dueno"], escena["x"] + 0.01,
                      escena["y"])
    medicion = fabrica.medicion(vecina, escena["periodo"], escena["tecnico"],
                                "APROBADA", escena["aprobador"])
    assert _emitir(api, fabrica, escena["emisor"], medicion).status_code == 201


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "DIRECCION_CERTIFICACION",
                                 "PERSONAL_ADMINISTRATIVO", "TECNICO_CAMPO",
                                 "AUDITOR_EXTERNO", "DUENO_FINCA",
                                 "TERCERO_AUTORIZADO"])
def test_solo_el_verificador_emite(api, fabrica, escena, rol):
    quien = fabrica.cuenta(rol, zonas=("PN",))
    if rol == "AUDITOR_EXTERNO":
        fabrica.ventana(quien)
    assert _emitir(api, fabrica, quien, escena["medicion"]).status_code == 403


def test_una_medicion_que_no_existe_responde_403(api, fabrica, escena):
    """Igual que una ajena: no se puede averiguar que ids existen."""
    assert _emitir(api, fabrica, escena["emisor"], 999_999).status_code == 403


def test_la_base_no_deja_cambiar_lo_firmado(grupo, api, fabrica, escena):
    """Migraciones 012 y 013: app_rw solo cambia lo necesario para anular.
    Aunque alguien se salte la API, el documento firmado no se toca."""
    import psycopg

    c = _emitir(api, fabrica, escena["emisor"], escena["medicion"]).json()
    for columna, valor in (("documento", "{}"), ("toneladas", "999"),
                           ("firma", b"x")):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with grupo.connection() as con:
                con.execute("UPDATE certificados SET %s = %%s WHERE id = %%s"
                            % columna, (valor, c["id"]))


# ---------------------------------------------------------------------------
# Verificacion publica (D-09)
# ---------------------------------------------------------------------------

@pytest.fixture
def emitido(api, fabrica, escena):
    return _emitir(api, fabrica, escena["emisor"], escena["medicion"]).json()


def test_la_verificacion_no_pide_sesion_ni_toca_la_base(api, fabrica, emitido):
    antes = len(fabrica.eventos())
    r = _verificar(api, emitido["documento"])
    assert r.status_code == 200 and r.json()["valido"] is True
    assert len(fabrica.eventos()) == antes


def test_la_verificacion_rechaza_lo_enorme(api):
    r = _verificar(api, "x" * 200_000)
    assert r.status_code == 413


@pytest.mark.parametrize("cuerpo", [b"no es json", b"[]", b'{"otro": 1}'])
def test_la_verificacion_rechaza_peticiones_raras(api, cuerpo):
    r = api.post("/publico/verificar", content=cuerpo,
                 headers={"content-type": "application/json"})
    assert r.status_code == 422
