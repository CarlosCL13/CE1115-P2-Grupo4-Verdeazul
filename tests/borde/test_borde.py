"""Lo que es del borde: paginas, cabeceras, CSRF, origen y como traduce las
respuestas del backend. El control de acceso lo prueban tests/matriz y las
pruebas de integracion; aqui se prueba que el borde no lo esconda ni lo
rompa.
"""

import pytest

from conftest import ORIGEN, ROLES

PAGINAS = ("/panel", "/fincas", "/periodos", "/mediciones", "/enmiendas",
           "/asignaciones", "/certificados", "/consentimientos", "/personas",
           "/cuentas", "/solicitudes", "/bitacora", "/clave")


# ---------------------------------------------------------------------------
# Paginas publicas y la raiz
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ruta", ["/entrar", "/verificar", "/static/estilo.css"])
def test_las_paginas_publicas_abren_sin_sesion(anonimo, ruta):
    assert anonimo.get(ruta).status_code == 200


def test_la_raiz_lleva_a_entrar_sin_sesion(anonimo):
    r = anonimo.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/entrar")


def test_la_raiz_lleva_al_panel_con_sesion(con_sesion):
    r = con_sesion.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/panel")


def test_una_pagina_privada_sin_sesion_lleva_a_entrar(anonimo, backend):
    backend.fijar("GET", r"/fincas", 401, {"detail": "sin_sesion"})
    r = anonimo.get("/fincas", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/entrar")


# ---------------------------------------------------------------------------
# Cabeceras de seguridad (D-04): Cloud Run no las pone, las pone el borde
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ruta", ["/entrar", "/verificar", "/static/estilo.css"])
def test_cabeceras_de_seguridad(anonimo, ruta):
    h = anonimo.get(ruta).headers
    assert h["strict-transport-security"].startswith("max-age=31536000")
    assert "script-src 'self'" in h["content-security-policy"]
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["x-frame-options"] == "DENY"
    assert h["x-content-type-options"] == "nosniff"


def test_las_paginas_con_sesion_no_se_guardan_en_cache(con_sesion):
    assert con_sesion.get("/panel").headers["cache-control"] == "no-store"


# ---------------------------------------------------------------------------
# Cada pagina se dibuja, para cada rol
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rol", ROLES)
def test_el_panel_se_dibuja_para_cada_rol(con_sesion, backend, rol):
    backend.rol = rol
    r = con_sesion.get("/panel")
    assert r.status_code == 200, r.text[:300]
    assert "Verificar un certificado" in r.text


@pytest.mark.parametrize("ruta", PAGINAS)
def test_cada_pagina_se_dibuja(con_sesion, ruta):
    r = con_sesion.get(ruta)
    assert r.status_code == 200, r.text[:300]


# ---------------------------------------------------------------------------
# Como traduce lo que dice el backend
# ---------------------------------------------------------------------------

def test_un_403_del_backend_se_ve_como_acceso_denegado(con_sesion, backend):
    backend.fijar("GET", r"/bitacora", 403, {"detail": "denegado"})
    r = con_sesion.get("/bitacora")
    assert r.status_code == 403
    assert "Acceso denegado" in r.text


def test_una_accion_grave_manda_a_reautenticar(con_sesion, backend, csrf):
    backend.fijar("POST", r"/enmiendas/\d+/aprobar", 401,
                  {"detail": "reautenticacion_requerida"})
    r = con_sesion.post("/enmiendas/7/aprobar", data={"csrf": csrf},
                        headers={"Origin": ORIGEN}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/reautenticar")


def test_con_el_backend_caido_responde_503(con_sesion, backend):
    backend.caido = True
    r = con_sesion.get("/fincas")
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# CSRF y origen: ningun formulario se acepta si no nacio aqui
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ruta", ["/enmiendas/7/aprobar", "/asignaciones/7/revocar",
                                  "/certificados/7/anular", "/periodos/7/cerrar"])
def test_un_formulario_con_csrf_falso_no_llega_al_backend(con_sesion, backend, ruta):
    r = con_sesion.post(ruta, data={"csrf": "falso", "motivo": "prueba larga"},
                        headers={"Origin": ORIGEN}, follow_redirects=False)
    assert r.status_code == 403
    assert not [ll for ll in backend.llamadas if ll[0] == "POST"]


def test_un_formulario_de_otro_origen_no_llega_al_backend(con_sesion, backend, csrf):
    r = con_sesion.post("/enmiendas/7/aprobar", data={"csrf": csrf},
                        headers={"Origin": "https://sitio-malo.example"},
                        follow_redirects=False)
    assert r.status_code == 403
    assert not [ll for ll in backend.llamadas if ll[0] == "POST"]


def test_un_formulario_valido_si_llega(con_sesion, backend, csrf):
    r = con_sesion.post("/enmiendas/7/devolver",
                        data={"csrf": csrf, "motivo": "Falta evidencia"},
                        headers={"Origin": ORIGEN}, follow_redirects=False)
    assert r.status_code == 303
    assert ("POST", "/enmiendas/7/devolver",
            {"motivo": "Falta evidencia"}) in backend.llamadas
