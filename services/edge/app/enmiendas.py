"""Pantallas de enmiendas (O4).

Como las demas, no deciden nada. Los botones se dibujan segun el rol y el
estado para no ofrecer lo que no sirve, pero quien decide es el backend: si
el tecnico que pidio una enmienda intenta aprobarla escribiendo el
formulario a mano, el servidor responde 403 (C4) y el intento queda en la
bitacora.

Aprobar y cerrar piden reautenticacion: `pedir` manda a /reautenticar y la
persona vuelve a la lista a repetir la accion.
"""

import urllib.parse

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import Response

from app.web import (FalloDelBackend, comprobar_csrf, ir, mensaje_de, pagina,
                     pedir, sesion)

router = APIRouter()

ESTADOS = ("SOLICITADA", "REVISADA", "CERRADA", "DEVUELTA")


def _con_error(error: FalloDelBackend):
    return ir("/enmiendas?error=" + urllib.parse.quote(mensaje_de(error)[:200]))


def _candidatas(request: Request, cuenta: int) -> list[dict]:
    """Las mediciones propias en periodos cerrados: las unicas sobre las que
    el tecnico puede pedir una enmienda (C11). Es comodidad: el backend lo
    vuelve a decidir."""
    cerrados = {p["id"] for p in pedir(request, "GET", "/periodos"
                                       ).json()["periodos"]
                if p["estado"] == "CERRADO"}
    if not cerrados:
        return []
    return [m for m in pedir(request, "GET", "/mediciones").json()["mediciones"]
            if m["autor"] == cuenta and m["periodo"] in cerrados]


@router.get("/enmiendas/exportar")
def enmiendas_exportar(request: Request):
    """Pasa el CSV tal cual lo entrega el backend. Solo el auditor lo logra."""
    respuesta = pedir(request, "GET", "/enmiendas/exportar")
    return Response(
        respuesta.content, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="enmiendas.csv"'})


@router.get("/enmiendas")
def enmiendas(request: Request, error: str = Query("", max_length=200),
              estado: str = Query("", max_length=10),
              ok: str = Query("", max_length=200)):
    estado = estado if estado in ESTADOS else ""
    datos = pedir(request, "GET", "/enmiendas",
                  params={"estado": estado} if estado else None).json()

    datos_sesion = sesion(request)
    candidatas = []
    if datos_sesion and datos_sesion["rol"] == "TECNICO_CAMPO":
        candidatas = _candidatas(request, datos_sesion["cuenta"])
    # `filtro_estado` y no `estado`: pagina() ya usa `estado` para el codigo
    # HTTP de la respuesta.
    return pagina(request, "enmiendas/lista.html",
                  enmiendas=datos["enmiendas"], filtro_estado=estado,
                  estados=ESTADOS, candidatas=candidatas,
                  error=error or None, ok=ok or None,
                  datos_sesion=datos_sesion)


@router.post("/enmiendas")
def enmienda_nueva(request: Request, csrf: str = Form(""),
                   medicion: int = Form(gt=0),
                   justificacion: str = Form(max_length=1000)):
    comprobar_csrf(request, csrf)
    try:
        r = pedir(request, "POST", "/enmiendas", json={
            "medicion": medicion, "justificacion": justificacion.strip()},
            volver_a="/enmiendas")
    except FalloDelBackend as error:
        return _con_error(error)
    return ir("/enmiendas?ok=" + urllib.parse.quote(
        "Enmienda %d solicitada. Ahora la revisa un verificador." % r.json()["id"]))


def _accion(request: Request, enmienda: int, accion: str, mensaje: str,
            json: dict | None = None):
    try:
        pedir(request, "POST", "/enmiendas/%d/%s" % (enmienda, accion),
              json=json, volver_a="/enmiendas")
    except FalloDelBackend as error:
        return _con_error(error)
    return ir("/enmiendas?ok=" + urllib.parse.quote(mensaje % enmienda))


@router.post("/enmiendas/{enmienda}/aprobar")
def enmienda_aprobar(request: Request, enmienda: int, csrf: str = Form("")):
    comprobar_csrf(request, csrf)
    return _accion(request, enmienda, "aprobar",
                   "Enmienda %d revisada. Falta que Dirección de "
                   "Certificación la cierre.")


@router.post("/enmiendas/{enmienda}/devolver")
def enmienda_devolver(request: Request, enmienda: int, csrf: str = Form(""),
                      motivo: str = Form("", max_length=500)):
    comprobar_csrf(request, csrf)
    return _accion(request, enmienda, "devolver", "Enmienda %d devuelta.",
                   json={"motivo": motivo.strip()})


@router.post("/enmiendas/{enmienda}/cerrar")
def enmienda_cerrar(request: Request, enmienda: int, csrf: str = Form("")):
    comprobar_csrf(request, csrf)
    return _accion(request, enmienda, "cerrar", "Enmienda %d cerrada.")
