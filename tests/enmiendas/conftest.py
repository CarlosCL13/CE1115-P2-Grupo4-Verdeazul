"""Comun a las pruebas de O4 enmiendas.

De integracion, como las de certificacion: la misma base desechable y el
mismo OPA real. Se saltan si no hay base.

    bash tests/identidad/preparar_bd.sh
    opa run --server --addr=127.0.0.1:8181 services/policies/rego &
    VERDEAZUL_PRUEBAS_BD="postgresql://app_rw@localhost:5432/neondb" \
        pytest tests/enmiendas -v

La base de pruebas NUNCA es Neon.
"""

import importlib.util
import pathlib

import pytest

# Las fixtures de certificacion (base, cliente, cuentas, fincas, periodos,
# mediciones) sirven tal cual. Se cargan del archivo porque dos conftest no
# se importan entre si.
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


def enmienda(fabrica, medicion, solicitante, estado="SOLICITADA",
             revisor=None):
    """Una enmienda directo en la base, para probar revisar y cerrar sin
    depender de que solicitar funcione."""
    return fabrica.sql(
        "INSERT INTO enmiendas (medicion, solicitante, justificacion, estado, "
        "revisor, revisada_en) VALUES (%s, %s, 'Correccion de prueba', %s, "
        "%s, CASE WHEN %s::int IS NULL THEN NULL ELSE now() END) RETURNING id",
        (medicion, solicitante["id"], estado,
         revisor["id"] if revisor else None,
         revisor["id"] if revisor else None))[0]["id"]


@pytest.fixture
def escenario(fabrica):
    """Una finca de PN con una medicion aprobada de un tecnico, en un periodo
    ya cerrado: lo justo para pedir una enmienda (C11)."""
    dueno = fabrica.cuenta("DUENO_FINCA")
    tecnico = fabrica.cuenta("TECNICO_CAMPO", zonas=("PN",))
    ver1 = fabrica.cuenta("VERIFICADOR", zonas=("PN",))
    ver2 = fabrica.cuenta("VERIFICADOR", zonas=("PN",))
    finca = fabrica.finca(dueno, "PN")
    periodo = fabrica.periodo("CERRADO")
    medicion = fabrica.medicion(finca, periodo, tecnico, "APROBADA", ver1)
    return {"dueno": dueno, "tecnico": tecnico, "ver1": ver1, "ver2": ver2,
            "finca": finca, "periodo": periodo, "medicion": medicion}
