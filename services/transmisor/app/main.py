"""Transmisor y trabajos programados. Un solo punto de entrada (D-11).

Cloud Scheduler lo invoca y cada tarea se ejecuta segun le toque. El servicio
esta cerrado a internet: solo lo puede invocar la cuenta del planificador.

Las cuatro tareas que P1 preveia como procesos independientes:

  - transmitir: copia los eventos de la bandeja de salida a la bitacora
  - vencer:     desactiva asignaciones y autorizaciones vencidas (HBAC-03)
  - cadena:     recomputa la cadena HMAC y reporta si se rompio
  - volcado:    pg_dump de ambas bases a Cloud Storage (D-07, retencion de BI-04)

Cuidado con el consumo: §3.1 del enunciado advierte que procesos en bucle
pueden generar un cobro. Ninguna tarea debe reintentar sin limite.

Lo que ya esta listo para escribirlas (config, conexiones, permisos y como
deberia funcionar cada una) esta en el README de esta carpeta.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

# Se importa al arrancar: si falta un secreto en la nube, el contenedor no
# llega a estar sano y Cloud Run sigue sirviendo la revision anterior.
from app import bd, config

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

TAREAS = ("transmitir", "vencer", "cadena", "volcado")


@app.post("/tareas/{nombre}")
def ejecutar(nombre: str) -> dict:
    """Ejecuta una tarea programada.

    PENDIENTE: implementar cada tarea. El relleno responde 501 para que se
    note en los registros que la tarea existe pero no hace nada.
    """
    if nombre not in TAREAS:
        raise HTTPException(status_code=404, detail="tarea desconocida")
    raise HTTPException(status_code=501, detail=f"{nombre}: sin implementar")


@app.get("/salud")
def salud() -> JSONResponse:
    """Si las dos bases responden con los roles del transmisor.

    No la llama el planificador, solo una persona: despierta las dos bases de
    Neon. Sin detalles del error al cliente; el detalle va a los registros.
    """
    estado = {}
    for nombre, abrir in (("bandeja", bd.bandeja), ("bitacora", bd.bitacora)):
        try:
            with abrir() as cur:
                cur.execute("SELECT 1")
            estado[nombre] = "ok"
        except bd.SinConexion:
            estado[nombre] = "sin configurar"
        except Exception:
            estado[nombre] = "inaccesible"
    todo_bien = all(v == "ok" for v in estado.values())
    return JSONResponse(
        status_code=200 if todo_bien else 503,
        content={"estado": "ok" if todo_bien else "degradado",
                 **estado, **config.resumen()})
