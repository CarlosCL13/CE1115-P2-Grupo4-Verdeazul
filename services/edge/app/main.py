"""Servicio de borde. Sirve la interfaz y es el unico expuesto a internet.

Implementa la frontera F1 del diseno. No habla con la base de datos: pide los
datos al backend por HTTP y con eso rellena las plantillas. El punto de
aplicacion de autorizacion (PEP) vive en el backend, no aqui.

Las cabeceras de seguridad y la politica CSP son responsabilidad de este
servicio: Cloud Run termina el TLS pero no pone cabeceras (D-04).

Lo comun a todas las paginas (sesion, CSRF, errores del backend) esta en
app/web.py. Cada frente agrega su router con una linea, igual que en el
backend.
"""

import urllib.parse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app import api
from app.web import (RAIZ, VERSION, Denegada, FalloDelBackend, Redirigir,
                     ir, mensaje_de, pagina)

app = FastAPI(
    title="Verdeazul Carbono",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.mount("/static", StaticFiles(directory=RAIZ / "static"), name="static")

# A donde se le piden los datos. En Cloud Run es la URL del backend, que no
# acepta invocaciones anonimas: solo la cuenta de servicio de este borde puede
# llamarlo. Asi se implementa la frontera F2. Ver app/api.py.
API = api.API

# Sin unsafe-inline ni unsafe-eval. Con plantillas servidas no hace falta
# JavaScript en linea, asi que la politica puede ser estricta de verdad.
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'"
)


@app.middleware("http")
async def cabeceras_de_seguridad(request: Request, call_next):
    """Agrega las cabeceras que P1 asignaba a nginx.

    Ademas, ningun formulario se acepta si viene de otro sitio: si el
    navegador dice que el POST nacio en otro origen, se rechaza antes de
    tocar nada. Es la defensa contra CSRF para el formulario de entrar, que
    todavia no tiene sesion ni token; los demas llevan ademas el token CSRF.
    """
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origen = request.headers.get("origin")
        if origen and origen != "null":
            esperado = request.headers.get("host", "")
            if urllib.parse.urlsplit(origen).netloc != esperado:
                return PlainTextResponse("Origen no permitido", status_code=403)

    respuesta = await call_next(request)
    respuesta.headers["Content-Security-Policy"] = CSP
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["Referrer-Policy"] = "same-origin"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    # Las paginas con datos de una sesion no se guardan en caches compartidas
    # ni en el historial del navegador.
    respuesta.headers.setdefault("Cache-Control", "no-store")
    return respuesta


# ---------------------------------------------------------------------------
# Lo que el backend responde se traduce aqui, una sola vez
# ---------------------------------------------------------------------------

@app.exception_handler(Redirigir)
async def _redirigir(_request: Request, error: Redirigir):
    return ir(error.destino)


@app.exception_handler(Denegada)
async def _denegada(request: Request, _error: Denegada):
    # El servidor rechazo la operacion. Esta es la pantalla de la evidencia
    # "el intento fallido de un rol" (§5.1, punto 7).
    return pagina(request, "denegado.html", estado=403)


@app.exception_handler(FalloDelBackend)
async def _fallo(request: Request, error: FalloDelBackend):
    return pagina(request, "error.html", estado=error.estado,
                  mensaje=mensaje_de(error))


@app.exception_handler(api.BackendCaido)
async def _caido(request: Request, _error: Exception):
    return pagina(request, "error.html", estado=503, datos_sesion={},
                  mensaje="El sistema no responde en este momento. Intentá "
                          "de nuevo en unos segundos.")


# ---------------------------------------------------------------------------
# Paginas
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    return pagina(request, "inicio.html")


# Aqui va una linea por modulo, a medida que existan:
from app.identidad import router as router_identidad  # noqa: E402
from app.certificacion import router as router_certificacion  # noqa: E402
from app.bitacora import router as router_bitacora  # noqa: E402

app.include_router(router_identidad)
app.include_router(router_certificacion)
app.include_router(router_bitacora)


__all__ = ["app", "VERSION"]
