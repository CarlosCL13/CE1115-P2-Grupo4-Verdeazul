"""O1 Catalogo de fincas. Las celdas de la matriz, una por una."""

import pytest

from conftest import entrar

CUADRADO = [[-84.10, 9.90], [-84.00, 9.90], [-84.00, 10.00],
            [-84.10, 10.00], [-84.10, 9.90]]


def _ids(r):
    return {f["id"] for f in r.json()["fincas"]}


def test_listado_se_filtra_segun_el_rol(api, fabrica):
    dueno, otro = fabrica.cuenta("DUENO_FINCA"), fabrica.cuenta("DUENO_FINCA")
    suya, ajena = fabrica.finca(dueno, "PN"), fabrica.finca(otro, "CS")
    tecnico = fabrica.cuenta("TECNICO_CAMPO", zonas=("PN",))

    d = api.get("/fincas", headers=entrar(api, fabrica, dueno))
    assert suya in _ids(d) and ajena not in _ids(d)
    t = api.get("/fincas", headers=entrar(api, fabrica, tecnico))
    assert suya in _ids(t) and ajena not in _ids(t)
    g = api.get("/fincas", headers=entrar(
        api, fabrica, fabrica.cuenta("DIRECCION_GENERAL")))
    assert {suya, ajena} <= _ids(g)


def test_tercero_autorizado_no_tiene_nada_en_o1(api, fabrica):
    tercero = fabrica.cuenta("TERCERO_AUTORIZADO")
    r = api.get("/fincas", headers=entrar(api, fabrica, tercero))
    assert r.status_code == 403
    assert fabrica.eventos("ACCESO_DENEGADO", tercero["id"])


def test_c8_el_dueno_no_ve_la_finca_ajena(api, fabrica):
    dueno, otro = fabrica.cuenta("DUENO_FINCA"), fabrica.cuenta("DUENO_FINCA")
    ajena = fabrica.finca(otro)
    h = entrar(api, fabrica, dueno)
    assert api.get("/fincas/%d" % ajena, headers=h).status_code == 403
    assert api.get("/fincas/%d" % fabrica.finca(dueno), headers=h
                   ).status_code == 200


def test_c1_el_tecnico_solo_ve_su_zona(api, fabrica):
    dueno = fabrica.cuenta("DUENO_FINCA")
    en_zona, fuera = fabrica.finca(dueno, "PN"), fabrica.finca(dueno, "CS")
    h = entrar(api, fabrica, fabrica.cuenta("TECNICO_CAMPO", zonas=("PN",)))
    assert api.get("/fincas/%d" % en_zona, headers=h).status_code == 200
    assert api.get("/fincas/%d" % fuera, headers=h).status_code == 403


def test_c7_el_auditor_solo_ve_dentro_de_su_ventana(api, fabrica):
    finca = fabrica.finca(fabrica.cuenta("DUENO_FINCA"))
    dentro, fuera, sin = (fabrica.cuenta("AUDITOR_EXTERNO") for _ in range(3))
    fabrica.ventana(dentro)
    fabrica.ventana(fuera, dias_desde=-10, dias_hasta=-5)
    assert api.get("/fincas/%d" % finca, headers=entrar(
        api, fabrica, dentro)).status_code == 200
    assert api.get("/fincas/%d" % finca, headers=entrar(
        api, fabrica, fuera)).status_code == 403
    assert api.get("/fincas", headers=entrar(
        api, fabrica, sin)).status_code == 403


def test_inexistente_no_delata_ids_a_quien_no_puede_verlos(api, fabrica):
    tecnico = entrar(api, fabrica, fabrica.cuenta("TECNICO_CAMPO", zonas=("PN",)))
    general = entrar(api, fabrica, fabrica.cuenta("DIRECCION_GENERAL"))
    assert api.get("/fincas/99999999", headers=tecnico).status_code == 403
    assert api.get("/fincas/99999999", headers=general).status_code == 404


def test_administrativo_registra_una_finca_con_poligono(api, fabrica):
    admin = fabrica.cuenta("PERSONAL_ADMINISTRATIVO")
    dueno = fabrica.cuenta("DUENO_FINCA")
    h = entrar(api, fabrica, admin)
    r = api.post("/fincas", headers=h, json={
        "nombre": "Nueva", "zona": "PN", "propietario": dueno["id"],
        "poligono": {"type": "Polygon", "coordinates": [CUADRADO]}})
    assert r.status_code == 201, r.text
    ver = api.get("/fincas/%d" % r.json()["id"], headers=h).json()
    assert ver["poligono"]["type"] == "Polygon"
    assert fabrica.eventos("FINCA_REGISTRADA", admin["id"])


@pytest.mark.parametrize("anillo,codigo", [
    # Lazo: el anillo se cruza consigo mismo. Es lo que ST_IsValid atrapa.
    ([[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]], "poligono_invalido"),
    # Sin cerrar.
    ([[0, 0], [1, 0], [1, 1], [0, 1]], "poligono_invalido"),
    # Fuera de rango.
    ([[0, 0], [200, 0], [200, 1], [0, 1], [0, 0]], "poligono_invalido"),
    # Menos de cuatro puntos.
    ([[0, 0], [1, 0], [0, 0]], "poligono_invalido"),
])
def test_poligonos_invalidos_se_rechazan(api, fabrica, anillo, codigo):
    h = entrar(api, fabrica, fabrica.cuenta("PERSONAL_ADMINISTRATIVO"))
    dueno = fabrica.cuenta("DUENO_FINCA")
    r = api.post("/fincas", headers=h, json={
        "nombre": "Mala", "zona": "PN", "propietario": dueno["id"],
        "poligono": {"type": "Polygon", "coordinates": [anillo]}})
    assert r.status_code == 422 and r.json()["detail"] == codigo


def test_propietario_y_zona_se_validan(api, fabrica):
    h = entrar(api, fabrica, fabrica.cuenta("PERSONAL_ADMINISTRATIVO"))
    tecnico = fabrica.cuenta("TECNICO_CAMPO")
    base = {"nombre": "X1", "poligono": {"type": "Polygon",
                                         "coordinates": [CUADRADO]}}
    r = api.post("/fincas", headers=h, json={
        **base, "zona": "PN", "propietario": tecnico["id"]})
    assert r.json()["detail"] == "propietario_invalido"
    r = api.post("/fincas", headers=h, json={
        **base, "zona": "ZZ", "propietario":
        fabrica.cuenta("DUENO_FINCA")["id"]})
    assert r.json()["detail"] == "zona_inexistente"


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "DIRECCION_CERTIFICACION",
                                 "TECNICO_CAMPO", "VERIFICADOR",
                                 "AUDITOR_EXTERNO", "DUENO_FINCA",
                                 "TERCERO_AUTORIZADO"])
def test_solo_el_administrativo_crea_y_modifica(api, fabrica, rol):
    dueno = fabrica.cuenta("DUENO_FINCA")
    finca = fabrica.finca(dueno)
    h = entrar(api, fabrica, fabrica.cuenta(rol))
    r = api.post("/fincas", headers=h, json={
        "nombre": "Intruso", "zona": "PN", "propietario": dueno["id"],
        "poligono": {"type": "Polygon", "coordinates": [CUADRADO]}})
    assert r.status_code == 403
    r = api.patch("/fincas/%d" % finca, headers=h, json={"nombre": "Otro"})
    assert r.status_code == 403


def test_correccion_deja_evento_y_cambia_la_finca(api, fabrica):
    admin = fabrica.cuenta("PERSONAL_ADMINISTRATIVO")
    finca = fabrica.finca(fabrica.cuenta("DUENO_FINCA"))
    h = entrar(api, fabrica, admin)
    r = api.patch("/fincas/%d" % finca, headers=h, json={
        "nombre": "Renombrada",
        "poligono": {"type": "Polygon", "coordinates": [CUADRADO]}})
    assert r.status_code == 200, r.text
    assert api.get("/fincas/%d" % finca, headers=h).json()["nombre"] == \
        "Renombrada"
    evento = fabrica.eventos("FINCA_CORREGIDA", admin["id"])[-1]
    assert evento["detalle"]["campos"] == ["nombre", "poligono"]
    assert api.patch("/fincas/%d" % finca, headers=h, json={}
                     ).status_code == 422


def test_sin_sesion_es_401(api):
    assert api.get("/fincas").status_code == 401
