"""O8 asignaciones contra la matriz, con un OPA real y una base desechable.

    DG       L
    DC       L, C, M
    TC, VF   L.C1
    demas    nada

Y la politica que este objeto hace real: revocar quita el acceso en la
siguiente peticion (CU-11), y una asignacion vencida deja de dar acceso sola
(HBAC-03).
"""

import datetime

import pytest

from conftest import entrar

HOY = datetime.date.today()


def _en(dias: int) -> str:
    return (HOY + datetime.timedelta(days=dias)).isoformat()


def _crear(api, h, sujeto, zona="PC", dias=30):
    return api.post("/asignaciones", headers=h, json={
        "sujeto": sujeto["id"], "zona": zona, "vence": _en(dias)})


@pytest.fixture
def dc(api, fabrica):
    cuenta = fabrica.cuenta("DIRECCION_CERTIFICACION")
    return cuenta, entrar(api, fabrica, cuenta, reautenticar=True)


# ---------------------------------------------------------------------------
# Crear
# ---------------------------------------------------------------------------

def test_direccion_de_certificacion_asigna(api, fabrica, dc):
    cuenta, h = dc
    tecnico = fabrica.cuenta("TECNICO_CAMPO")
    r = _crear(api, h, tecnico, "PC")
    assert r.status_code == 201, r.text
    a = r.json()
    assert (a["sujeto"], a["zona"], a["vigente"]) == (tecnico["id"], "PC", True)
    assert fabrica.eventos("ASIGNACION_CREADA", cuenta["id"])


def test_asignar_pide_reautenticacion(api, fabrica):
    h = entrar(api, fabrica, fabrica.cuenta("DIRECCION_CERTIFICACION"))
    r = _crear(api, h, fabrica.cuenta("TECNICO_CAMPO"))
    assert r.status_code == 401
    assert r.json()["detail"] == "reautenticacion_requerida"


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "PERSONAL_ADMINISTRATIVO",
                                 "TECNICO_CAMPO", "VERIFICADOR",
                                 "AUDITOR_EXTERNO", "DUENO_FINCA"])
def test_solo_direccion_de_certificacion_asigna(api, fabrica, rol):
    quien = fabrica.cuenta(rol, zonas=("PC",))
    h = entrar(api, fabrica, quien, reautenticar=True)
    # Ni siquiera a si mismo: nadie se da zonas (CU-03).
    assert _crear(api, h, quien, "CS").status_code == 403


@pytest.mark.parametrize("cuerpo, detalle", [
    ({"zona": "XX"}, "zona_invalida"),
    ({"vence": "2020-01-01"}, "vence_en_el_pasado"),
    ({"vence": "2099-01-01"}, "vence_muy_lejos"),
])
def test_datos_invalidos(api, fabrica, dc, cuerpo, detalle):
    _, h = dc
    tecnico = fabrica.cuenta("TECNICO_CAMPO")
    datos = {"sujeto": tecnico["id"], "zona": "PC", "vence": _en(30), **cuerpo}
    r = api.post("/asignaciones", headers=h, json=datos)
    assert r.status_code == 422
    assert r.json()["detail"] == detalle


@pytest.mark.parametrize("rol", ["DUENO_FINCA", "DIRECCION_GENERAL",
                                 "AUDITOR_EXTERNO"])
def test_solo_tecnicos_y_verificadores_reciben_zona(api, fabrica, dc, rol):
    _, h = dc
    r = _crear(api, h, fabrica.cuenta(rol))
    assert r.status_code == 422
    assert r.json()["detail"] == "sujeto_invalido"


def test_no_se_duplica_una_asignacion_abierta(api, fabrica, dc):
    _, h = dc
    tecnico = fabrica.cuenta("TECNICO_CAMPO")
    assert _crear(api, h, tecnico, "PC").status_code == 201
    r = _crear(api, h, tecnico, "PC")
    assert r.status_code == 409
    assert r.json()["detail"] == "ya_asignada"


# ---------------------------------------------------------------------------
# Revocar: el acceso se pierde en la siguiente peticion (CU-11)
# ---------------------------------------------------------------------------

def test_revocar_quita_el_acceso_en_el_siguiente_clic(api, fabrica, dc):
    _, h_dc = dc
    tecnico = fabrica.cuenta("TECNICO_CAMPO")
    asignacion = _crear(api, h_dc, tecnico, "PS").json()["id"]
    finca = fabrica.finca(fabrica.cuenta("DUENO_FINCA"), "PS")

    # La misma sesion del tecnico, antes y despues: no vuelve a entrar.
    h_tc = entrar(api, fabrica, tecnico)
    assert api.get("/fincas/%d" % finca, headers=h_tc).status_code == 200

    r = api.patch("/asignaciones/%d" % asignacion, headers=h_dc,
                  json={"revocar": True})
    assert r.status_code == 200, r.text
    assert r.json()["vigente"] is False and r.json()["revocada_en"]

    assert api.get("/fincas/%d" % finca, headers=h_tc).status_code == 403
    assert fabrica.eventos("ASIGNACION_REVOCADA")


def test_no_se_revoca_dos_veces(api, fabrica, dc):
    _, h = dc
    a = _crear(api, h, fabrica.cuenta("TECNICO_CAMPO")).json()["id"]
    assert api.patch("/asignaciones/%d" % a, headers=h,
                     json={"revocar": True}).status_code == 200
    r = api.patch("/asignaciones/%d" % a, headers=h, json={"vence": _en(60)})
    assert r.status_code == 409
    assert r.json()["detail"] == "ya_revocada"


# ---------------------------------------------------------------------------
# Vencer y extender (HBAC-03, CU-07)
# ---------------------------------------------------------------------------

def test_una_vencida_no_da_acceso_y_se_renueva_extendiendola(api, fabrica, dc):
    _, h_dc = dc
    tecnico = fabrica.cuenta("TECNICO_CAMPO")
    vencida = fabrica.sql(
        "INSERT INTO asignaciones_zona (sujeto, zona, vence) "
        "VALUES (%s, 'VC', CURRENT_DATE - 1) RETURNING id",
        (tecnico["id"],))[0]["id"]
    finca = fabrica.finca(fabrica.cuenta("DUENO_FINCA"), "VC")
    h_tc = entrar(api, fabrica, tecnico)

    # Vencida: sin acceso, aunque la fila no este revocada.
    assert api.get("/fincas/%d" % finca, headers=h_tc).status_code == 403

    # No se crea otra encima: se extiende la que hay.
    r = _crear(api, h_dc, tecnico, "VC")
    assert r.status_code == 409 and "vencida" in r.json()["mensaje"]

    r = api.patch("/asignaciones/%d" % vencida, headers=h_dc,
                  json={"vence": _en(15)})
    assert r.status_code == 200, r.text
    assert r.json()["vigente"] is True
    assert api.get("/fincas/%d" % finca, headers=h_tc).status_code == 200


def test_cambiar_de_zona(api, fabrica, dc):
    _, h = dc
    tecnico = fabrica.cuenta("TECNICO_CAMPO")
    a = _crear(api, h, tecnico, "PC").json()["id"]
    otra = _crear(api, h, tecnico, "CN").json()["id"]
    # A una zona donde ya tiene otra abierta, no.
    assert api.patch("/asignaciones/%d" % a, headers=h,
                     json={"zona": "CN"}).status_code == 409
    r = api.patch("/asignaciones/%d" % a, headers=h, json={"zona": "ZN"})
    assert r.status_code == 200 and r.json()["zona"] == "ZN"
    assert otra != a


@pytest.mark.parametrize("cuerpo", [{}, {"revocar": True, "vence": "2027-01-01"}])
def test_un_cambio_sin_sentido_es_422(api, fabrica, dc, cuerpo):
    _, h = dc
    a = _crear(api, h, fabrica.cuenta("TECNICO_CAMPO")).json()["id"]
    assert api.patch("/asignaciones/%d" % a, headers=h,
                     json=cuerpo).status_code == 422


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "TECNICO_CAMPO",
                                 "VERIFICADOR"])
def test_solo_direccion_de_certificacion_modifica(api, fabrica, dc, rol):
    _, h_dc = dc
    a = _crear(api, h_dc, fabrica.cuenta("TECNICO_CAMPO"), "PC").json()["id"]
    quien = fabrica.cuenta(rol, zonas=("PC",))
    h = entrar(api, fabrica, quien, reautenticar=True)
    assert api.patch("/asignaciones/%d" % a, headers=h,
                     json={"revocar": True}).status_code == 403


# ---------------------------------------------------------------------------
# Leer (C1)
# ---------------------------------------------------------------------------

def test_el_tecnico_ve_las_de_su_zona_y_no_las_ajenas(api, fabrica, dc):
    _, h_dc = dc
    en_pc = _crear(api, h_dc, fabrica.cuenta("TECNICO_CAMPO"), "PC").json()["id"]
    en_cs = _crear(api, h_dc, fabrica.cuenta("TECNICO_CAMPO"), "CS").json()["id"]
    h = entrar(api, fabrica, fabrica.cuenta("TECNICO_CAMPO", zonas=("PC",)))

    assert api.get("/asignaciones/%d" % en_pc, headers=h).status_code == 200
    assert api.get("/asignaciones/%d" % en_cs, headers=h).status_code == 403
    ids = [a["id"] for a in api.get("/asignaciones", headers=h).json()["asignaciones"]]
    assert en_pc in ids and en_cs not in ids


def test_direccion_general_ve_todas(api, fabrica, dc):
    _, h_dc = dc
    a = _crear(api, h_dc, fabrica.cuenta("TECNICO_CAMPO"), "CS").json()["id"]
    h = entrar(api, fabrica, fabrica.cuenta("DIRECCION_GENERAL"))
    assert a in [x["id"] for x in
                 api.get("/asignaciones", headers=h).json()["asignaciones"]]


@pytest.mark.parametrize("rol", ["PERSONAL_ADMINISTRATIVO", "AUDITOR_EXTERNO",
                                 "DUENO_FINCA", "TERCERO_AUTORIZADO"])
def test_los_demas_no_leen(api, fabrica, rol):
    quien = fabrica.cuenta(rol)
    h = entrar(api, fabrica, quien)
    assert api.get("/asignaciones", headers=h).status_code == 403
    assert any(e["objeto"] == "O8:*" for e in
               fabrica.eventos(accion="ACCESO_DENEGADO", sujeto=quien["id"]))


def test_las_opciones_del_formulario_son_solo_para_quien_asigna(api, fabrica, dc):
    _, h_dc = dc
    r = api.get("/asignaciones/opciones", headers=h_dc)
    assert r.status_code == 200
    roles = {c["rol"] for c in r.json()["cuentas"]}
    assert roles <= {"TECNICO_CAMPO", "VERIFICADOR"}
    assert {"id", "nombre"} <= set(r.json()["zonas"][0])
    h = entrar(api, fabrica, fabrica.cuenta("DIRECCION_GENERAL"))
    assert api.get("/asignaciones/opciones", headers=h).status_code == 403
