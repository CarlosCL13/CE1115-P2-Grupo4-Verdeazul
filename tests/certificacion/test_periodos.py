"""O2 Periodos de medicion."""

import pytest

from conftest import entrar


def test_seis_roles_leen_los_periodos(api, fabrica):
    periodo = fabrica.periodo()
    # La matriz da L sobre O2 a seis roles. PA y el tercero tienen "-" (el
    # contrato 04 decia siete, y la matriz manda).
    leen = ("DIRECCION_GENERAL", "DIRECCION_CERTIFICACION", "TECNICO_CAMPO",
            "VERIFICADOR", "DUENO_FINCA")
    for rol in leen:
        h = entrar(api, fabrica, fabrica.cuenta(rol))
        r = api.get("/periodos/%d" % periodo, headers=h)
        assert r.status_code == 200, rol
        assert r.json()["estado"] == "ABIERTO"
        assert api.get("/periodos", headers=h).status_code == 200
    for rol in ("PERSONAL_ADMINISTRATIVO", "TERCERO_AUTORIZADO"):
        h = entrar(api, fabrica, fabrica.cuenta(rol))
        assert api.get("/periodos", headers=h).status_code == 403, rol
        assert api.get("/periodos/%d" % periodo, headers=h
                       ).status_code == 403, rol


def test_c7_auditor_lee_periodos_solo_con_ventana(api, fabrica):
    periodo = fabrica.periodo()
    con, sin = fabrica.cuenta("AUDITOR_EXTERNO"), fabrica.cuenta("AUDITOR_EXTERNO")
    fabrica.ventana(con)
    assert api.get("/periodos/%d" % periodo, headers=entrar(
        api, fabrica, con)).status_code == 200
    assert api.get("/periodos/%d" % periodo, headers=entrar(
        api, fabrica, sin)).status_code == 403


def test_abrir_un_periodo_nuevo_pide_reautenticacion(api, fabrica):
    dc = fabrica.cuenta("DIRECCION_CERTIFICACION")
    sin = entrar(api, fabrica, dc)
    r = api.post("/periodos", headers=sin, json={"etiqueta": "2031-Q1"})
    assert r.status_code == 401
    assert r.json()["detail"] == "reautenticacion_requerida"


def test_direccion_de_certificacion_abre_y_cierra(api, fabrica):
    dc = fabrica.cuenta("DIRECCION_CERTIFICACION")
    h = entrar(api, fabrica, dc, reautenticar=True)
    etiqueta = "T-" + dc["usuario"][-8:]
    r = api.post("/periodos", headers=h, json={"etiqueta": etiqueta})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert api.post("/periodos", headers=h, json={"etiqueta": etiqueta}
                    ).json()["detail"] == "etiqueta_repetida"

    r = api.post("/periodos/%d/cerrar" % pid, headers=h)
    assert r.status_code == 200 and r.json()["estado"] == "CERRADO"
    assert api.post("/periodos/%d/cerrar" % pid, headers=h
                    ).json()["detail"] == "estado_invalido"

    r = api.post("/periodos/%d/abrir" % pid, headers=h)
    assert r.status_code == 200 and r.json()["estado"] == "ABIERTO"
    assert api.post("/periodos/%d/abrir" % pid, headers=h
                    ).json()["detail"] == "estado_invalido"
    for accion in ("PERIODO_ABIERTO", "PERIODO_CERRADO"):
        assert fabrica.eventos(accion, dc["id"])


def test_etiqueta_con_caracteres_raros_se_rechaza(api, fabrica):
    h = entrar(api, fabrica, fabrica.cuenta("DIRECCION_CERTIFICACION"),
               reautenticar=True)
    r = api.post("/periodos", headers=h, json={"etiqueta": "x'; DROP--"})
    assert r.status_code == 422


def test_no_cierra_con_mediciones_sin_aprobar(api, fabrica):
    dueno = fabrica.cuenta("DUENO_FINCA")
    finca, periodo = fabrica.finca(dueno), fabrica.periodo()
    tecnico = fabrica.cuenta("TECNICO_CAMPO", zonas=("PN",))
    pendiente = fabrica.medicion(finca, periodo, tecnico)
    h = entrar(api, fabrica, fabrica.cuenta("DIRECCION_CERTIFICACION"),
               reautenticar=True)
    r = api.post("/periodos/%d/cerrar" % periodo, headers=h)
    assert r.status_code == 409
    assert r.json()["detail"] == "mediciones_pendientes"
    assert r.json()["pendientes"] == 1

    # Decidida (aqui devuelta), ya no bloquea.
    revisor = fabrica.cuenta("VERIFICADOR", zonas=("PN",))
    fabrica.sql("UPDATE mediciones SET estado = 'DEVUELTA', revisada_por = %s, "
                "motivo_devolucion = 'x' WHERE id = %s",
                (revisor["id"], pendiente))
    assert api.post("/periodos/%d/cerrar" % periodo, headers=h
                    ).status_code == 200


@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "PERSONAL_ADMINISTRATIVO",
                                 "TECNICO_CAMPO", "VERIFICADOR",
                                 "AUDITOR_EXTERNO", "DUENO_FINCA"])
def test_solo_certificacion_abre_y_cierra(api, fabrica, rol):
    periodo = fabrica.periodo()
    cuenta = fabrica.cuenta(rol)
    h = entrar(api, fabrica, cuenta, reautenticar=True)
    assert api.post("/periodos", headers=h, json={"etiqueta": "NO-" + rol[:5]}
                    ).status_code == 403
    assert api.post("/periodos/%d/cerrar" % periodo, headers=h
                    ).status_code == 403
    assert fabrica.eventos("ACCESO_DENEGADO", cuenta["id"])
    assert fabrica.sql("SELECT estado::text AS e FROM periodos_medicion "
                       "WHERE id = %s", (periodo,))[0]["e"] == "ABIERTO"
