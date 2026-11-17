"""Pantallas de autorizaciones a terceros (O7).

No deciden nada. El formulario de autorizar se dibuja para quien tiene C
(dueno de finca y Personal Administrativo); extender y revocar, solo para el
dueno, que es el unico con M. Si otro rol manda el formulario a mano, el
backend responde 403 y el intento queda en la bitacora.

Un formulario HTML solo sabe GET y POST, asi que el PATCH del backend se
alcanza desde dos POST del borde: /extender y /revocar.
"""

import urllib.parse

from fastapi import APIRouter, Form, Query, Request

from app.web import (FalloDelBackend, comprobar_csrf, ir, mensaje_de, pagina,
                     pedir, sesion)

router = APIRouter()

PUEDEN_AUTORIZAR = ("DUENO_FINCA", "PERSONAL_ADMINISTRATIVO")


def _volver(error: FalloDelBackend | None = None, ok: str | None = None):
    if error is not None:
        return ir("/consentimientos?error=" +
                  urllib.parse.quote(mensaje_de(error)[:200]))
    return ir("/consentimientos?ok=" + urllib.parse.quote(ok or ""))


@router.get("/consentimientos")
def consentimientos(request: Request, error: str = Query("", max_length=200),
                    ok: str = Query("", max_length=200),
                    vigentes: str = Query("", max_length=2)):
    datos = pedir(request, "GET", "/consentimientos",
                  params={"solo_vigentes": "true"} if vigentes else None).json()
    datos_sesion = sesion(request)
    opciones = None
    if datos_sesion and datos_sesion["rol"] in PUEDEN_AUTORIZAR:
        opciones = pedir(request, "GET", "/consentimientos/opciones").json()
    return pagina(request, "consentimientos/lista.html",
                  consentimientos=datos["consentimientos"], opciones=opciones,
                  solo_vigentes=bool(vigentes), error=error or None,
                  ok=ok or None, datos_sesion=datos_sesion)


@router.post("/consentimientos")
def consentimiento_nuevo(request: Request, csrf: str = Form(""),
                         finca: int = Form(gt=0), tercero: int = Form(gt=0),
                         vence: str = Form(max_length=10)):
    comprobar_csrf(request, csrf)
    try:
        r = pedir(request, "POST", "/consentimientos", json={
            "finca": finca, "tercero": tercero, "vence": vence},
            volver_a="/consentimientos")
    except FalloDelBackend as error:
        return _volver(error)
    k = r.json()
    return _volver(ok="Autorización %d registrada: %s puede ver los "
                      "certificados de %s hasta %s."
                   % (k["id"], k["tercero_usuario"], k["finca_nombre"],
                      k["vence"]))


@router.post("/consentimientos/{consentimiento}/extender")
def consentimiento_extender(request: Request, consentimiento: int,
                            csrf: str = Form(""),
                            vence: str = Form(max_length=10)):
    comprobar_csrf(request, csrf)
    try:
        pedir(request, "PATCH", "/consentimientos/%d" % consentimiento,
              json={"vence": vence}, volver_a="/consentimientos")
    except FalloDelBackend as error:
        return _volver(error)
    return _volver(ok="Autorización %d extendida hasta %s."
                      % (consentimiento, vence))


@router.post("/consentimientos/{consentimiento}/revocar")
def consentimiento_revocar(request: Request, consentimiento: int,
                           csrf: str = Form("")):
    comprobar_csrf(request, csrf)
    try:
        pedir(request, "PATCH", "/consentimientos/%d" % consentimiento,
              json={"revocar": True}, volver_a="/consentimientos")
    except FalloDelBackend as error:
        return _volver(error)
    return _volver(ok="Autorización %d revocada. El tercero deja de ver esos "
                      "certificados en su siguiente clic." % consentimiento)
