"""Backend de la plataforma Verdeazul. Punto de aplicacion (PEP).

Aqui se registran los modulos de cada frente. Cada uno expone un router y se
agrega con una sola linea, para que un conflicto de git sea de una linea.

Por ahora solo esta /salud, que reporta por separado el motor de politicas y
la base de datos.
"""

import contextlib

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import bd, config
from app.authz.Servicio_opa import motor_disponible
from app.auth import cifrado
from app.errores import ErrorAPI, manejar_denegado, manejar_error_api


@contextlib.asynccontextmanager
async def ciclo(app: FastAPI):
    """Abre las conexiones al levantar y las cierra al apagar.

    Abrirlas aqui y no en la primera peticion hace que un problema de
    credenciales se vea cuando el servicio arranca.

    En local no corta el arranque si no hay base: el ciclo de trabajo sobre
    las politicas levanta api y policies sin base de datos, y /salud lo
    reporta como sin configurar.
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

# Errores con forma unica, {"detail": "codigo"}. Denegado es el 403 del
# contrato 02: el motivo ya quedo en la bitacora y al cliente no se le dice.
app.add_exception_handler(ErrorAPI, manejar_error_api)
app.add_exception_handler(bd.Denegado, manejar_denegado)


@app.exception_handler(bd.SinTransaccion)
async def _sin_base(_request, _error) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "sin_base_de_datos"})


@app.exception_handler(cifrado.DatoAlterado)
async def _dato_alterado(_request, _error) -> JSONResponse:
    # GCM detecto un dato cifrado que no cuadra con su fila. No se dice mas.
    return JSONResponse(status_code=409, content={"detail": "dato_ilegible"})


@app.exception_handler(cifrado.SinLlave)
async def _sin_llave(_request, _error) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "sin_llave_de_cifrado"})


# Aqui va una linea por modulo, a medida que existan:
from app.auth import router as router_auth  # noqa: E402
from app.personas import router as router_personas  # noqa: E402
from app.cuentas import router as router_cuentas  # noqa: E402
from app.certificacion import router as router_certificacion  # noqa: E402

app.include_router(router_auth)
app.include_router(router_personas)
app.include_router(router_cuentas)
app.include_router(router_certificacion)


def _estado_del_motor() -> dict[str, object]:
    """Si el contenedor adjunto de politicas responde.

    Es la comprobacion que demuestra que los dos contenedores se estan
    hablando. Si dice "no responde", `puede(...)` esta denegando todo por la
    regla 2 del contrato 02, y conviene saberlo aqui antes de perder una hora
    pensando que la matriz esta mal transcrita.
    """
    return {"estado": "ok" if motor_disponible() else "no responde"}


def _estado_de_la_base() -> dict[str, object]:
    """Si Neon responde.

    Sin detalles del error al cliente: un mensaje de base de datos revela
    estructura interna. El detalle va a los registros.
    """
    if config.BD_URL is None:
        return {"estado": "sin configurar"}
    return {"estado": "ok" if bd.esta_viva() else "inaccesible"}


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
            "motor_de_politicas": motor,
            "base_de_datos": base,
            **config.resumen(),
        },
    )
