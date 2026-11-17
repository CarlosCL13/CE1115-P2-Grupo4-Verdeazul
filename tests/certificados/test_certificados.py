"""O5 certificados contra la matriz, con un OPA real y una base desechable.

    DG       L
    DC       L, An
    VF       L, Em.C6
    AE       L.C7, X.C7
    DF       L.C8
    TA       L.C9
    PA, TC   nada

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


# ---------------------------------------------------------------------------
# An: anular
# ---------------------------------------------------------------------------

def _anular(api, fabrica, quien, certificado, motivo="La medición se enmendó."):
    h = entrar(api, fabrica, quien, reautenticar=True)
    return api.post("/certificados/%d/anular" % certificado, headers=h,
                    json={"motivo": motivo})


def test_direccion_de_certificacion_anula_y_libera_el_terreno(api, fabrica,
                                                              escena):
    c = _emitir(api, fabrica, escena["emisor"], escena["medicion"]).json()
    dc = fabrica.cuenta("DIRECCION_CERTIFICACION")
    r = _anular(api, fabrica, dc, c["id"])
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ANULADO"
    assert fabrica.eventos("CERTIFICADO_ANULADO", dc["id"])
    # B2: se anula el anterior y se emite uno nuevo.
    assert _emitir(api, fabrica, escena["emisor"],
                   escena["medicion"]).status_code == 201
    assert _anular(api, fabrica, dc, c["id"]).status_code == 409


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "VERIFICADOR",
                                 "DUENO_FINCA"])
def test_solo_direccion_de_certificacion_anula(api, fabrica, escena, rol):
    c = _emitir(api, fabrica, escena["emisor"], escena["medicion"]).json()
    quien = escena["dueno"] if rol == "DUENO_FINCA" else fabrica.cuenta(rol)
    assert _anular(api, fabrica, quien, c["id"]).status_code == 403


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
# L: quien ve que (C7, C8, C9)
# ---------------------------------------------------------------------------

def _ver(api, fabrica, quien, certificado):
    h = entrar(api, fabrica, quien)
    return api.get("/certificados/%d" % certificado, headers=h)


def _ids(api, fabrica, quien):
    h = entrar(api, fabrica, quien)
    r = api.get("/certificados", headers=h)
    return r.status_code, {c["id"] for c in r.json().get("certificados", [])}


def _consentir(fabrica, finca, tercero, otorga, dias=30, revocado=False):
    fabrica.sql(
        "INSERT INTO consentimientos (finca, tercero, otorgado_por, vence, "
        "revocado_en) VALUES (%s, %s, %s, CURRENT_DATE + %s, "
        "CASE WHEN %s THEN now() END)",
        (finca, tercero["id"], otorga["id"], dias, revocado))


@pytest.fixture
def emitido(api, fabrica, escena):
    return _emitir(api, fabrica, escena["emisor"], escena["medicion"]).json()


def test_el_dueno_ve_los_suyos_y_no_los_ajenos(api, fabrica, escena, emitido):
    assert _ver(api, fabrica, escena["dueno"], emitido["id"]).status_code == 200
    otro = fabrica.cuenta("DUENO_FINCA")
    assert _ver(api, fabrica, otro, emitido["id"]).status_code == 403
    estado, ids = _ids(api, fabrica, otro)
    assert estado == 200 and emitido["id"] not in ids


def test_el_tercero_ve_lo_que_el_dueno_autorizo(api, fabrica, escena, emitido):
    tercero = fabrica.cuenta("TERCERO_AUTORIZADO")
    assert _ver(api, fabrica, tercero, emitido["id"]).status_code == 403
    _consentir(fabrica, escena["finca"], tercero, escena["dueno"])
    r = _ver(api, fabrica, tercero, emitido["id"])
    assert r.status_code == 200
    assert r.json()["documento"] == emitido["documento"]
    assert emitido["id"] in _ids(api, fabrica, tercero)[1]
    assert fabrica.eventos("CERTIFICADO_CONSULTADO", tercero["id"])


def test_una_autorizacion_de_otra_finca_no_sirve(api, fabrica, escena, emitido):
    """El hueco de la regla C9 tal como estaba escrita en P1 (D-20)."""
    tercero = fabrica.cuenta("TERCERO_AUTORIZADO")
    otra = finca_en(fabrica, escena["dueno"], *lugar())
    _consentir(fabrica, otra, tercero, escena["dueno"])
    assert _ver(api, fabrica, tercero, emitido["id"]).status_code == 403
    assert emitido["id"] not in _ids(api, fabrica, tercero)[1]


@pytest.mark.parametrize("dias, revocado", [(0, False), (-5, False),
                                            (30, True)])
def test_vencida_o_revocada_no_sirve(api, fabrica, escena, emitido, dias,
                                     revocado):
    """C9 es estricto: el dia que vence ya no sirve. Y revocar quita el
    acceso en la siguiente peticion."""
    tercero = fabrica.cuenta("TERCERO_AUTORIZADO")
    _consentir(fabrica, escena["finca"], tercero, escena["dueno"], dias,
               revocado)
    assert _ver(api, fabrica, tercero, emitido["id"]).status_code == 403


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "DIRECCION_CERTIFICACION",
                                 "VERIFICADOR"])
def test_los_internos_ven_todos(api, fabrica, emitido, rol):
    quien = fabrica.cuenta(rol)
    assert _ver(api, fabrica, quien, emitido["id"]).status_code == 200


@pytest.mark.parametrize("rol", ["PERSONAL_ADMINISTRATIVO", "TECNICO_CAMPO"])
def test_sin_l_sobre_o5(api, fabrica, emitido, rol):
    quien = fabrica.cuenta(rol, zonas=("PN",))
    assert _ver(api, fabrica, quien, emitido["id"]).status_code == 403
    assert _ids(api, fabrica, quien)[0] == 403


def test_el_auditor_solo_en_su_ventana(api, fabrica, emitido):
    auditor = fabrica.cuenta("AUDITOR_EXTERNO")
    assert _ver(api, fabrica, auditor, emitido["id"]).status_code == 403
    fabrica.ventana(auditor)
    assert _ver(api, fabrica, auditor, emitido["id"]).status_code == 200


# ---------------------------------------------------------------------------
# X: exportar
# ---------------------------------------------------------------------------

def test_el_auditor_exporta_en_su_ventana(api, fabrica, emitido):
    auditor = fabrica.cuenta("AUDITOR_EXTERNO")
    h = entrar(api, fabrica, auditor)
    assert api.get("/certificados/exportar", headers=h).status_code == 403
    fabrica.ventana(auditor)
    r = api.get("/certificados/exportar", headers=h)
    assert r.status_code == 200
    lineas = r.text.splitlines()
    assert lineas[0].startswith("id,medicion,finca,periodo,toneladas")
    assert any(l.startswith("%d," % emitido["id"]) for l in lineas[1:])


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "VERIFICADOR"])
def test_exportar_es_solo_del_auditor(api, fabrica, rol):
    h = entrar(api, fabrica, fabrica.cuenta(rol))
    assert api.get("/certificados/exportar", headers=h).status_code == 403


# ---------------------------------------------------------------------------
# Verificacion publica (D-09)
# ---------------------------------------------------------------------------

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
