"""Pantalla de la bitacora de auditoria (O11).

No decide nada. El enlace de exportar se dibuja para quien la matriz se lo da
(DG, DC y el auditor), pero eso es comodidad: si el personal administrativo
escribe /bitacora/exportar a mano, el backend responde 403, se dibuja la
pagina de acceso denegado y el intento queda en la propia bitacora.

Los filtros se pasan tal cual al backend, que es quien los valida. Aqui solo
se quitan los campos vacios y se arman los enlaces: las paginas, y una
etiqueta por filtro activo con su enlace para quitarlo.
"""

import urllib.parse

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from app.web import FalloDelBackend, mensaje_de, pagina, pedir

router = APIRouter()

# Lo que se muestra en cada etiqueta de filtro activo.
_NOMBRES = {
    "desde": "Desde",
    "hasta": "Hasta",
    "accion": "Acción",
    "sujeto": "Sujeto",
    "tipo": "Objeto",
    "resultado": "Resultado",
}

POR_PAGINA = (10, 25, 50)


def _filtros(**valores) -> dict:
    return {k: v.strip() for k, v in valores.items() if v and v.strip()}


def _enlace(filtros: dict, **extra) -> str:
    """/bitacora con los filtros y lo que se agregue. Codificado, nunca
    concatenado: un valor con & o # no puede colar otro parametro."""
    datos = {**filtros, **{k: v for k, v in extra.items() if v is not None}}
    return "/bitacora" + ("?" + urllib.parse.urlencode(datos) if datos else "")


def _etiquetas(filtros: dict, por_pagina: int) -> list[dict]:
    """Una por filtro activo, con el enlace que lo quita y conserva el resto.
    Quitar un filtro vuelve a la pagina 1: la que se estaba viendo puede ya
    no existir con menos condiciones o con mas."""
    return [{"nombre": _NOMBRES[clave], "valor": valor,
             "quitar": _enlace({k: v for k, v in filtros.items() if k != clave},
                               por_pagina=por_pagina)}
            for clave, valor in filtros.items()]


def _paginas(actual: int, total: int) -> list[int | None]:
    """Los numeros a mostrar: la primera, la ultima y dos alrededor de la
    actual. None es un salto (...)."""
    visibles = sorted({1, total, *range(actual - 2, actual + 3)} & set(range(1, total + 1)))
    salida, previa = [], 0
    for n in visibles:
        if n - previa > 1:
            salida.append(None)
        salida.append(n)
        previa = n
    return salida


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
             pagina_actual: int = Query(1, alias="pagina", gt=0, le=100_000),
             por_pagina: int = Query(25)):
    if por_pagina not in POR_PAGINA:
        por_pagina = 25
    # La accion se escribe a mano: se pasa a mayusculas para que
    # "acceso_denegado" encuentre ACCESO_DENEGADO.
    filtros = _filtros(desde=desde, hasta=hasta, accion=accion.upper(),
                       sujeto=sujeto, tipo=tipo, resultado=resultado)
    error = None
    try:
        datos = pedir(request, "GET", "/bitacora",
                      params={**filtros, "pagina": pagina_actual,
                              "por_pagina": por_pagina}).json()
    except FalloDelBackend as fallo:
        # Un filtro mal escrito (422) se muestra en la misma pagina.
        if fallo.estado != 422:
            raise
        datos = {"eventos": [], "total": 0, "pagina": 1, "paginas": 1,
                 "primera_fila": 0, "pendientes_de_transmitir": None}
        error = mensaje_de(fallo)

    actual, paginas = datos["pagina"], datos["paginas"]
    return pagina(
        request, "bitacora/lista.html",
        eventos=datos["eventos"], total=datos["total"],
        primera_fila=datos["primera_fila"],
        pagina_actual=actual, paginas=paginas, por_pagina=por_pagina,
        numeros=[(n, _enlace(filtros, pagina=n, por_pagina=por_pagina))
                 if n else (None, None) for n in _paginas(actual, paginas)],
        anterior=(_enlace(filtros, pagina=actual - 1, por_pagina=por_pagina)
                  if actual > 1 else None),
        siguiente=(_enlace(filtros, pagina=actual + 1, por_pagina=por_pagina)
                   if actual < paginas else None),
        tamanos=[(n, _enlace(filtros, por_pagina=n)) for n in POR_PAGINA],
        pendientes=datos["pendientes_de_transmitir"],
        filtros=filtros, etiquetas=_etiquetas(filtros, por_pagina),
        exportar="/bitacora/exportar" + (
            "?" + urllib.parse.urlencode(filtros) if filtros else ""),
        error=error)
