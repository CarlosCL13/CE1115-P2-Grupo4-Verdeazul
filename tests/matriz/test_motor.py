
import pytest
from usuarios_prueba import USUARIOS

from app.authz import Cliente_opa as cliente_opa
from app.authz.Modelos_opa import Objeto
from app.authz.Servicio_opa import servicio_consulta_autorizacion

DG = USUARIOS["direccion"]
TC = USUARIOS["tecnico"]
VF = USUARIOS["verificador"]
DF = USUARIOS["dueno"]
TA = USUARIOS["tercero"]

@pytest.fixture(scope="session", autouse=True)
def motor() -> None:
    if not cliente_opa.OPA_disponible():
        pytest.skip(
            f"el motor de politicas no responde en {cliente_opa.URL_DECISION}.")

# ---------------------------------------------------------------------------
# 1. El motor autoriza por permiso directo, sin condicion
# ---------------------------------------------------------------------------
def test_el_motor_responde() -> None:
    decision = servicio_consulta_autorizacion(DG, "L", Objeto(tipo="O1"))

    assert decision.permitido is True # dirección general puede leer sobre O1
    assert decision.condicion is None # no hay condicion, es un permiso directo

# ---------------------------------------------------------------------------
# 2. Regla 1 que no se negocia, lo que no esta concedido en la matriz, se niega
# ---------------------------------------------------------------------------
def test_denegacion_por_omision() -> None:
    decision = servicio_consulta_autorizacion(TA, "L", Objeto(tipo="O11"))

    assert decision.permitido is False
    assert decision.condicion is None

# Un dueño de finca no puede modificar el catálogo de fincas
def test_abac_no_agrega_lo_que_el_rol_no_tiene() -> None:
    decision = servicio_consulta_autorizacion(
        DF, "M", Objeto(tipo="O1", atributos={"finca.propietario_id": DF.id})
    )

    assert decision.permitido is False
    assert decision.condicion is None

# Ningun rol tiene permiso de borrado sobre nada
def test_nadie_elimina_nunca() -> None:
    decision = servicio_consulta_autorizacion(DG, "E", Objeto(tipo="O1"))

    assert decision.permitido is False
    assert decision.condicion is None

# Ningun rol tiene permiso de modificacion sobre O3, todo pasa por una enmienda (O4)
def test_nadie_modifica_una_medicion() -> None:
    decision = servicio_consulta_autorizacion(VF, "M", Objeto(tipo="O3"))

    assert decision.permitido is False
    assert decision.condicion is None

# ---------------------------------------------------------------------------
# 3. Tres condiciones representativas, en los dos sentidos
# ---------------------------------------------------------------------------
def test_c1_zona_asignada() -> None:
    # Un tecnico de campo consulta si puede leer una finca de su zona (permitido)
    consulta_propia = servicio_consulta_autorizacion(TC, "L", Objeto(tipo="O1", atributos={"finca.zona": "norte"}))
    assert consulta_propia.permitido is True, consulta_propia.motivo

    # Un tecnico de campo consulta si puede leer una finca que no es de su zona (no permitido)
    consulta_ajena = servicio_consulta_autorizacion(TC, "L", Objeto(tipo="O1", atributos={"finca.zona": "pacifico"}))
    assert consulta_ajena.permitido is False
    assert consulta_ajena.condicion == "C1"

    # Un tecnico de campo consulta si puede leer una finca sin enviar la zona a la que fue asignado (se niega)
    consulta_sin_atributo = servicio_consulta_autorizacion(TC, "L", Objeto(tipo="O1"))
    assert consulta_sin_atributo.permitido is False
    assert consulta_sin_atributo.condicion == "C1"


def test_c3_separacion_de_deberes_al_aprobar() -> None:
    # Un verificador sí puede aprobar una medición que hizo otro técnico de campo
    consulta_meidicion_ajena = servicio_consulta_autorizacion(
        VF,
        "A",
        Objeto(
            tipo="O3",
            atributos={
                "medicion.autor_id": TC.id,
                "contexto.sujeto_midio_en_finca_periodo": False,
            },
        ),
    )
    assert consulta_meidicion_ajena.permitido is True, consulta_meidicion_ajena.motivo

    # Un verificador no puede aprobar una medición que hizo él mismo
    consulta_medicion_propia = servicio_consulta_autorizacion(
        VF,
        "A",
        Objeto(
            tipo="O3",
            atributos={
                "medicion.autor_id": VF.id,
                "contexto.sujeto_midio_en_finca_periodo": False,
            },
        ),
    )
    assert consulta_medicion_propia.permitido is False
    assert consulta_medicion_propia.condicion == "C3"

    # Un verificador no puede aprobar una medición que hizo otro técnico de campo que midió en la misma finca y periodo
    consulta_medicion_ajena_traslapada = servicio_consulta_autorizacion(
        VF,
        "A",
        Objeto(
            tipo="O3",
            atributos={
                "medicion.autor_id": TC.id,
                "contexto.sujeto_midio_en_finca_periodo": True,
            },
        ),
    )
    assert consulta_medicion_ajena_traslapada.permitido is False


def test_c6_emision_de_certificado() -> None:
    base_atributos_objeto = {
        "medicion.estado": "APROBADA",
        "medicion.autor_id": TC.id,
        "contexto.poligono_traslapa_certificado_vigente": False, # no hay traslape
    }

    # Un verificador puede emitir un certificado sobre una medición aprobada que no traslapa otro certificado
    consulta_emision_correcta = servicio_consulta_autorizacion(VF, "Em", Objeto(tipo="O5", atributos=base_atributos_objeto))
    assert consulta_emision_correcta.permitido is True, consulta_emision_correcta.motivo

    # Un verificador no puede emitir un certificado sobre una medición aprobada que traslapa otro certificado vigente
    consulta_emision_traslape = servicio_consulta_autorizacion(
        VF,
        "Em",
        Objeto(
            tipo="O5",
            atributos={**base_atributos_objeto, "contexto.poligono_traslapa_certificado_vigente": True},
        )
    )
    assert consulta_emision_traslape.permitido is False
    assert consulta_emision_traslape.condicion == "C6"


    # Un verificador no puede emitir un certificado sobre una medición que no ha sido aprobada
    consulta_emision_sin_medicion_aprobada = servicio_consulta_autorizacion(
        VF, "Em", Objeto(tipo="O5", atributos={**base_atributos_objeto, "medicion.estado": "REGISTRADA"})
    )
    assert consulta_emision_sin_medicion_aprobada.permitido is False

    # Un verificador no puede emitir un certificado sobre una medición que él mismo midió
    consulta_emite_quien_midio = servicio_consulta_autorizacion(
        VF,
        "Em",
        Objeto(tipo="O5", atributos={**base_atributos_objeto, "medicion.autor_id": VF.id}),
    )
    assert consulta_emite_quien_midio.permitido is False
