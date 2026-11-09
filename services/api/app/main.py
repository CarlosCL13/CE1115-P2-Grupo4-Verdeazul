"""Backend de la plataforma Verdeazul. Punto de aplicacion (PEP).

Por ahora solo expone /salud, que sirve para comprobar de punta a punta que
Secret Manager entrega la cadena de conexion, que Cloud Run la recibe como
variable de entorno y que Neon responde por TLS.
"""

import os

import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.authz.Servicio_opa import motor_disponible

app = FastAPI(
    title="Verdeazul Carbono",
    description="Plataforma de certificacion de captura de carbono",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# La version de la imagen la inyecta Cloud Run al desplegar. Sirve para
# responder "que version esta corriendo" sin entrar a la consola.
VERSION = os.getenv("APP_VERSION", "dev")


def _estado_de_la_base() -> dict[str, object]:
    """Si Neon responde por TLS y con que version."""
    url = os.getenv("DATABASE_URL")
    if not url:
        return {"estado": "sin configurar"}

    try:
        with psycopg.connect(url, connect_timeout=10) as conexion:
            with conexion.cursor() as cursor:
                cursor.execute("SELECT version(), now()")
                version_bd, ahora = cursor.fetchone()
    except Exception:
        # Sin detalles al cliente: un mensaje de error de base de datos
        # revela estructura interna. El detalle va a la bitacora.
        return {"estado": "inaccesible"}

    return {
        "estado": "ok",
        "version": version_bd.split(" on ")[0],
        "hora_servidor": ahora.isoformat(),
    }


def _estado_del_motor() -> dict[str, object]:
    """Si el contenedor adjunto de politicas responde.

    Es la comprobacion que demuestra que los dos contenedores se estan
    hablando. Si dice "no responde", `puede(...)` esta denegando todo por la
    regla 2 del contrato 02, y conviene saberlo aqui antes de perder una hora
    pensando que la matriz esta mal transcrita.
    """
    return {"estado": "ok" if motor_disponible() else "no responde"}


@app.get("/salud")
def salud() -> JSONResponse:
    """Comprueba el servicio, el motor de politicas y la base de datos.

    Reporta los dos componentes por separado y siempre los dos, aunque uno
    falle. Antes, una base sin configurar cortaba la respuesta antes de llegar
    a mirar el motor, y en desarrollo local, que es justo donde no hay base de
    datos, eso dejaba ciego lo unico que se queria ver.
    """
    motor = _estado_del_motor()
    base = _estado_de_la_base()
    todo_bien = motor["estado"] == "ok" and base["estado"] == "ok"

    return JSONResponse(
        status_code=200 if todo_bien else 503,
        content={
            "estado": "ok" if todo_bien else "degradado",
            "version": VERSION,
            "motor_de_politicas": motor,
            "base_de_datos": base,
        },
    )
