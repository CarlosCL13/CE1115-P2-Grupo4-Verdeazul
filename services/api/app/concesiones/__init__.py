"""Concesiones: O7 consentimientos (Meibel) y O8 asignaciones (Adriel).

Un archivo por objeto, para que dos personas trabajen aqui sin pisarse. Cada
uno expone su router y este paquete los junta en uno solo, que es el que
main.py registra. O7 agrega aqui su linea cuando exista.
"""

from fastapi import APIRouter

from app.concesiones import asignaciones

router = APIRouter()
router.include_router(asignaciones.router)

__all__ = ["router"]
