"""Un solo router para O1, O2 y O3. El contrato 04 lo ubica en rutas.py."""

from fastapi import APIRouter

from app.certificacion import fincas, mediciones, periodos

router = APIRouter()
router.include_router(fincas.router)
router.include_router(periodos.router)
router.include_router(mediciones.router)
