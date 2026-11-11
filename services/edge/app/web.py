"""Lo que toda pagina del borde necesita: plantillas, sesion, CSRF y errores.

Para cualquier pagina nueva, de cualquier frente:

    from app.web import pagina, pedir, router_con_sesion

    @router.get("/fincas")
    def fincas(request: Request):
        datos = pedir(request, "GET", "/fincas").json()
        return pagina(request, "certificacion/fincas.html", fincas=datos["fincas"])

`pedir` ya traduce las respuestas del backend: 401 manda a entrar, al segundo
factor, a cambiar la clave o a reautenticarse, segun lo que falte; 403 dibuja
la pagina de acceso denegado con estado 403. Ninguna pagina tiene que
acordarse de eso.

La sesion vive en una cookie del borde:

    HttpOnly   el JavaScript de la pagina no la puede leer, asi que un XSS no
               se la roba
    Secure     solo viaja por HTTPS (en la nube; en local no hay TLS)
    SameSite   Strict: el navegador no la manda en peticiones que nacen en
               otro sitio, que es la primera defensa contra CSRF
    __Host-    el prefijo obliga a Secure, Path=/ y sin Domain: ningun
               subdominio la puede pisar

El valor es el token opaco del backend. El borde no lo interpreta.
"""

import hashlib
import hmac
import os
import urllib.parse
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import api

RAIZ = Path(__file__).resolve().parent.parent
plantillas = Jinja2Templates(directory=RAIZ / "templates")

VERSION = os.getenv("APP_VERSION", "dev")

COOKIE = "__Host-verdeazul" if api.EN_NUBE else "verdeazul"


# ---------------------------------------------------------------------------
# Excepciones que terminan en una respuesta
# ---------------------------------------------------------------------------

class Redirigir(Exception):
    def __init__(self, destino: str) -> None:
        super().__init__(destino)
        self.destino = destino


class Denegada(Exception):
    """El backend dijo 403. Se dibuja la pagina de acceso denegado."""


class FalloDelBackend(Exception):
    def __init__(self, estado: int, cuerpo: dict) -> None:
        super().__init__(estado)
        self.estado = estado
        self.cuerpo = cuerpo


# ---------------------------------------------------------------------------
# Sesion y CSRF
# ---------------------------------------------------------------------------

def token(request: Request) -> str | None:
    return request.cookies.get(COOKIE) or None


def csrf(token_sesion: str | None) -> str:
    """Token CSRF atado a la sesion: HMAC del token de sesion.

    Va en un campo oculto de cada formulario y se compara al recibirlo. Un
    sitio ajeno no lo puede calcular porque no conoce el token de sesion,
    que esta en una cookie HttpOnly. Es la segunda defensa despues de
    SameSite=Strict.
    """
    if not token_sesion:
        return ""
    return hmac.new(token_sesion.encode(), b"csrf-v1", hashlib.sha256).hexdigest()


def comprobar_csrf(request: Request, enviado: str | None) -> None:
    esperado = csrf(token(request))
    if not esperado or not hmac.compare_digest(esperado, enviado or ""):
        raise Denegada()


def poner_cookie(respuesta, valor: str) -> None:
    respuesta.set_cookie(COOKIE, valor, httponly=True, secure=api.EN_NUBE,
                         samesite="strict", path="/")


def quitar_cookie(respuesta) -> None:
    respuesta.delete_cookie(COOKIE, path="/", secure=api.EN_NUBE,
                            httponly=True, samesite="strict")


def destino_seguro(siguiente: str | None) -> str:
    """Evita la redireccion abierta: solo rutas de este mismo sitio."""
    if (not siguiente or not siguiente.startswith("/")
            or siguiente.startswith("//") or "\\" in siguiente):
        return "/panel"
    return siguiente


# ---------------------------------------------------------------------------
# Hablar con el backend
# ---------------------------------------------------------------------------

_PASOS = {
    "segundo_factor_pendiente": "/segundo-factor",
    "cambio_de_clave_pendiente": "/clave",
}


def pedir(request: Request, metodo: str, ruta: str, json: dict | None = None,
          params: dict | None = None, volver_a: str | None = None):
    """Llama al backend con la sesion de la persona y traduce los errores.

    Devuelve la respuesta si fue 2xx. Si no, lanza la excepcion que la
    convierte en la pagina que corresponde. `volver_a` es a donde regresar
    despues de reautenticarse; por omision, la pagina actual.
    """
    respuesta = api.llamar(metodo, ruta, sesion=token(request), json=json,
                           params=params)
    if respuesta.is_success:
        return respuesta

    try:
        cuerpo = respuesta.json()
    except ValueError:
        cuerpo = {}
    codigo = cuerpo.get("detail") if isinstance(cuerpo.get("detail"), str) else None

    if respuesta.status_code == 401:
        if codigo in _PASOS:
            raise Redirigir(_PASOS[codigo])
        if codigo == "reautenticacion_requerida":
            volver = volver_a or request.headers.get("referer") or str(request.url.path)
            volver = urllib.parse.urlsplit(volver).path or "/panel"
            raise Redirigir("/reautenticar?siguiente=" + urllib.parse.quote(volver))
        raise Redirigir("/entrar")
    if respuesta.status_code == 403:
        raise Denegada()
    raise FalloDelBackend(respuesta.status_code, cuerpo)


def sesion(request: Request) -> dict | None:
    """Quien es, segun el backend. None si no hay sesion."""
    if not token(request):
        return None
    respuesta = api.llamar("GET", "/auth/sesion", sesion=token(request))
    if respuesta.status_code != 200:
        return None
    return respuesta.json()


def mensaje_de(error: FalloDelBackend) -> str:
    """Un mensaje para la persona, sin detalles internos."""
    cuerpo = error.cuerpo
    if cuerpo.get("mensaje"):
        return cuerpo["mensaje"]
    if error.estado == 422:
        return "Revisá los datos del formulario."
    if error.estado == 404:
        return "No existe."
    if error.estado == 409:
        return "Eso ya existe o ya se hizo."
    return "No se pudo completar la operación."


# ---------------------------------------------------------------------------
# Dibujar
# ---------------------------------------------------------------------------

def pagina(request: Request, plantilla: str, estado: int = 200,
           datos_sesion: dict | None = None, **contexto) -> HTMLResponse:
    """Una pagina con lo comun: version, sesion y token CSRF."""
    if datos_sesion is None and token(request):
        datos_sesion = sesion(request)
    return plantillas.TemplateResponse(
        request=request,
        name=plantilla,
        status_code=estado,
        context={"version": VERSION, "sesion": datos_sesion,
                 "csrf": csrf(token(request)), **contexto},
    )


def ir(destino: str) -> RedirectResponse:
    """303: despues de un POST, el navegador pide la pagina con GET."""
    return RedirectResponse(destino, status_code=303)
