from .Modelos_opa import Sujeto, Objeto, Decision, Operacion
from datetime import date
from . import Cliente_opa as cliente_opa # importa todo lo definido en el cliente_opa.py

# Servicio de consulta de autorización
def servicio_consulta_autorizacion(sujeto: Sujeto, operacion: Operacion, objeto: Objeto) -> Decision:
    # Se crea la petición que se enviará al motor de políticas OPA
    peticion = {
        "sujeto": {
            "id": sujeto.id,
            "rol": sujeto.rol,
            "zonas": sujeto.zonas,
        },
        "operacion": operacion,
        "objeto": {"tipo": objeto.tipo, "atributos": _atributos(objeto)}
    }

    try:
        respuesta_decision = cliente_opa.consultar(peticion) # diccionario con la decision del motor
    except cliente_opa.ErrorDelMotor as error:
        return Decision(
            permitido=False,
            motivo=f"El motor de politicas no pudo decidir, se deniega: {error}",
            condicion=None,
            version_politica=None,
        )

    permitido = respuesta_decision.get("permitido") is True # True si el motor dijo que sí, False si dijo que no

    return Decision(
        permitido=permitido, # un booleano que indica si la operación está permitida o no
        motivo=str(respuesta_decision.get("motivo", "el motor no explico la decisión")),
        condicion=respuesta_decision.get("condicion") or None,
        version_politica=respuesta_decision.get("version_politica") or None
    )

# Función auxiliar para obtener los atributos del objeto, agregando la fecha de hoy
def _atributos(objeto: Objeto) -> dict[str, object]:
    atributos = dict(objeto.atributos)
    atributos.setdefault("contexto.hoy", date.today().isoformat())
    return atributos

# Función para verificar si el motor de políticas OPA está disponible
def motor_disponible() -> bool:
    return cliente_opa.OPA_disponible()