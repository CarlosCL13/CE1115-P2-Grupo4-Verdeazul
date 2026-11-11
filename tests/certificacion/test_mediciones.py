"""O3 Mediciones de biomasa. C1, C2, C3, C7, C8 y la inmutabilidad."""

import pytest

from conftest import entrar


@pytest.fixture
def escenario(fabrica):
    """Una finca de PN, un periodo abierto, un tecnico y dos verificadores."""
    dueno = fabrica.cuenta("DUENO_FINCA")
    return {
        "dueno": dueno,
        "finca": fabrica.finca(dueno, "PN"),
        "periodo": fabrica.periodo(),
        "tecnico": fabrica.cuenta("TECNICO_CAMPO", zonas=("PN",)),
        "ver1": fabrica.cuenta("VERIFICADOR", zonas=("PN",)),
        "ver2": fabrica.cuenta("VERIFICADOR", zonas=("PN",)),
    }


def _registrar(api, h, e, biomasa="12.345"):
    return api.post("/mediciones", headers=h, json={
        "finca": e["finca"], "periodo": e["periodo"],
        "biomasa_toneladas": biomasa})


# --- registrar --------------------------------------------------------------

def test_tecnico_registra_en_su_zona_con_periodo_abierto(api, fabrica, escenario):
    h = entrar(api, fabrica, escenario["tecnico"])
    r = _registrar(api, h, escenario)
    assert r.status_code == 201, r.text
    ver = api.get("/mediciones/%d" % r.json()["id"], headers=h).json()
    assert ver["estado"] == "REGISTRADA" and ver["biomasa_toneladas"] == "12.345"
    assert ver["autor"] == escenario["tecnico"]["id"]
    assert fabrica.eventos("MEDICION_REGISTRADA", escenario["tecnico"]["id"])


def test_c2_periodo_cerrado_no_admite_mediciones(api, fabrica, escenario):
    cerrado = fabrica.periodo("CERRADO")
    h = entrar(api, fabrica, escenario["tecnico"])
    r = api.post("/mediciones", headers=h, json={
        "finca": escenario["finca"], "periodo": cerrado,
        "biomasa_toneladas": "5"})
    assert r.status_code == 403
    assert fabrica.eventos("ACCESO_DENEGADO", escenario["tecnico"]["id"])


def test_el_tecnico_no_registra_en_una_zona_ajena(api, fabrica, escenario):
    lejana = fabrica.finca(escenario["dueno"], "CS")
    h = entrar(api, fabrica, escenario["tecnico"])
    r = api.post("/mediciones", headers=h, json={
        "finca": lejana, "periodo": escenario["periodo"],
        "biomasa_toneladas": "5"})
    assert r.status_code == 403


def test_c1_c2_el_verificador_tambien_registra_en_su_zona(api, fabrica, escenario):
    h = entrar(api, fabrica, escenario["ver1"])
    assert _registrar(api, h, escenario).status_code == 201
    fuera = entrar(api, fabrica, fabrica.cuenta("VERIFICADOR", zonas=("CS",)))
    assert _registrar(api, fuera, escenario).status_code == 403


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "DIRECCION_CERTIFICACION",
                                 "PERSONAL_ADMINISTRATIVO", "AUDITOR_EXTERNO",
                                 "DUENO_FINCA", "TERCERO_AUTORIZADO"])
def test_los_demas_roles_no_registran(api, fabrica, escenario, rol):
    assert _registrar(api, entrar(api, fabrica, fabrica.cuenta(rol)),
                      escenario).status_code == 403


@pytest.mark.parametrize("biomasa", ["0", "-3", "abc", "1234567890", "1.2345"])
def test_biomasa_invalida_se_rechaza(api, fabrica, escenario, biomasa):
    r = _registrar(api, entrar(api, fabrica, escenario["tecnico"]),
                   escenario, biomasa)
    assert r.status_code == 422


def test_finca_o_periodo_inexistente(api, fabrica, escenario):
    h = entrar(api, fabrica, escenario["tecnico"])
    r = api.post("/mediciones", headers=h, json={
        "finca": 99999999, "periodo": escenario["periodo"],
        "biomasa_toneladas": "1"})
    # Para quien no puede ver "todo", no existe y no tiene permiso se parecen.
    assert r.status_code == 403


# --- C3 ---------------------------------------------------------------------

def test_c3_quien_registro_no_la_aprueba(api, fabrica, escenario):
    e = escenario
    medicion = fabrica.medicion(e["finca"], e["periodo"], e["ver1"])
    h = entrar(api, fabrica, e["ver1"], reautenticar=True)
    r = api.post("/mediciones/%d/aprobar" % medicion, headers=h)
    assert r.status_code == 403
    assert fabrica.eventos("ACCESO_DENEGADO", e["ver1"]["id"])
    assert api.get("/mediciones/%d" % medicion, headers=h
                   ).json()["estado"] == "REGISTRADA"


def test_c3_quien_midio_esa_finca_en_ese_periodo_tampoco(api, fabrica, escenario):
    """Ver2 no es autor de la medicion, pero midio otra en la misma finca."""
    e = escenario
    ajena = fabrica.medicion(e["finca"], e["periodo"], e["tecnico"])
    fabrica.medicion(e["finca"], e["periodo"], e["ver2"])
    h = entrar(api, fabrica, e["ver2"], reautenticar=True)
    assert api.post("/mediciones/%d/aprobar" % ajena, headers=h
                    ).status_code == 403
    assert api.post("/mediciones/%d/devolver" % ajena, headers=h,
                    json={"motivo": "no cuadra"}).status_code == 403


def test_c3_otro_verificador_aprueba(api, fabrica, escenario):
    e = escenario
    medicion = fabrica.medicion(e["finca"], e["periodo"], e["tecnico"])
    h = entrar(api, fabrica, e["ver1"], reautenticar=True)
    r = api.post("/mediciones/%d/aprobar" % medicion, headers=h)
    assert r.status_code == 200, r.text
    ver = api.get("/mediciones/%d" % medicion, headers=h).json()
    assert ver["estado"] == "APROBADA" and ver["revisada_por"] == \
        e["ver1"]["id"]
    assert fabrica.eventos("MEDICION_APROBADA", e["ver1"]["id"])
    # Ya decidida, no se decide de nuevo.
    assert api.post("/mediciones/%d/aprobar" % medicion, headers=h
                    ).json()["detail"] == "estado_invalido"
    assert api.post("/mediciones/%d/devolver" % medicion, headers=h,
                    json={"motivo": "ya no"}).json()["detail"] == \
        "estado_invalido"


def test_aprobar_pide_reautenticacion(api, fabrica, escenario):
    e = escenario
    medicion = fabrica.medicion(e["finca"], e["periodo"], e["tecnico"])
    h = entrar(api, fabrica, e["ver1"])
    r = api.post("/mediciones/%d/aprobar" % medicion, headers=h)
    assert r.status_code == 401
    assert r.json()["detail"] == "reautenticacion_requerida"


def test_devolver_lleva_motivo(api, fabrica, escenario):
    e = escenario
    medicion = fabrica.medicion(e["finca"], e["periodo"], e["tecnico"])
    h = entrar(api, fabrica, e["ver1"])
    assert api.post("/mediciones/%d/devolver" % medicion, headers=h,
                    json={}).status_code == 422
    assert api.post("/mediciones/%d/devolver" % medicion, headers=h,
                    json={"motivo": "xx"}).status_code == 422
    r = api.post("/mediciones/%d/devolver" % medicion, headers=h,
                 json={"motivo": "Falta la parcela norte"})
    assert r.status_code == 200 and r.json()["estado"] == "DEVUELTA"
    assert api.get("/mediciones/%d" % medicion, headers=h
                   ).json()["motivo_devolucion"] == "Falta la parcela norte"
    assert fabrica.eventos("MEDICION_DEVUELTA", e["ver1"]["id"])


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "DIRECCION_CERTIFICACION",
                                 "PERSONAL_ADMINISTRATIVO", "TECNICO_CAMPO",
                                 "AUDITOR_EXTERNO", "DUENO_FINCA"])
def test_solo_el_verificador_decide(api, fabrica, escenario, rol):
    e = escenario
    medicion = fabrica.medicion(e["finca"], e["periodo"], e["ver1"])
    h = entrar(api, fabrica, fabrica.cuenta(rol), reautenticar=True)
    assert api.post("/mediciones/%d/aprobar" % medicion, headers=h
                    ).status_code == 403
    assert api.post("/mediciones/%d/devolver" % medicion, headers=h,
                    json={"motivo": "no puedo"}).status_code == 403


def test_la_segunda_aprobacion_encuentra_el_estado_nuevo(api, fabrica, escenario):
    """Aprobada una vez, la de otro verificador recibe 409, no un segundo cambio."""
    e = escenario
    medicion = fabrica.medicion(e["finca"], e["periodo"], e["tecnico"])
    a = entrar(api, fabrica, e["ver1"], reautenticar=True)
    b = entrar(api, fabrica, e["ver2"], reautenticar=True)
    assert api.post("/mediciones/%d/aprobar" % medicion, headers=a
                    ).status_code == 200
    assert api.post("/mediciones/%d/aprobar" % medicion, headers=b
                    ).status_code == 409


# --- inmutabilidad ----------------------------------------------------------

def test_ningun_rol_modifica_una_medicion(api, fabrica, escenario):
    e = escenario
    medicion = fabrica.medicion(e["finca"], e["periodo"], e["tecnico"])
    h = entrar(api, fabrica, e["ver1"], reautenticar=True)
    for metodo in (api.patch, api.put, api.delete):
        assert metodo("/mediciones/%d" % medicion, headers=h
                      ).status_code == 405


def test_la_base_impide_cambiar_la_biomasa(fabrica, escenario):
    """Aunque un bug o una inyeccion lo intentara: app_rw no tiene el permiso."""
    e = escenario
    medicion = fabrica.medicion(e["finca"], e["periodo"], e["tecnico"])
    with pytest.raises(Exception, match="permission denied"):
        fabrica.sql("UPDATE mediciones SET biomasa_toneladas = 999 "
                    "WHERE id = %s", (medicion,))


# --- lectura ---------------------------------------------------------------

def test_c8_el_dueno_solo_ve_las_mediciones_de_su_finca(api, fabrica, escenario):
    e = escenario
    suya = fabrica.medicion(e["finca"], e["periodo"], e["tecnico"])
    otra_finca = fabrica.finca(fabrica.cuenta("DUENO_FINCA"), "PN")
    ajena = fabrica.medicion(otra_finca, e["periodo"], e["tecnico"])
    h = entrar(api, fabrica, e["dueno"])
    ids = {m["id"] for m in api.get("/mediciones", headers=h
                                    ).json()["mediciones"]}
    assert suya in ids and ajena not in ids
    assert api.get("/mediciones/%d" % ajena, headers=h).status_code == 403


def test_c1_el_tecnico_solo_ve_su_zona(api, fabrica, escenario):
    e = escenario
    lejana = fabrica.finca(e["dueno"], "CS")
    suya = fabrica.medicion(e["finca"], e["periodo"], e["tecnico"])
    fuera = fabrica.medicion(lejana, e["periodo"], e["tecnico"])
    h = entrar(api, fabrica, e["tecnico"])
    ids = {m["id"] for m in api.get("/mediciones?periodo=%d" % e["periodo"],
                                    headers=h).json()["mediciones"]}
    assert suya in ids and fuera not in ids
    assert api.get("/mediciones/%d" % fuera, headers=h).status_code == 403


def test_filtros_del_listado(api, fabrica, escenario):
    e = escenario
    a = fabrica.medicion(e["finca"], e["periodo"], e["tecnico"])
    b = fabrica.medicion(e["finca"], e["periodo"], e["tecnico"],
                         estado="APROBADA", revisor=e["ver1"])
    h = entrar(api, fabrica, fabrica.cuenta("DIRECCION_GENERAL"))
    r = api.get("/mediciones?periodo=%d&estado=APROBADA" % e["periodo"],
                headers=h).json()["mediciones"]
    assert [m["id"] for m in r] == [b]
    assert api.get("/mediciones?estado=INVENTADA", headers=h
                   ).status_code == 422
    assert a  # la registrada no sale con el filtro de aprobadas


# --- exportar (C7) ----------------------------------------------------------

def test_c7_el_auditor_exporta_dentro_de_su_ventana(api, fabrica, escenario):
    e = escenario
    medicion = fabrica.medicion(e["finca"], e["periodo"], e["tecnico"])
    auditor = fabrica.cuenta("AUDITOR_EXTERNO")
    fabrica.ventana(auditor)
    h = entrar(api, fabrica, auditor)
    r = api.get("/mediciones/exportar", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lineas = r.text.splitlines()
    assert lineas[0].startswith("id,finca,periodo")
    assert any(l.startswith("%d," % medicion) for l in lineas[1:])
    assert fabrica.eventos("MEDICIONES_EXPORTADAS", auditor["id"])


def test_c7_fuera_de_la_ventana_no_hay_permiso(api, fabrica):
    vencido = fabrica.cuenta("AUDITOR_EXTERNO")
    fabrica.ventana(vencido, dias_desde=-9, dias_hasta=-3)
    sin = fabrica.cuenta("AUDITOR_EXTERNO")
    for cuenta in (vencido, sin):
        assert api.get("/mediciones/exportar", headers=entrar(
            api, fabrica, cuenta)).status_code == 403
        assert api.get("/mediciones", headers=entrar(
            api, fabrica, cuenta)).status_code == 403


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "DIRECCION_CERTIFICACION",
                                 "VERIFICADOR", "TECNICO_CAMPO", "DUENO_FINCA"])
def test_solo_el_auditor_exporta(api, fabrica, rol):
    assert api.get("/mediciones/exportar", headers=entrar(
        api, fabrica, fabrica.cuenta(rol))).status_code == 403
