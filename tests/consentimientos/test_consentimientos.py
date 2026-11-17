"""O7 consentimientos contra la matriz, con un OPA real y una base desechable.

    DG       L
    PA       L, C
    DF       L.C8, C.C8, M.C8
    demas    nada

Y la politica que este objeto hace real: un tercero solo ve lo que el dueno
autorizo (LG-03), toda autorizacion vence, y el dueno la revoca cuando
quiera (CU-09).
"""

import datetime

import pytest

from conftest import entrar

HOY = datetime.date.today()


def _en(dias: int) -> str:
    return (HOY + datetime.timedelta(days=dias)).isoformat()


@pytest.fixture
def escena(fabrica):
    dueno = fabrica.cuenta("DUENO_FINCA")
    return {"dueno": dueno, "finca": fabrica.finca(dueno),
            "tercero": fabrica.cuenta("TERCERO_AUTORIZADO")}


def _crear(api, h, finca, tercero, dias=30):
    return api.post("/consentimientos", headers=h, json={
        "finca": finca, "tercero": tercero["id"], "vence": _en(dias)})


# ---------------------------------------------------------------------------
# C: autorizar
# ---------------------------------------------------------------------------

def test_el_dueno_autoriza_sobre_su_finca(api, fabrica, escena):
    h = entrar(api, fabrica, escena["dueno"], reautenticar=True)
    r = _crear(api, h, escena["finca"], escena["tercero"])
    assert r.status_code == 201, r.text
    k = r.json()
    assert (k["finca"], k["tercero"], k["otorgado_por"], k["vigente"]) == (
        escena["finca"], escena["tercero"]["id"], escena["dueno"]["id"], True)
    assert fabrica.eventos("CONSENTIMIENTO_OTORGADO", escena["dueno"]["id"])


def test_autorizar_pide_reautenticacion(api, fabrica, escena):
    h = entrar(api, fabrica, escena["dueno"])
    r = _crear(api, h, escena["finca"], escena["tercero"])
    assert r.status_code == 401
    assert r.json()["detail"] == "reautenticacion_requerida"


def test_el_dueno_no_autoriza_sobre_una_finca_ajena(api, fabrica, escena):
    otro = fabrica.cuenta("DUENO_FINCA")
    h = entrar(api, fabrica, otro, reautenticar=True)
    assert _crear(api, h, escena["finca"], escena["tercero"]).status_code == 403


def test_el_administrativo_registra_por_el_dueno(api, fabrica, escena):
    """La matriz le da C al Personal Administrativo. Quien otorga sigue
    siendo el dueno; quien registro queda en la bitacora."""
    pa = fabrica.cuenta("PERSONAL_ADMINISTRATIVO")
    h = entrar(api, fabrica, pa, reautenticar=True)
    r = _crear(api, h, escena["finca"], escena["tercero"])
    assert r.status_code == 201, r.text
    assert r.json()["otorgado_por"] == escena["dueno"]["id"]
    evento = fabrica.eventos("CONSENTIMIENTO_OTORGADO", pa["id"])[-1]
    assert evento["detalle"]["registrado_por_rol"] == "PERSONAL_ADMINISTRATIVO"


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "DIRECCION_CERTIFICACION",
                                 "TECNICO_CAMPO", "VERIFICADOR",
                                 "AUDITOR_EXTERNO", "TERCERO_AUTORIZADO"])
def test_los_demas_no_autorizan(api, fabrica, escena, rol):
    quien = fabrica.cuenta(rol, zonas=("PN",))
    if rol == "AUDITOR_EXTERNO":
        fabrica.ventana(quien)
    h = entrar(api, fabrica, quien, reautenticar=True)
    # Ni un tercero a si mismo.
    tercero = quien if rol == "TERCERO_AUTORIZADO" else escena["tercero"]
    assert _crear(api, h, escena["finca"], tercero).status_code == 403


@pytest.mark.parametrize("cambio, detalle", [
    ({"vence": "2020-01-01"}, "vence_en_el_pasado"),
    ({"vence": HOY.isoformat()}, "vence_en_el_pasado"),
    ({"vence": "2099-01-01"}, "vence_muy_lejos"),
    ({"tercero": "otra_cuenta"}, "tercero_invalido"),
])
def test_datos_invalidos(api, fabrica, escena, cambio, detalle):
    h = entrar(api, fabrica, escena["dueno"], reautenticar=True)
    datos = {"finca": escena["finca"], "tercero": escena["tercero"]["id"],
             "vence": _en(30)}
    if cambio.get("tercero") == "otra_cuenta":
        # Un tecnico no es un tercero autorizado.
        cambio = {"tercero": fabrica.cuenta("TECNICO_CAMPO")["id"]}
    r = api.post("/consentimientos", headers=h, json={**datos, **cambio})
    assert r.status_code == 422
    assert r.json()["detail"] == detalle


def test_no_dos_vigentes_iguales(api, fabrica, escena):
    h = entrar(api, fabrica, escena["dueno"], reautenticar=True)
    assert _crear(api, h, escena["finca"], escena["tercero"]).status_code == 201
    r = _crear(api, h, escena["finca"], escena["tercero"])
    assert r.status_code == 409
    assert r.json()["detail"] == "ya_autorizado"


# ---------------------------------------------------------------------------
# L: quien ve que
# ---------------------------------------------------------------------------

@pytest.fixture
def otorgado(api, fabrica, escena):
    h = entrar(api, fabrica, escena["dueno"], reautenticar=True)
    return _crear(api, h, escena["finca"], escena["tercero"]).json()


def _lista(api, fabrica, quien):
    h = entrar(api, fabrica, quien)
    r = api.get("/consentimientos", headers=h)
    return r.status_code, {k["id"] for k in r.json().get("consentimientos", [])}


def test_el_dueno_ve_los_suyos(api, fabrica, escena, otorgado):
    assert otorgado["id"] in _lista(api, fabrica, escena["dueno"])[1]
    h = entrar(api, fabrica, escena["dueno"])
    assert api.get("/consentimientos/%d" % otorgado["id"],
                   headers=h).status_code == 200


def test_otro_dueno_no_ve_los_ajenos(api, fabrica, otorgado):
    otro = fabrica.cuenta("DUENO_FINCA")
    estado, ids = _lista(api, fabrica, otro)
    assert estado == 200 and otorgado["id"] not in ids
    h = entrar(api, fabrica, otro)
    assert api.get("/consentimientos/%d" % otorgado["id"],
                   headers=h).status_code == 403


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "PERSONAL_ADMINISTRATIVO"])
def test_dg_y_pa_ven_todos(api, fabrica, otorgado, rol):
    assert otorgado["id"] in _lista(api, fabrica, fabrica.cuenta(rol))[1]


@pytest.mark.parametrize("rol", ["DIRECCION_CERTIFICACION", "TECNICO_CAMPO",
                                 "VERIFICADOR", "TERCERO_AUTORIZADO"])
def test_sin_l_sobre_o7(api, fabrica, otorgado, rol):
    """Ni siquiera el tercero ve la fila que lo autoriza: la matriz le da
    L sobre los certificados (O5), no sobre las autorizaciones."""
    assert _lista(api, fabrica, fabrica.cuenta(rol, zonas=("PN",)))[0] == 403


# ---------------------------------------------------------------------------
# M: extender y revocar
# ---------------------------------------------------------------------------

def test_revocar_no_pide_reautenticacion_y_corta_el_acceso(api, fabrica,
                                                           escena, otorgado):
    h = entrar(api, fabrica, escena["dueno"])
    r = api.patch("/consentimientos/%d" % otorgado["id"], headers=h,
                  json={"revocar": True})
    assert r.status_code == 200, r.text
    assert r.json()["revocado_en"] and r.json()["vigente"] is False
    assert fabrica.eventos("CONSENTIMIENTO_REVOCADO", escena["dueno"]["id"])
    r = api.patch("/consentimientos/%d" % otorgado["id"], headers=h,
                  json={"revocar": True})
    assert r.status_code == 409


def test_extender_pide_reautenticacion(api, fabrica, escena, otorgado):
    h = entrar(api, fabrica, escena["dueno"])
    r = api.patch("/consentimientos/%d" % otorgado["id"], headers=h,
                  json={"vence": _en(60)})
    assert r.status_code == 401
    h = entrar(api, fabrica, escena["dueno"], reautenticar=True)
    r = api.patch("/consentimientos/%d" % otorgado["id"], headers=h,
                  json={"vence": _en(60)})
    assert r.status_code == 200 and r.json()["vence"] == _en(60)


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "PERSONAL_ADMINISTRATIVO",
                                 "DUENO_FINCA"])
def test_solo_el_dueno_modifica_lo_suyo(api, fabrica, otorgado, rol):
    """PA tiene C pero no M; otro dueno tiene M, pero no sobre lo ajeno."""
    h = entrar(api, fabrica, fabrica.cuenta(rol), reautenticar=True)
    r = api.patch("/consentimientos/%d" % otorgado["id"], headers=h,
                  json={"revocar": True})
    assert r.status_code == 403


def test_revocar_y_extender_a_la_vez_no(api, fabrica, escena, otorgado):
    h = entrar(api, fabrica, escena["dueno"], reautenticar=True)
    r = api.patch("/consentimientos/%d" % otorgado["id"], headers=h,
                  json={"revocar": True, "vence": _en(10)})
    assert r.status_code == 422
