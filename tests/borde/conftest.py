"""El borde contra un backend de mentira.

El borde no decide nada: pide al backend y dibuja. Estas pruebas cambian
api.llamar por un backend falso que contesta lo que cada prueba necesita, y
comprueban lo que si es del borde: que las paginas se dibujen, las cabeceras
de seguridad, el CSRF, el control de origen, y como traduce cada respuesta
del backend (403, 401 de reautenticacion, backend caido).

No abre ningun puerto ni toca ninguna base.
"""

import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app import api, web
from app.main import app as borde

ORIGEN = "http://localhost:8081"
TOKEN = "token-de-prueba"

ROLES = ("DIRECCION_GENERAL", "DIRECCION_CERTIFICACION",
         "PERSONAL_ADMINISTRATIVO", "TECNICO_CAMPO", "VERIFICADOR",
         "AUDITOR_EXTERNO", "DUENO_FINCA", "TERCERO_AUTORIZADO")

# Lo que devuelve un listado vacio, con las claves que leen las plantillas.
VACIO = {
    "fincas": [], "periodos": [], "mediciones": [], "enmiendas": [],
    "asignaciones": [], "certificados": [], "consentimientos": [],
    "personas": [], "cuentas": [], "solicitudes": [], "eventos": [],
    "zonas": [], "terceros": [], "total": 0, "pagina": 1, "paginas": 1,
    "primera_fila": 0, "pendientes_de_transmitir": 0,
}


def _respuesta(metodo, ruta, estado, cuerpo):
    return httpx.Response(estado, json=cuerpo,
                          request=httpx.Request(metodo, "http://backend" + ruta))


class Backend:
    """Contesta como el backend. `fijar` cambia la respuesta de una ruta."""

    def __init__(self):
        self.rol = "DIRECCION_GENERAL"
        self.fijas = []
        self.llamadas = []
        self.caido = False

    def fijar(self, metodo, patron, estado, cuerpo):
        self.fijas.append((metodo, re.compile(patron), estado, cuerpo))

    def sesion(self):
        return {"cuenta": 1, "usuario": "prueba", "nombre": "Persona de prueba",
                "rol": self.rol, "zonas": ["PN"],
                "expira_en": "2026-11-19T23:00:00",
                "segundo_factor": {"requerido": False, "activo": True,
                                   "verificado": True},
                "debe_cambiar": False, "reautenticada": True,
                "siguiente": "listo"}

    def __call__(self, metodo, ruta, sesion=None, json=None, params=None):
        if self.caido:
            raise api.BackendCaido("prueba")
        self.llamadas.append((metodo, ruta, json))
        for m, patron, estado, cuerpo in self.fijas:
            if m == metodo and patron.fullmatch(ruta):
                return _respuesta(metodo, ruta, estado, cuerpo)
        if ruta == "/auth/sesion":
            if not sesion:
                return _respuesta(metodo, ruta, 401, {"detail": "sin_sesion"})
            return _respuesta(metodo, ruta, 200, self.sesion())
        if metodo == "GET":
            return _respuesta(metodo, ruta, 200, dict(VACIO))
        return _respuesta(metodo, ruta, 200, {"id": 1, "estado": "OK"})


@pytest.fixture
def backend(monkeypatch):
    falso = Backend()
    monkeypatch.setattr(api, "llamar", falso)
    return falso


@pytest.fixture
def anonimo(backend):
    return TestClient(borde, base_url=ORIGEN)


@pytest.fixture
def con_sesion(backend):
    cliente = TestClient(borde, base_url=ORIGEN)
    cliente.cookies.set(web.COOKIE, TOKEN)
    return cliente


@pytest.fixture
def csrf():
    return web.csrf(TOKEN)
