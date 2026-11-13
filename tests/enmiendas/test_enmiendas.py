"""O4 Enmiendas contra la matriz, con un OPA real y una base desechable.

    C11  el tecnico pide solo sobre lo suyo y con el periodo cerrado
    C4   quien revisa no es quien pidio
    C5   quien cierra no es ni quien pidio ni quien reviso, y solo REVISADA
    C1, C7, C8 en las lecturas
"""

import pytest

from conftest import enmienda, entrar


def _denegado(fabrica, cuenta, objeto):
    return any(e["objeto"] == objeto for e in
               fabrica.eventos(accion="ACCESO_DENEGADO", sujeto=cuenta["id"]))


# ---------------------------------------------------------------------------
# Solicitar (C11)
# ---------------------------------------------------------------------------

def test_el_tecnico_pide_sobre_lo_suyo_con_el_periodo_cerrado(
        api, fabrica, escenario):
    h = entrar(api, fabrica, escenario["tecnico"])
    r = api.post("/enmiendas", headers=h, json={
        "medicion": escenario["medicion"],
        "justificacion": "El equipo estaba descalibrado esa semana."})
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "SOLICITADA"

    ver = api.get("/enmiendas/%d" % r.json()["id"], headers=h).json()
    assert ver["solicitante"] == escenario["tecnico"]["id"]
    assert ver["medicion"] == escenario["medicion"]
    eventos = fabrica.eventos("ENMIENDA_SOLICITADA", escenario["tecnico"]["id"])
    assert eventos and "justificacion" not in eventos[0]["detalle"]


def test_c11_con_el_periodo_abierto_no_se_pide(api, fabrica, escenario):
    abierto = fabrica.periodo("ABIERTO")
    medicion = fabrica.medicion(escenario["finca"], abierto,
                                escenario["tecnico"])
    h = entrar(api, fabrica, escenario["tecnico"])
    r = api.post("/enmiendas", headers=h, json={
        "medicion": medicion, "justificacion": "Todavia esta abierto."})
    assert r.status_code == 403
    assert _denegado(fabrica, escenario["tecnico"], "O4:nueva")


def test_c11_no_se_pide_sobre_lo_ajeno(api, fabrica, escenario):
    otro = fabrica.cuenta("TECNICO_CAMPO", zonas=("PN",))
    h = entrar(api, fabrica, otro)
    r = api.post("/enmiendas", headers=h, json={
        "medicion": escenario["medicion"],
        "justificacion": "No es mia pero la quiero cambiar."})
    assert r.status_code == 403


@pytest.mark.parametrize("rol", ["VERIFICADOR", "DIRECCION_CERTIFICACION",
                                 "DIRECCION_GENERAL", "DUENO_FINCA"])
def test_solo_el_tecnico_pide(api, fabrica, escenario, rol):
    h = entrar(api, fabrica, fabrica.cuenta(rol, zonas=("PN",)))
    r = api.post("/enmiendas", headers=h, json={
        "medicion": escenario["medicion"], "justificacion": "No me toca pedirla."})
    assert r.status_code == 403


def test_una_sola_enmienda_abierta_por_medicion(api, fabrica, escenario):
    enmienda(fabrica, escenario["medicion"], escenario["tecnico"])
    h = entrar(api, fabrica, escenario["tecnico"])
    r = api.post("/enmiendas", headers=h, json={
        "medicion": escenario["medicion"], "justificacion": "Otra correccion mas."})
    assert r.status_code == 409
    assert r.json()["detail"] == "enmienda_abierta"


def test_justificacion_corta_es_422(api, fabrica, escenario):
    h = entrar(api, fabrica, escenario["tecnico"])
    r = api.post("/enmiendas", headers=h, json={
        "medicion": escenario["medicion"], "justificacion": "   corta    "})
    assert r.status_code == 422


def test_medicion_inexistente(api, fabrica, escenario):
    h = entrar(api, fabrica, escenario["tecnico"])
    r = api.post("/enmiendas", headers=h, json={
        "medicion": 999999, "justificacion": "No existe esta medicion."})
    # El tecnico no puede crear sin condicion: no se le confirma si existe.
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Revisar (C4)
# ---------------------------------------------------------------------------

def test_otro_verificador_aprueba(api, fabrica, escenario):
    e = enmienda(fabrica, escenario["medicion"], escenario["tecnico"])
    h = entrar(api, fabrica, escenario["ver2"], reautenticar=True)
    r = api.post("/enmiendas/%d/aprobar" % e, headers=h)
    assert r.status_code == 200, r.text
    ver = api.get("/enmiendas/%d" % e, headers=h).json()
    assert ver["estado"] == "REVISADA"
    assert ver["revisor"] == escenario["ver2"]["id"]
    assert fabrica.eventos("ENMIENDA_APROBADA", escenario["ver2"]["id"])


def test_aprobar_pide_reautenticacion(api, fabrica, escenario):
    e = enmienda(fabrica, escenario["medicion"], escenario["tecnico"])
    h = entrar(api, fabrica, escenario["ver2"])
    r = api.post("/enmiendas/%d/aprobar" % e, headers=h)
    assert r.status_code == 401
    assert r.json()["detail"] == "reautenticacion_requerida"


def test_c4_quien_pidio_no_revisa(api, fabrica, escenario):
    # Una persona puede ser tecnico y verificador (minuta A1). Se simula con
    # una enmienda cuyo solicitante es el mismo verificador.
    e = enmienda(fabrica, escenario["medicion"], escenario["ver2"])
    h = entrar(api, fabrica, escenario["ver2"], reautenticar=True)
    assert api.post("/enmiendas/%d/aprobar" % e, headers=h).status_code == 403
    assert api.post("/enmiendas/%d/devolver" % e, headers=h,
                    json={"motivo": "No corresponde"}).status_code == 403
    assert _denegado(fabrica, escenario["ver2"], "O4:%d" % e)


def test_devolver_guarda_el_motivo_en_la_bitacora(api, fabrica, escenario):
    e = enmienda(fabrica, escenario["medicion"], escenario["tecnico"])
    h = entrar(api, fabrica, escenario["ver2"])
    r = api.post("/enmiendas/%d/devolver" % e, headers=h,
                 json={"motivo": "Falta la evidencia de campo."})
    assert r.status_code == 200, r.text
    assert api.get("/enmiendas/%d" % e, headers=h).json()["estado"] == "DEVUELTA"
    evento = fabrica.eventos("ENMIENDA_DEVUELTA", escenario["ver2"]["id"])[0]
    assert evento["detalle"]["motivo"] == "Falta la evidencia de campo."


def test_no_se_revisa_dos_veces(api, fabrica, escenario):
    e = enmienda(fabrica, escenario["medicion"], escenario["tecnico"])
    h = entrar(api, fabrica, escenario["ver2"], reautenticar=True)
    assert api.post("/enmiendas/%d/aprobar" % e, headers=h).status_code == 200
    r = api.post("/enmiendas/%d/aprobar" % e, headers=h)
    assert r.status_code == 409
    assert r.json()["detail"] == "estado_invalido"


@pytest.mark.parametrize("rol", ["TECNICO_CAMPO", "DIRECCION_CERTIFICACION",
                                 "DIRECCION_GENERAL"])
def test_solo_el_verificador_revisa(api, fabrica, escenario, rol):
    e = enmienda(fabrica, escenario["medicion"], escenario["tecnico"])
    h = entrar(api, fabrica, fabrica.cuenta(rol, zonas=("PN",)),
               reautenticar=True)
    assert api.post("/enmiendas/%d/aprobar" % e, headers=h).status_code == 403


# ---------------------------------------------------------------------------
# Cerrar (C5)
# ---------------------------------------------------------------------------

def test_direccion_de_certificacion_cierra_lo_revisado(api, fabrica, escenario):
    e = enmienda(fabrica, escenario["medicion"], escenario["tecnico"],
                 "REVISADA", escenario["ver2"])
    dc = fabrica.cuenta("DIRECCION_CERTIFICACION")
    h = entrar(api, fabrica, dc, reautenticar=True)
    r = api.post("/enmiendas/%d/cerrar" % e, headers=h)
    assert r.status_code == 200, r.text
    ver = api.get("/enmiendas/%d" % e, headers=h).json()
    assert ver["estado"] == "CERRADA" and ver["cerrada_por"] == dc["id"]
    # Tres personas distintas.
    assert len({ver["solicitante"], ver["revisor"], ver["cerrada_por"]}) == 3


def test_c5_no_se_cierra_lo_que_nadie_reviso(api, fabrica, escenario):
    e = enmienda(fabrica, escenario["medicion"], escenario["tecnico"])
    dc = fabrica.cuenta("DIRECCION_CERTIFICACION")
    h = entrar(api, fabrica, dc, reautenticar=True)
    assert api.post("/enmiendas/%d/cerrar" % e, headers=h).status_code == 403
    assert _denegado(fabrica, dc, "O4:%d" % e)


def test_c5_quien_reviso_no_cierra(api, fabrica, escenario):
    dc = fabrica.cuenta("DIRECCION_CERTIFICACION")
    e = enmienda(fabrica, escenario["medicion"], escenario["tecnico"],
                 "REVISADA", dc)
    h = entrar(api, fabrica, dc, reautenticar=True)
    assert api.post("/enmiendas/%d/cerrar" % e, headers=h).status_code == 403


def test_c5_quien_pidio_no_cierra(api, fabrica, escenario):
    dc = fabrica.cuenta("DIRECCION_CERTIFICACION")
    e = enmienda(fabrica, escenario["medicion"], dc, "REVISADA",
                 escenario["ver2"])
    h = entrar(api, fabrica, dc, reautenticar=True)
    assert api.post("/enmiendas/%d/cerrar" % e, headers=h).status_code == 403


def test_cerrar_pide_reautenticacion(api, fabrica, escenario):
    e = enmienda(fabrica, escenario["medicion"], escenario["tecnico"],
                 "REVISADA", escenario["ver2"])
    h = entrar(api, fabrica, fabrica.cuenta("DIRECCION_CERTIFICACION"))
    assert api.post("/enmiendas/%d/cerrar" % e, headers=h).status_code == 401


def test_el_verificador_no_cierra(api, fabrica, escenario):
    e = enmienda(fabrica, escenario["medicion"], escenario["tecnico"],
                 "REVISADA", escenario["ver1"])
    h = entrar(api, fabrica, escenario["ver2"], reautenticar=True)
    assert api.post("/enmiendas/%d/cerrar" % e, headers=h).status_code == 403


# ---------------------------------------------------------------------------
# Leer (C1, C7, C8) y exportar
# ---------------------------------------------------------------------------

def test_el_dueno_ve_las_de_su_finca_y_no_las_ajenas(api, fabrica, escenario):
    e = enmienda(fabrica, escenario["medicion"], escenario["tecnico"])
    propio = entrar(api, fabrica, escenario["dueno"])
    ajeno = entrar(api, fabrica, fabrica.cuenta("DUENO_FINCA"))
    assert api.get("/enmiendas/%d" % e, headers=propio).status_code == 200
    assert api.get("/enmiendas/%d" % e, headers=ajeno).status_code == 403
    ids = [x["id"] for x in api.get("/enmiendas", headers=ajeno).json()["enmiendas"]]
    assert e not in ids


def test_el_tecnico_ve_solo_su_zona(api, fabrica, escenario):
    e = enmienda(fabrica, escenario["medicion"], escenario["tecnico"])
    de_otra_zona = entrar(api, fabrica,
                          fabrica.cuenta("TECNICO_CAMPO", zonas=("CS",)))
    assert api.get("/enmiendas/%d" % e, headers=de_otra_zona).status_code == 403


def test_el_administrativo_no_tiene_nada_sobre_o4(api, fabrica, escenario):
    pa = fabrica.cuenta("PERSONAL_ADMINISTRATIVO")
    h = entrar(api, fabrica, pa)
    assert api.get("/enmiendas", headers=h).status_code == 403
    assert _denegado(fabrica, pa, "O4:*")


def test_el_auditor_en_su_ventana_lee_y_exporta(api, fabrica, escenario):
    enmienda(fabrica, escenario["medicion"], escenario["tecnico"])
    auditor = fabrica.cuenta("AUDITOR_EXTERNO")
    fabrica.ventana(auditor)
    h = entrar(api, fabrica, auditor)
    assert api.get("/enmiendas", headers=h).status_code == 200
    r = api.get("/enmiendas/exportar", headers=h)
    assert r.status_code == 200
    assert r.text.startswith("id,medicion,finca,periodo,solicitante,")


def test_el_auditor_sin_ventana_no_ve_nada(api, fabrica):
    h = entrar(api, fabrica, fabrica.cuenta("AUDITOR_EXTERNO"))
    assert api.get("/enmiendas", headers=h).status_code == 403
    assert api.get("/enmiendas/exportar", headers=h).status_code == 403


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "DIRECCION_CERTIFICACION",
                                 "VERIFICADOR"])
def test_solo_el_auditor_exporta(api, fabrica, rol):
    h = entrar(api, fabrica, fabrica.cuenta(rol))
    assert api.get("/enmiendas/exportar", headers=h).status_code == 403


def test_filtro_por_estado(api, fabrica, escenario):
    e = enmienda(fabrica, escenario["medicion"], escenario["tecnico"],
                 "REVISADA", escenario["ver1"])
    h = entrar(api, fabrica, fabrica.cuenta("DIRECCION_GENERAL"))
    revisadas = api.get("/enmiendas", headers=h,
                        params={"estado": "REVISADA"}).json()["enmiendas"]
    assert e in [x["id"] for x in revisadas]
    assert all(x["estado"] == "REVISADA" for x in revisadas)
    assert api.get("/enmiendas", headers=h,
                   params={"estado": "BORRADA"}).status_code == 422
