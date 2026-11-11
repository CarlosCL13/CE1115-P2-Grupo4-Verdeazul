"""Pantallas de certificacion: fincas (O1), periodos (O2) y mediciones (O3).

Estas pantallas no deciden nada. Los botones de aprobar o cerrar se dibujan
segun el rol para no ofrecer lo que no sirve, pero eso es comodidad: quien
decide es el backend. Si alguien escribe la direccion a mano o manda el
formulario con otro rol, el servidor responde 403 y se dibuja la pagina de
acceso denegado, que es la evidencia del intento fallido (§5.1, punto 7).

Despues de un POST se vuelve a la lista con el mensaje del backend, igual que
en las solicitudes de cuentas. Aprobar, abrir y cerrar piden reautenticacion:
`pedir` manda a /reautenticar y la persona vuelve a la lista a repetir la
accion, porque un POST no se reenvia solo.
"""

import urllib.parse

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import Response

from app.web import (FalloDelBackend, comprobar_csrf, ir, mensaje_de, pagina,
                     pedir, sesion)

router = APIRouter()


def _con_error(destino: str, error: FalloDelBackend):
    return ir("%s?error=%s" % (
        destino, urllib.parse.quote(mensaje_de(error)[:200])))


# ---------------------------------------------------------------------------
# O1 Fincas
# ---------------------------------------------------------------------------

def _anillo(texto: str) -> list[list[float]]:
    """Una coordenada por linea, "longitud, latitud". Cierra el anillo solo.

    El backend valida la geometria de verdad (PostGIS). Aqui solo se convierte
    el texto de la persona en la forma que el backend espera.
    """
    puntos = []
    for linea in texto.replace(";", "\n").splitlines():
        partes = linea.replace(",", " ").split()
        if not partes:
            continue
        if len(partes) != 2:
            raise ValueError("Cada línea lleva dos números, longitud y latitud.")
        try:
            puntos.append([float(partes[0]), float(partes[1])])
        except ValueError:
            raise ValueError("Las coordenadas tienen que ser números.") from None
    if len(puntos) < 3:
        raise ValueError("El polígono necesita al menos tres puntos.")
    if puntos[0] != puntos[-1]:
        puntos.append(puntos[0])
    return puntos


def _texto_del_anillo(poligono: dict) -> str:
    anillo = poligono["coordinates"][0][:-1]
    return "\n".join("%s, %s" % (x, y) for x, y in anillo)


@router.get("/fincas")
def fincas(request: Request, error: str = Query("", max_length=200)):
    datos = pedir(request, "GET", "/fincas").json()
    return pagina(request, "certificacion/fincas.html",
                  fincas=datos["fincas"], error=error or None)


@router.post("/fincas")
def finca_nueva(request: Request, csrf: str = Form(""),
                nombre: str = Form(max_length=120),
                zona: str = Form(max_length=8),
                propietario: int = Form(),
                poligono: str = Form(max_length=20000)):
    comprobar_csrf(request, csrf)
    valores = {"nombre": nombre, "zona": zona, "propietario": propietario,
               "poligono": poligono}
    try:
        anillo = _anillo(poligono)
        creada = pedir(request, "POST", "/fincas", json={
            "nombre": nombre, "zona": zona.upper(), "propietario": propietario,
            "poligono": {"type": "Polygon", "coordinates": [anillo]}}).json()
    except ValueError as error:
        return _redibujar_fincas(request, 422, str(error), valores)
    except FalloDelBackend as error:
        return _redibujar_fincas(request, error.estado, mensaje_de(error),
                                 valores)
    return ir("/fincas/%d" % creada["id"])


def _redibujar_fincas(request, estado, error, valores):
    datos = pedir(request, "GET", "/fincas").json()
    return pagina(request, "certificacion/fincas.html", estado=estado,
                  fincas=datos["fincas"], error=error, valores=valores)


@router.get("/fincas/{finca}")
def finca(request: Request, finca: int, error: str = Query("", max_length=200),
          corregida: int = 0):
    datos = pedir(request, "GET", "/fincas/%d" % finca).json()
    return pagina(request, "certificacion/finca.html", finca=datos,
                  anillo=_texto_del_anillo(datos["poligono"]),
                  error=error or None, corregida=bool(corregida))


@router.post("/fincas/{finca}/editar")
def finca_editar(request: Request, finca: int, csrf: str = Form(""),
                 nombre: str = Form("", max_length=120),
                 zona: str = Form("", max_length=8),
                 poligono: str = Form("", max_length=20000)):
    comprobar_csrf(request, csrf)
    cuerpo: dict = {}
    if nombre.strip():
        cuerpo["nombre"] = nombre.strip()
    if zona.strip():
        cuerpo["zona"] = zona.strip().upper()
    try:
        if poligono.strip():
            cuerpo["poligono"] = {"type": "Polygon",
                                  "coordinates": [_anillo(poligono)]}
        pedir(request, "PATCH", "/fincas/%d" % finca, json=cuerpo)
    except ValueError as error:
        return ir("/fincas/%d?error=%s" % (
            finca, urllib.parse.quote(str(error))))
    except FalloDelBackend as error:
        return _con_error("/fincas/%d" % finca, error)
    return ir("/fincas/%d?corregida=1" % finca)


# ---------------------------------------------------------------------------
# O2 Periodos
# ---------------------------------------------------------------------------

@router.get("/periodos")
def periodos(request: Request, error: str = Query("", max_length=200)):
    datos = pedir(request, "GET", "/periodos").json()
    return pagina(request, "certificacion/periodos.html",
                  periodos=datos["periodos"], error=error or None)


@router.post("/periodos")
def periodo_nuevo(request: Request, csrf: str = Form(""),
                  etiqueta: str = Form(max_length=20)):
    comprobar_csrf(request, csrf)
    try:
        pedir(request, "POST", "/periodos", json={"etiqueta": etiqueta.strip()},
              volver_a="/periodos")
    except FalloDelBackend as error:
        return _con_error("/periodos", error)
    return ir("/periodos")


@router.post("/periodos/{periodo}/cerrar")
def periodo_cerrar(request: Request, periodo: int, csrf: str = Form("")):
    comprobar_csrf(request, csrf)
    try:
        pedir(request, "POST", "/periodos/%d/cerrar" % periodo,
              volver_a="/periodos")
    except FalloDelBackend as error:
        return _con_error("/periodos", error)
    return ir("/periodos")


@router.post("/periodos/{periodo}/abrir")
def periodo_abrir(request: Request, periodo: int, csrf: str = Form("")):
    comprobar_csrf(request, csrf)
    try:
        pedir(request, "POST", "/periodos/%d/abrir" % periodo,
              volver_a="/periodos")
    except FalloDelBackend as error:
        return _con_error("/periodos", error)
    return ir("/periodos")


# ---------------------------------------------------------------------------
# O3 Mediciones
# ---------------------------------------------------------------------------

# Antes de cualquier ruta con parametro, para que "exportar" no se tome por uno.
@router.get("/mediciones/exportar")
def mediciones_exportar(request: Request):
    """Pasa el CSV tal cual lo entrega el backend. Solo el auditor lo logra."""
    respuesta = pedir(request, "GET", "/mediciones/exportar")
    return Response(
        respuesta.content, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="mediciones.csv"'})


@router.get("/mediciones")
def mediciones(request: Request, error: str = Query("", max_length=200),
               periodo: int | None = Query(None, gt=0),
               finca: int | None = Query(None, gt=0)):
    filtros = {k: v for k, v in (("periodo", periodo), ("finca", finca)) if v}
    datos = pedir(request, "GET", "/mediciones", params=filtros).json()

    # Para el formulario de registrar. Solo los roles que registran pueden leer
    # ambas listas; el resto no las pide y no ve el formulario.
    fincas_lista, abiertos = [], []
    datos_sesion = sesion(request)
    rol = datos_sesion["rol"] if datos_sesion else None
    if rol in ("TECNICO_CAMPO", "VERIFICADOR"):
        fincas_lista = pedir(request, "GET", "/fincas").json()["fincas"]
        abiertos = [p for p in pedir(request, "GET", "/periodos"
                                     ).json()["periodos"]
                    if p["estado"] == "ABIERTO"]
    return pagina(request, "certificacion/mediciones.html",
                  mediciones=datos["mediciones"], fincas=fincas_lista,
                  abiertos=abiertos, error=error or None,
                  datos_sesion=datos_sesion)


@router.post("/mediciones")
def medicion_nueva(request: Request, csrf: str = Form(""),
                   finca: int = Form(), periodo: int = Form(),
                   biomasa: str = Form(max_length=20)):
    comprobar_csrf(request, csrf)
    try:
        pedir(request, "POST", "/mediciones", json={
            "finca": finca, "periodo": periodo,
            "biomasa_toneladas": biomasa.strip().replace(",", ".")},
            volver_a="/mediciones")
    except FalloDelBackend as error:
        return _con_error("/mediciones", error)
    return ir("/mediciones")


@router.post("/mediciones/{medicion}/aprobar")
def medicion_aprobar(request: Request, medicion: int, csrf: str = Form("")):
    comprobar_csrf(request, csrf)
    try:
        pedir(request, "POST", "/mediciones/%d/aprobar" % medicion,
              volver_a="/mediciones")
    except FalloDelBackend as error:
        return _con_error("/mediciones", error)
    return ir("/mediciones")


@router.post("/mediciones/{medicion}/devolver")
def medicion_devolver(request: Request, medicion: int, csrf: str = Form(""),
                      motivo: str = Form("", max_length=500)):
    comprobar_csrf(request, csrf)
    try:
        pedir(request, "POST", "/mediciones/%d/devolver" % medicion,
              json={"motivo": motivo.strip()}, volver_a="/mediciones")
    except FalloDelBackend as error:
        return _con_error("/mediciones", error)
    return ir("/mediciones")


__all__ = ["router"]
