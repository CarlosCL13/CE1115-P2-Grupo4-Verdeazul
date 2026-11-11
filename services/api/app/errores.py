"""Errores que el backend le devuelve al borde, con una forma unica.

    {"detail": "codigo_legible_por_maquina", "mensaje": "...", ...}

`detail` es el mismo campo que usa FastAPI para sus propios errores, asi el
borde lee siempre el mismo lugar. El codigo no revela estructura interna: dice
que paso ("sin_sesion", "denegado"), no por que la politica lo decidio. El
porque va a la bitacora.
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class ErrorAPI(Exception):
    def __init__(self, estado: int, codigo: str, mensaje: str | None = None,
                 **extra) -> None:
        super().__init__(codigo)
        self.estado = estado
        self.codigo = codigo
        self.mensaje = mensaje
        self.extra = extra


async def manejar_error_api(_: Request, error: ErrorAPI) -> JSONResponse:
    cuerpo = {"detail": error.codigo, **error.extra}
    if error.mensaje:
        cuerpo["mensaje"] = error.mensaje
    return JSONResponse(status_code=error.estado, content=cuerpo)


async def manejar_denegado(_: Request, __: Exception) -> JSONResponse:
    """403 sin detalles. El motivo ya quedo en la bitacora (contrato 02)."""
    return JSONResponse(status_code=403, content={"detail": "denegado"})
