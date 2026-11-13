"""Comun a las pruebas de O8 asignaciones tecnico-zona.

De integracion, con la misma base desechable y el mismo OPA real que
certificacion. Se saltan si no hay base.

    bash tests/identidad/preparar_bd.sh
    opa run --server --addr=127.0.0.1:8181 services/policies/rego &
    VERDEAZUL_PRUEBAS_BD="postgresql://app_rw@localhost:5432/neondb" \
        pytest tests/asignaciones -v

La base de pruebas NUNCA es Neon.
"""

import importlib.util
import pathlib

_ruta = pathlib.Path(__file__).parents[1] / "certificacion" / "conftest.py"
_especificacion = importlib.util.spec_from_file_location(
    "conftest_certificacion", _ruta)
_certificacion = importlib.util.module_from_spec(_especificacion)
_especificacion.loader.exec_module(_certificacion)

llaves_de_prueba = _certificacion.llaves_de_prueba
grupo = _certificacion.grupo
api = _certificacion.api
fabrica = _certificacion.fabrica
entrar = _certificacion.entrar
