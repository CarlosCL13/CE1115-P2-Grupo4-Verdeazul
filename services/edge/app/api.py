"""El unico camino del borde al backend.

El borde no habla con la base de datos ni decide permisos: le pregunta al
backend y dibuja lo que este responde. Cada llamada lleva dos cosas:

  Authorization        el token de identidad de Google de la cuenta de
                       servicio de este borde. El backend esta en Cloud Run
                       con --no-allow-unauthenticated: sin este token, Google
                       rechaza la peticion antes de que llegue a nuestro
                       codigo. Esa es la frontera F2.
  X-Verdeazul-Sesion   el token de sesion de la persona, que el navegador
                       guarda en una cookie HttpOnly de este borde. Con eso el
                       backend sabe quien pregunta.

En local no hay token de Google: el backend corre en localhost sin IAM.
"""

import os
import threading
import time

import httpx

API = os.getenv("API_URL", "http://localhost:8080")

# K_SERVICE la pone Cloud Run y nadie mas.
EN_NUBE = bool(os.getenv("K_SERVICE"))

CABECERA_SESION = "X-Verdeazul-Sesion"

_METADATOS = ("http://metadata.google.internal/computeMetadata/v1/instance/"
              "service-accounts/default/identity")

_cliente = httpx.Client(
    base_url=API,
    timeout=httpx.Timeout(15.0, connect=5.0),
    # Sin proxies del entorno: el backend se alcanza directo.
    trust_env=False,
)

_candado = threading.Lock()
_token_google: tuple[str | None, float] = (None, 0.0)


class BackendCaido(RuntimeError):
    """El backend no contesto. La pagina dice que se intente de nuevo."""


def _identidad_google() -> str | None:
    """Token de identidad para invocar al backend, con cache de 50 minutos.

    Lo entrega el servidor de metadatos de Cloud Run, sin ninguna llave en el
    codigo ni en el contenedor: es la identidad de la cuenta de servicio con
    la que corre este borde. Dura una hora; se renueva antes.
    """
    global _token_google
    if not EN_NUBE:
        return None
    with _candado:
        token, vence = _token_google
        if token and time.time() < vence:
            return token
        respuesta = httpx.get(_METADATOS, params={"audience": API},
                              headers={"Metadata-Flavor": "Google"},
                              timeout=5.0, trust_env=False)
        respuesta.raise_for_status()
        _token_google = (respuesta.text, time.time() + 50 * 60)
        return respuesta.text


def llamar(metodo: str, ruta: str, sesion: str | None = None,
           json: dict | None = None, params: dict | None = None
           ) -> httpx.Response:
    cabeceras = {}
    try:
        google = _identidad_google()
    except httpx.HTTPError as error:
        raise BackendCaido("sin token de identidad: %r" % error) from error
    if google:
        cabeceras["Authorization"] = "Bearer " + google
    if sesion:
        cabeceras[CABECERA_SESION] = sesion
    try:
        return _cliente.request(metodo, ruta, headers=cabeceras, json=json,
                                params=params)
    except httpx.HTTPError as error:
        raise BackendCaido(repr(error)) from error
