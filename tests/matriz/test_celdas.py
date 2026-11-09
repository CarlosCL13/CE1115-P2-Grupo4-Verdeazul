import pytest
from conf_test_celdas import celdas_concedidas, celdas_denegadas

from app.authz import Cliente_opa
from app.authz.Modelos_opa import Decision, Objeto, Sujeto
from app.authz.Servicio_opa import servicio_consulta_autorizacion

# Quien pregunta en las 968. Se le cambia solo el rol; el id y la zona son
# fijos, y de ellos dependen los atributos de mas abajo.
SUJETO_ID = "u-prueba"
ZONA_ASIGNADA = "norte"

# Un futuro y un pasado lejanos, para que las ventanas de C7 y C9 no caduquen
# con el calendario.
LEJOS = "2999-12-31"
HACE_MUCHO = "2000-01-01"


def _sujeto(rol: str) -> Sujeto:
    return Sujeto(id=SUJETO_ID, rol=rol, zonas=(ZONA_ASIGNADA,))


ATRIBUTOS_QUE_CUMPLEN: dict[str, dict[str, object]] = {
    "C1": {"finca.zona": ZONA_ASIGNADA},
    "C2": {"periodo.estado": "ABIERTO"},
    "C3": {
        "medicion.autor_id": "u-otro",
        "contexto.sujeto_midio_en_finca_periodo": False,
    },
    "C4": {"enmienda.solicitante_id": "u-otro"},
    "C5": {
        "enmienda.estado": "REVISADA",
        "enmienda.solicitante_id": "u-otro",
        "enmienda.revisor_id": "u-tercero",
    },
    "C6": {
        "medicion.estado": "APROBADA",
        "medicion.autor_id": "u-otro",
        "contexto.poligono_traslapa_certificado_vigente": False,
    },
    "C7": {"auditoria.inicio": HACE_MUCHO, "auditoria.fin": LEJOS},
    "C8": {"finca.propietario_id": SUJETO_ID},
    "C9": {"autorizacion.tercero_id": SUJETO_ID, "autorizacion.vence": LEJOS},
    "C10": {
        "cambio.aprobador_id": "u-direccion",
        "cambio.aprobador_rol": "DIRECCION_GENERAL",
    },
    "C11": {"medicion.autor_id": SUJETO_ID, "periodo.estado": "CERRADO"},
}

def _atributos_de(condicion: str | None) -> dict[str, object]:
    if condicion is None:
        return {}

    if condicion == "C1yC2":
        ids_condiciones = ["C1", "C2"]
    else:
        ids_condiciones = [condicion] # condiciones que están en una celda

    atributos_objeto: dict[str, object] = {}
    for id_condicion in ids_condiciones:
        atributos_objeto.update(ATRIBUTOS_QUE_CUMPLEN[id_condicion])
    return atributos_objeto 

# Verifica que el motor de politicas este levantado
@pytest.fixture(scope="session", autouse=True)
def motor() -> None:
    if not Cliente_opa.OPA_disponible():
        pytest.skip(
            f"el motor de politicas no responde en {Cliente_opa.URL_DECISION}. "
            "Levantalo con `docker compose up -d` o con "
            "`opa run --server --addr=127.0.0.1:8181 services/policies/rego`"
        )

# ---------------------------------------------------------------------------
# 884 casos: lo que la matriz no concede
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("rol", "objeto", "operacion"),
    list(celdas_denegadas()),
    ids=lambda v: str(v),
)
def test_lo_no_concedido_se_niega(rol: str, objeto: str, operacion: str) -> None:
    decision = servicio_consulta_autorizacion(_sujeto(rol), operacion, Objeto(tipo=objeto))

    # Si la matriz no concede, el motor debe negarlo
    assert isinstance(decision, Decision)
    assert not decision.permitido, (
        f"{rol} NO deberia poder {operacion} sobre {objeto}, y el motor lo "
        f"permitio: {decision.motivo}"
    )

# ---------------------------------------------------------------------------
# 84 casos: lo que la matriz concede
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("rol", "objeto", "operacion", "condicion"),
    list(celdas_concedidas()),
    ids=lambda v: str(v),
)
def test_lo_concedido_se_permite(rol: str, objeto: str, operacion: str, condicion: str | None) -> None:
    decision = servicio_consulta_autorizacion(
        _sujeto(rol),
        operacion,
        Objeto(tipo=objeto, atributos=_atributos_de(condicion)),
    )

    # Si se cumple la condicion, el motor debe permitirlo
    assert decision.permitido, (
        f"{rol} deberia poder {operacion} sobre {objeto}"
        + (f" cumpliendo {condicion}" if condicion else "")
        + f", y el motor lo nego: {decision.motivo}"
    )

# ---------------------------------------------------------------------------
# La tabla
# ---------------------------------------------------------------------------
# Verifica que la matriz de permisos este completa, es decir, que todas las celdas
# esten definidas, ya sea concediendo o negando.
def test_la_matriz_esta_completa() -> None:
    celdas = {(rol, objeto) for rol, objeto, _, _ in celdas_concedidas()}
    celdas |= {(rol, objeto) for rol, objeto, _ in celdas_denegadas()}
    assert len(celdas) == 88, f"se esperaban 88 celdas definidas, hay {len(celdas)}"
