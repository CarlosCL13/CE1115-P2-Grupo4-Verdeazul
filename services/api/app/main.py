"""Backend de la plataforma Verdeazul. Punto de aplicacion (PEP).

Aqui se registran los modulos de cada frente. Cada uno expone un router y se
agrega con una sola linea, para que un conflicto de git sea de una linea.

Por ahora solo esta /salud, que comprueba de punta a punta que la
configuracion llego y que Neon responde por TLS.
"""

import contextlib

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import bd, config


@contextlib.asynccontextmanager
async def ciclo(app: FastAPI):
    """Abre las conexiones al levantar y las cierra al apagar.

    Abrirlas aqui y no en la primera peticion hace que un problema de
    credenciales se vea cuando el servicio arranca, no cuando entra el primer
    usuario.
    """
    bd.arrancar()
    try:
        yield
    finally:
        bd.cerrar()


app = FastAPI(
    title="Verdeazul Carbono",
    description="Plataforma de certificacion de captura de carbono",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=ciclo,
)

# Aqui va una linea por modulo, a medida que existan:
#
# from app.cuentas import router as router_cuentas
# app.include_router(router_cuentas)


@app.get("/salud")
def salud() -> JSONResponse:
    """Dice si el servicio responde y si la base contesta.

    Sin detalles del error al cliente: un mensaje de base de datos revela
    estructura interna. El detalle va a los registros.
    """
    viva = bd.esta_viva()
    return JSONResponse(
        status_code=200 if viva else 503,
        content={"estado": "ok" if viva else "base de datos inaccesible",
                 **config.resumen()},
    )
