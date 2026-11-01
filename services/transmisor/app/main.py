"""Transmisor y trabajos programados. Un solo punto de entrada (D-11).

Cloud Scheduler lo invoca y cada tarea se ejecuta segun le toque. El punto
exige autenticacion de la cuenta de servicio del planificador y no es
accesible desde internet.

Las cuatro tareas que P1 preveia como procesos independientes:

  - transmitir: copia los eventos de la bandeja de salida a la bitacora
  - vencer:     desactiva asignaciones y autorizaciones vencidas (HBAC-03)
  - cadena:     recomputa la cadena HMAC y reporta si se rompio
  - volcado:    pg_dump de ambas bases a Cloud Storage (D-07, retencion de BI-04)

Cuidado con el consumo: §3.1 del enunciado advierte que procesos en bucle
pueden generar un cobro. Ninguna tarea debe reintentar sin limite.
"""

from fastapi import FastAPI, HTTPException

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

TAREAS = ("transmitir", "vencer", "cadena", "volcado")


@app.post("/tareas/{nombre}")
def ejecutar(nombre: str) -> dict:
    """Ejecuta una tarea programada.

    PENDIENTE (F5): implementar cada tarea. El relleno responde 501 para que
    se note en los registros que la tarea existe pero no hace nada.
    """
    if nombre not in TAREAS:
        raise HTTPException(status_code=404, detail="tarea desconocida")
    raise HTTPException(status_code=501, detail=f"{nombre}: sin implementar")
