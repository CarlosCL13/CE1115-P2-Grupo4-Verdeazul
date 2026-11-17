"""La verificacion publica de certificados (D-09).

Las pantallas de la lista, el detalle, emitir y anular llegan en la rama
feature/certificados-resto.

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

from fastapi import APIRouter, File, Request, UploadFile

from app import api
from app.web import pagina

router = APIRouter()

MAXIMO_BYTES = 64 * 1024
VERIFICACIONES_POR_MINUTO = 10

_candado = threading.Lock()
_intentos: dict[str, collections.deque] = {}


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
