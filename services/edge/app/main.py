"""Servicio de borde. Sirve la interfaz y es el unico expuesto a internet.

Implementa la frontera F1 del diseno. No habla con la base de datos: pide los
datos al backend por HTTP y con eso rellena las plantillas. El punto de
aplicacion de autorizacion (PEP) vive en el backend, no aqui.

Las cabeceras de seguridad y la politica CSP son responsabilidad de este
servicio: Cloud Run termina el TLS pero no pone cabeceras (D-04).
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(
    title="Verdeazul Carbono",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Rutas relativas a este archivo, no al directorio desde donde se arranca:
# asi el servicio levanta igual desde la raiz del repo y desde el contenedor.
RAIZ = Path(__file__).resolve().parent.parent

app.mount("/static", StaticFiles(directory=RAIZ / "static"), name="static")
plantillas = Jinja2Templates(directory=RAIZ / "templates")

VERSION = os.getenv("APP_VERSION", "dev")

# A donde se le piden los datos. En Cloud Run es la URL del backend, que no
# acepta invocaciones anonimas: solo la cuenta de servicio de este borde puede
# llamarlo. Asi se implementa la frontera F2.
API = os.getenv("API_URL", "http://localhost:8080")

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

    HSTS no se pone aqui: Cloud Run ya responde solo por HTTPS en *.run.app.
    Cuando haya dominio propio hay que agregarlo.
    """
    respuesta = await call_next(request)
    respuesta.headers["Content-Security-Policy"] = CSP
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["Referrer-Policy"] = "same-origin"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    return respuesta


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    return plantillas.TemplateResponse(
        request=request,
        name="inicio.html",
        context={"version": VERSION},
    )


@app.get("/entrar", response_class=HTMLResponse)
def entrar(request: Request):
    """Pantalla de inicio de sesion.

    PENDIENTE (F2): el POST tiene que llevar token CSRF y delegar la
    verificacion de la contrasena al backend. Esta pantalla solo dibuja.
    """
    return plantillas.TemplateResponse(
        request=request,
        name="auth/entrar.html",
        context={"version": VERSION},
    )
