"""Backend de la plataforma Verdeazul. Punto de aplicacion (PEP).

Por ahora solo expone /salud, que sirve para comprobar de punta a punta que
Secret Manager entrega la cadena de conexion, que Cloud Run la recibe como
variable de entorno y que Neon responde por TLS.
"""

import os

import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse

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


@app.get("/salud")
def salud() -> JSONResponse:
    """Comprueba que el servicio responde y que la base de datos contesta."""
    url = os.getenv("DATABASE_URL")
    if not url:
        return JSONResponse(
            status_code=503,
            content={"estado": "sin configurar", "version": VERSION},
        )

    try:
        with psycopg.connect(url, connect_timeout=10) as conexion:
            with conexion.cursor() as cursor:
                cursor.execute("SELECT version(), now()")
                version_bd, ahora = cursor.fetchone()
    except Exception:
        # Sin detalles al cliente: un mensaje de error de base de datos
        # revela estructura interna. El detalle va a la bitacora.
        return JSONResponse(
            status_code=503,
            content={"estado": "base de datos inaccesible", "version": VERSION},
        )

    return JSONResponse(
        content={
            "estado": "ok",
            "version": VERSION,
            "base_de_datos": version_bd.split(" on ")[0],
            "hora_servidor": ahora.isoformat(),
        }
    )
