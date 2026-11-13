"""O11 bitacora contra la matriz, con un OPA real y bases desechables.

    DG, DC     L, X
    PA         L            (exportar: 403)
    AE         L.C7, X.C7   (sin ventana vigente: 403)
    los demas  nada
"""

import datetime

import psycopg
import pytest

from conftest import entrar


def _cuenta_y_entrar(api, fabrica, rol):
    cuenta = fabrica.cuenta(rol)
    return cuenta, entrar(api, fabrica, cuenta)


def _denegado_registrado(fabrica, cuenta, operacion):
    eventos = fabrica.eventos(accion="ACCESO_DENEGADO", sujeto=cuenta["id"])
    return any(e["objeto"] == "O11:*" and e["detalle"]["operacion"] == operacion
               for e in eventos)


# ---------------------------------------------------------------------------
# Quien puede leer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "DIRECCION_CERTIFICACION",
                                 "PERSONAL_ADMINISTRATIVO"])
def test_los_roles_con_L_leen_y_la_consulta_queda_registrada(
        api, fabrica, bitacora, rol):
    accion = bitacora.accion_unica()
    bitacora.evento(accion=accion, objeto="O3:7")
    cuenta, cabecera = _cuenta_y_entrar(api, fabrica, rol)

    r = api.get("/bitacora", headers=cabecera, params={"accion": accion})
    assert r.status_code == 200, r.text
    eventos = r.json()["eventos"]
    assert [e["accion"] for e in eventos] == [accion]
    assert eventos[0]["objeto"] == "O3:7"
    assert len(eventos[0]["eslabon"]) == 64
    assert "pendientes_de_transmitir" in r.json()

    # Quien mira la bitacora tambien queda en la bitacora.
    consultas = fabrica.eventos(accion="BITACORA_CONSULTADA", sujeto=cuenta["id"])
    assert len(consultas) == 1
    assert consultas[0]["detalle"]["filtros"] == {"accion": accion}


@pytest.mark.parametrize("rol", ["TECNICO_CAMPO", "VERIFICADOR", "DUENO_FINCA",
                                 "TERCERO_AUTORIZADO"])
def test_los_demas_roles_no_leen_ni_exportan(api, fabrica, rol):
    cuenta, cabecera = _cuenta_y_entrar(api, fabrica, rol)
    assert api.get("/bitacora", headers=cabecera).status_code == 403
    assert api.get("/bitacora/exportar", headers=cabecera).status_code == 403
    assert _denegado_registrado(fabrica, cuenta, "L")
    assert _denegado_registrado(fabrica, cuenta, "X")


def test_sin_sesion_es_401(api):
    assert api.get("/bitacora").status_code == 401


# ---------------------------------------------------------------------------
# Exportar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rol", ["DIRECCION_GENERAL", "DIRECCION_CERTIFICACION"])
def test_dg_y_dc_exportan_en_el_orden_de_la_cadena(api, fabrica, bitacora, rol):
    accion = bitacora.accion_unica()
    bitacora.evento(accion=accion, objeto="O1:1")
    bitacora.evento(accion=accion, objeto="O1:2", detalle={"finca": "2"})
    cuenta, cabecera = _cuenta_y_entrar(api, fabrica, rol)

    r = api.get("/bitacora/exportar", headers=cabecera, params={"accion": accion})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    lineas = r.text.strip().split("\n")
    assert lineas[0] == ("secuencia,id,momento,accion,sujeto,objeto,resultado,"
                         "motivo,detalle,eslabon")
    # Del mas viejo al mas nuevo, como se encadenan.
    assert ",O1:1," in lineas[1] and ",O1:2," in lineas[2]
    assert len(fabrica.eventos(accion="BITACORA_EXPORTADA",
                               sujeto=cuenta["id"])) == 1


def test_el_administrativo_lee_pero_no_exporta(api, fabrica):
    cuenta, cabecera = _cuenta_y_entrar(api, fabrica, "PERSONAL_ADMINISTRATIVO")
    assert api.get("/bitacora", headers=cabecera).status_code == 200
    assert api.get("/bitacora/exportar", headers=cabecera).status_code == 403
    assert _denegado_registrado(fabrica, cuenta, "X")


# ---------------------------------------------------------------------------
# C7: el auditor, solo dentro de su ventana
# ---------------------------------------------------------------------------

def test_el_auditor_en_su_ventana_lee_y_exporta(api, fabrica, bitacora):
    accion = bitacora.accion_unica()
    bitacora.evento(accion=accion)
    auditor = fabrica.cuenta("AUDITOR_EXTERNO")
    fabrica.ventana(auditor, dias_desde=-1, dias_hasta=1)
    cabecera = entrar(api, fabrica, auditor)

    r = api.get("/bitacora", headers=cabecera, params={"accion": accion})
    assert r.status_code == 200, r.text
    assert len(r.json()["eventos"]) == 1
    assert api.get("/bitacora/exportar", headers=cabecera,
                   params={"accion": accion}).status_code == 200


@pytest.mark.parametrize("desde, hasta", [(-30, -1), (1, 30)])
def test_el_auditor_fuera_de_su_ventana_no_tiene_permiso(
        api, fabrica, desde, hasta):
    auditor = fabrica.cuenta("AUDITOR_EXTERNO")
    fabrica.ventana(auditor, dias_desde=desde, dias_hasta=hasta)
    cabecera = entrar(api, fabrica, auditor)
    assert api.get("/bitacora", headers=cabecera).status_code == 403
    assert api.get("/bitacora/exportar", headers=cabecera).status_code == 403
    assert _denegado_registrado(fabrica, auditor, "L")


def test_el_auditor_sin_ventana_no_tiene_permiso(api, fabrica):
    auditor, cabecera = _cuenta_y_entrar(api, fabrica, "AUDITOR_EXTERNO")
    assert api.get("/bitacora", headers=cabecera).status_code == 403


# ---------------------------------------------------------------------------
# Filtros y paginas
# ---------------------------------------------------------------------------

def test_filtros(api, fabrica, bitacora, hoy):
    accion = bitacora.accion_unica()
    ayer = datetime.datetime.combine(hoy - datetime.timedelta(days=1),
                                     datetime.time(12), datetime.timezone.utc)
    bitacora.evento(accion=accion, sujeto="901", objeto="O3:1")
    bitacora.evento(accion=accion, sujeto="902", objeto="O5:1",
                    resultado="DENEGADO", motivo="C6")
    bitacora.evento(accion=accion, sujeto="901", objeto="O3:2", momento=ayer)
    _, cabecera = _cuenta_y_entrar(api, fabrica, "DIRECCION_GENERAL")

    def objetos(**filtros):
        r = api.get("/bitacora", headers=cabecera,
                    params={"accion": accion, **filtros})
        assert r.status_code == 200, r.text
        return sorted(e["objeto"] for e in r.json()["eventos"])

    assert objetos() == ["O3:1", "O3:2", "O5:1"]
    assert objetos(sujeto="901") == ["O3:1", "O3:2"]
    assert objetos(tipo="O5") == ["O5:1"]
    assert objetos(resultado="DENEGADO") == ["O5:1"]
    assert objetos(desde=hoy.isoformat()) == ["O3:1", "O5:1"]
    assert objetos(hasta=(hoy - datetime.timedelta(days=1)).isoformat()) == ["O3:2"]


def test_paginas(api, fabrica, bitacora):
    accion = bitacora.accion_unica()
    for i in range(3):
        bitacora.evento(accion=accion, objeto="O3:%d" % i)
    _, cabecera = _cuenta_y_entrar(api, fabrica, "DIRECCION_GENERAL")

    vistos, antes = [], None
    for _ in range(4):
        params = {"accion": accion, "limite": 2}
        if antes:
            params["antes"] = antes
        datos = api.get("/bitacora", headers=cabecera, params=params).json()
        vistos += [e["objeto"] for e in datos["eventos"]]
        antes = datos["siguiente"]
        if antes is None:
            break
    # Del mas nuevo al mas viejo, sin repetir ni saltar.
    assert vistos == ["O3:2", "O3:1", "O3:0"]


@pytest.mark.parametrize("filtros", [
    {"resultado": "OTRO"},
    {"tipo": "O12"},
    {"tipo": "O1%"},
    {"accion": "X' OR '1'='1"},
    {"sujeto": "1; DROP TABLE eventos"},
    {"desde": "ayer"},
    {"limite": 1000},
])
def test_un_filtro_mal_formado_es_422(api, fabrica, filtros):
    _, cabecera = _cuenta_y_entrar(api, fabrica, "DIRECCION_GENERAL")
    assert api.get("/bitacora", headers=cabecera,
                   params=filtros).status_code == 422


def test_rango_invertido_es_422(api, fabrica, hoy):
    _, cabecera = _cuenta_y_entrar(api, fabrica, "DIRECCION_GENERAL")
    r = api.get("/bitacora", headers=cabecera, params={
        "desde": hoy.isoformat(),
        "hasta": (hoy - datetime.timedelta(days=1)).isoformat()})
    assert r.status_code == 422
    assert r.json()["detail"] == "rango_invalido"


# ---------------------------------------------------------------------------
# La frontera F6: la API lee la bitacora y no puede escribirla
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sentencia", [
    "INSERT INTO eventos (id, accion, sujeto, objeto, resultado, eslabon) "
    "VALUES (gen_random_uuid(), 'FALSO', '1', 'O3:1', 'PERMITIDO', 'x')",
    "UPDATE eventos SET accion = 'ALTERADO'",
    "DELETE FROM eventos",
])
def test_log_reader_no_puede_escribir(grupo_bitacora, sentencia):
    with grupo_bitacora.connection() as con:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            con.execute(sentencia)
