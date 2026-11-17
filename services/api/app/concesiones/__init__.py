"""Concesiones: O7 consentimientos y O8 asignaciones 

Este paquete junta O7 y O8 en uno solo, que es el que
main.py registra. 

"""

from fastapi import APIRouter

from app.concesiones import asignaciones, consentimientos

router = APIRouter()
router.include_router(asignaciones.router)
router.include_router(consentimientos.router)

__all__ = ["router"]
