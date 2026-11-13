"""Pantalla de asignaciones tecnico-zona (O8).

No decide nada. El formulario de asignar y los botones de extender y revocar
se dibujan solo para Direccion de Certificacion, pero si otro rol manda el
formulario a mano el backend responde 403 y el intento queda en la
bitacora. Crear y modificar piden reautenticacion.

Un formulario HTML solo sabe GET y POST, asi que el PATCH del backend se
alcanza desde dos POST del borde: /modificar y /revocar.
"""

import urllib.parse

from fastapi import APIRouter, Form, Query, Request

from app.web import (FalloDelBackend, comprobar_csrf, ir, mensaje_de, pagina,
                     pedir, sesion)

router = APIRouter()


def _volver(error: FalloDelBackend | None = None, ok: str | None = None):
    if error is not None:
        return ir("/asignaciones?error=" +
                  urllib.parse.quote(mensaje_de(error)[:200]))
    return ir("/asignaciones?ok=" + urllib.parse.quote(ok or ""))


@router.get("/asignaciones")
def asignaciones(request: Request, error: str = Query("", max_length=200),
                 ok: str = Query("", max_length=200),
                 vigentes: str = Query("", max_length=2)):
    datos = pedir(request, "GET", "/asignaciones",
                  params={"solo_vigentes": "true"} if vigentes else None).json()
    datos_sesion = sesion(request)
    opciones = None
    if datos_sesion and datos_sesion["rol"] == "DIRECCION_CERTIFICACION":
        opciones = pedir(request, "GET", "/asignaciones/opciones").json()
    return pagina(request, "asignaciones/lista.html",
                  asignaciones=datos["asignaciones"], opciones=opciones,
                  solo_vigentes=bool(vigentes), error=error or None,
                  ok=ok or None, datos_sesion=datos_sesion)


@router.post("/asignaciones")
def asignacion_nueva(request: Request, csrf: str = Form(""),
                     sujeto: int = Form(gt=0),
                     zona: str = Form(max_length=8),
                     vence: str = Form(max_length=10)):
    comprobar_csrf(request, csrf)
    try:
        r = pedir(request, "POST", "/asignaciones", json={
            "sujeto": sujeto, "zona": zona, "vence": vence},
            volver_a="/asignaciones")
    except FalloDelBackend as error:
        return _volver(error)
    a = r.json()
    return _volver(ok="Asignación %d creada: %s en %s hasta %s."
                   % (a["id"], a["usuario"], a["zona"], a["vence"]))


@router.post("/asignaciones/{asignacion}/modificar")
def asignacion_modificar(request: Request, asignacion: int,
                         csrf: str = Form(""),
                         vence: str = Form("", max_length=10),
                         zona: str = Form("", max_length=8)):
    comprobar_csrf(request, csrf)
    cambios = {k: v for k, v in (("vence", vence), ("zona", zona)) if v}
    try:
        pedir(request, "PATCH", "/asignaciones/%d" % asignacion, json=cambios,
              volver_a="/asignaciones")
    except FalloDelBackend as error:
        return _volver(error)
    return _volver(ok="Asignación %d actualizada." % asignacion)


@router.post("/asignaciones/{asignacion}/revocar")
def asignacion_revocar(request: Request, asignacion: int,
                       csrf: str = Form("")):
    comprobar_csrf(request, csrf)
    try:
        pedir(request, "PATCH", "/asignaciones/%d" % asignacion,
              json={"revocar": True}, volver_a="/asignaciones")
    except FalloDelBackend as error:
        return _volver(error)
    return _volver(ok="Asignación %d revocada. La persona pierde esa zona "
                      "en su siguiente clic." % asignacion)
