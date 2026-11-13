"""Pantalla de la bitacora de auditoria (O11).

No decide nada. El enlace de exportar se dibuja para quien la matriz se lo da
(DG, DC y el auditor), pero eso es comodidad: si el personal administrativo
escribe /bitacora/exportar a mano, el backend responde 403, se dibuja la
pagina de acceso denegado y el intento queda en la propia bitacora.

Los filtros se pasan tal cual al backend, que es quien los valida. Aqui solo
se quitan los campos vacios del formulario.
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from app.web import FalloDelBackend, mensaje_de, pagina, pedir

router = APIRouter()

_FILTROS = ("desde", "hasta", "accion", "sujeto", "tipo", "resultado")


def _filtros(**valores) -> dict:
    return {k: v.strip() for k, v in valores.items() if v and v.strip()}


# Antes de /bitacora, por orden de lectura; no hay ruta con parametro.
@router.get("/bitacora/exportar")
def bitacora_exportar(request: Request,
                      desde: str = Query("", max_length=10),
                      hasta: str = Query("", max_length=10),
                      accion: str = Query("", max_length=60),
                      sujeto: str = Query("", max_length=40),
                      tipo: str = Query("", max_length=3),
                      resultado: str = Query("", max_length=9)):
    """Pasa el CSV tal cual lo entrega el backend."""
    filtros = _filtros(desde=desde, hasta=hasta, accion=accion, sujeto=sujeto,
                       tipo=tipo, resultado=resultado)
    respuesta = pedir(request, "GET", "/bitacora/exportar", params=filtros)
    return Response(
        respuesta.content, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="bitacora.csv"'})


@router.get("/bitacora")
def bitacora(request: Request,
             desde: str = Query("", max_length=10),
             hasta: str = Query("", max_length=10),
             accion: str = Query("", max_length=60),
             sujeto: str = Query("", max_length=40),
             tipo: str = Query("", max_length=3),
             resultado: str = Query("", max_length=9),
             antes: str = Query("", max_length=20)):
    filtros = _filtros(desde=desde, hasta=hasta, accion=accion, sujeto=sujeto,
                       tipo=tipo, resultado=resultado)
    error = None
    try:
        datos = pedir(request, "GET", "/bitacora",
                      params={**filtros, **_filtros(antes=antes)}).json()
    except FalloDelBackend as fallo:
        # Un filtro mal escrito (422) se muestra en la misma pagina.
        if fallo.estado == 422:
            datos = {"eventos": [], "siguiente": None,
                     "pendientes_de_transmitir": None}
            error = mensaje_de(fallo)
        else:
            raise
    return pagina(request, "bitacora/lista.html",
                  eventos=datos["eventos"], siguiente=datos["siguiente"],
                  pendientes=datos["pendientes_de_transmitir"],
                  filtros=filtros, error=error)
