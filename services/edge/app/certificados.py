"""Pantallas de certificados (O5) y la verificacion publica (D-09).

Como las demas, no deciden nada. Los botones de emitir y anular se dibujan
solo para el rol que los tiene, pero si otro rol manda el formulario a mano
el backend responde 403 y el intento queda en la bitacora. Emitir y anular
piden reautenticacion: `pedir` manda a /reautenticar y la persona vuelve a
la lista a repetir la accion.

La verificacion publica es la unica pagina de este borde que llama al
backend sin sesion. Tiene dos protecciones que viven aqui porque este es el
servicio expuesto a internet:

    tamano   se leen como maximo 64 KB del archivo; uno mas grande no llega
             al backend
    tasa     cada direccion de origen puede verificar 10 veces por minuto

El limite de tasa vive en la memoria de cada instancia. Si Cloud Run levanta
dos, el limite efectivo es el doble. Para una demostracion y para el volumen
de Verdeazul alcanza; en una operacion real iria en un servicio compartido.
Esta declarado en D-09.
"""

import collections
import threading
import time
import urllib.parse

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import Response

from app import api
from app.web import (FalloDelBackend, comprobar_csrf, ir, mensaje_de, pagina,
                     pedir, sesion)

router = APIRouter()

MAXIMO_BYTES = 64 * 1024
VERIFICACIONES_POR_MINUTO = 10

_candado = threading.Lock()
_intentos: dict[str, collections.deque] = {}


def _volver(destino: str = "/certificados",
            error: FalloDelBackend | None = None, ok: str | None = None):
    if error is not None:
        return ir(destino + "?error=" +
                  urllib.parse.quote(mensaje_de(error)[:200]))
    return ir(destino + "?ok=" + urllib.parse.quote(ok or ""))


# ---------------------------------------------------------------------------
# Con sesion: listar, ver, descargar, emitir, anular, exportar
# ---------------------------------------------------------------------------

@router.get("/certificados/exportar")
def certificados_exportar(request: Request):
    """Pasa el CSV tal cual lo entrega el backend. Solo el auditor lo logra."""
    respuesta = pedir(request, "GET", "/certificados/exportar")
    return Response(
        respuesta.content, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 'attachment; filename="certificados.csv"'})


@router.get("/certificados")
def certificados(request: Request, error: str = Query("", max_length=200),
                 ok: str = Query("", max_length=200),
                 estado: str = Query("", max_length=8)):
    estado = estado if estado in ("VIGENTE", "ANULADO") else ""
    datos = pedir(request, "GET", "/certificados",
                  params={"estado": estado} if estado else None).json()
    datos_sesion = sesion(request)

    # Para el verificador: las mediciones aprobadas que todavia no tienen un
    # certificado vigente. Es comodidad: si alguien emite sobre otra, el
    # servidor vuelve a decidir con C6.
    por_emitir = []
    if datos_sesion and datos_sesion["rol"] == "VERIFICADOR":
        vigentes = {c["medicion"] for c in pedir(
            request, "GET", "/certificados",
            params={"estado": "VIGENTE"}).json()["certificados"]}
        por_emitir = [m for m in pedir(
            request, "GET", "/mediciones",
            params={"estado": "APROBADA"}).json()["mediciones"]
            if m["id"] not in vigentes]

    return pagina(request, "certificados/lista.html",
                  certificados=datos["certificados"], por_emitir=por_emitir,
                  filtro_estado=estado, error=error or None, ok=ok or None,
                  datos_sesion=datos_sesion)


@router.get("/certificados/{certificado}")
def certificado(request: Request, certificado: int,
                error: str = Query("", max_length=200),
                ok: str = Query("", max_length=200)):
    datos = pedir(request, "GET", "/certificados/%d" % certificado).json()
    return pagina(request, "certificados/detalle.html", c=datos,
                  error=error or None, ok=ok or None)


@router.get("/certificados/{certificado}/descargar")
def certificado_descargar(request: Request, certificado: int):
    """El archivo firmado, tal como se emitio. Es el que se sube a /verificar."""
    datos = pedir(request, "GET", "/certificados/%d" % certificado).json()
    return Response(
        datos["documento"], media_type="application/json; charset=utf-8",
        headers={"Content-Disposition":
                 'attachment; filename="certificado-%d.json"' % certificado})


@router.post("/certificados/emitir")
def certificado_emitir(request: Request, csrf: str = Form(""),
                       medicion: int = Form(gt=0)):
    comprobar_csrf(request, csrf)
    try:
        r = pedir(request, "POST", "/certificados/%d/emitir" % medicion,
                  volver_a="/certificados")
    except FalloDelBackend as error:
        return _volver(error=error)
    c = r.json()
    return _volver("/certificados/%d" % c["id"],
                   ok="Certificado %d emitido y firmado." % c["id"])


@router.post("/certificados/{certificado}/anular")
def certificado_anular(request: Request, certificado: int,
                       csrf: str = Form(""),
                       motivo: str = Form(max_length=500)):
    comprobar_csrf(request, csrf)
    destino = "/certificados/%d" % certificado
    try:
        pedir(request, "POST", destino + "/anular",
              json={"motivo": motivo.strip()}, volver_a=destino)
    except FalloDelBackend as error:
        return _volver(destino, error=error)
    return _volver(destino, ok="Certificado %d anulado." % certificado)


# ---------------------------------------------------------------------------
# Sin sesion: verificar un archivo (D-09)
# ---------------------------------------------------------------------------

def _origen(request: Request) -> str:
    """La direccion de quien pide.

    Detras de Cloud Run, la del cliente llega en X-Forwarded-For. El cliente
    puede escribir ahi lo que quiera, pero Google agrega la direccion real al
    final, asi que se toma la ultima: esa no la controla el cliente.
    """
    reenviada = request.headers.get("x-forwarded-for", "")
    if reenviada:
        return reenviada.split(",")[-1].strip()
    return request.client.host if request.client else "desconocido"


def _dentro_del_limite(origen: str) -> bool:
    ahora = time.monotonic()
    with _candado:
        # Que la tabla no crezca sin fin con direcciones que ya no vuelven.
        if len(_intentos) > 10_000:
            _intentos.clear()
        cola = _intentos.setdefault(origen, collections.deque())
        while cola and ahora - cola[0] > 60:
            cola.popleft()
        if len(cola) >= VERIFICACIONES_POR_MINUTO:
            return False
        cola.append(ahora)
        return True


# Sin async a proposito: api.llamar es bloqueante, y en una funcion sync
# FastAPI la corre en un hilo aparte sin detener a las demas peticiones.
@router.post("/verificar")
def verificar_archivo(request: Request, archivo: UploadFile = File(...)):
    """Recibe el archivo, lo manda al backend y muestra el resultado.

    Sin CSRF a proposito: no hay sesion que proteger y no cambia nada. Lo
    que si aplica es la revision de origen del middleware de main.py, que
    rechaza un POST que nace en otro sitio.
    """
    if not _dentro_del_limite(_origen(request)):
        return pagina(request, "certificados/verificacion.html", estado=429,
                      error="Demasiadas verificaciones seguidas desde su "
                            "conexión. Espere un minuto e intente de nuevo.")

    crudo = archivo.file.read(MAXIMO_BYTES + 1)
    if len(crudo) > MAXIMO_BYTES:
        return pagina(request, "certificados/verificacion.html", estado=413,
                      error="El archivo es demasiado grande para ser un "
                            "certificado (máximo 64 KB).")
    try:
        texto = crudo.decode("utf-8")
    except UnicodeDecodeError:
        texto = ""

    # Directo con api.llamar y sin sesion: es la unica ruta del backend que
    # no la pide. El backend igual exige el token de Google de este borde
    # (F2), asi que desde internet nadie llega a el sin pasar por aqui.
    respuesta = api.llamar("POST", "/publico/verificar",
                           json={"archivo": texto})
    if not respuesta.is_success:
        return pagina(request, "certificados/verificacion.html", estado=503,
                      error="No se pudo verificar en este momento.")
    return pagina(request, "certificados/verificacion.html",
                  resultado=respuesta.json(), nombre=archivo.filename)
