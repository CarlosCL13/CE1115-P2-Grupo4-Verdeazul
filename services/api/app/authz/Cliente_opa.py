import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

# El cliente de OPA es un singleton que se comparte entre todas las peticiones
URL_POR_OMISION = "http://127.0.0.1:8181/v1/data/verdeazul/autorizacion/decision"

URL_DECISION = os.getenv("OPA_URL", URL_POR_OMISION) # si no encuentra OPA_URL, usa la URL por omision

# El tiempo limite para las peticiones al motor de politicas
TIEMPO_LIMITE = httpx.Timeout(connect=0.5, read=2.0, write=0.5, pool=0.5)

# cliente HTTP para comunicarse con OPA
cliente = httpx.Client(
    timeout=TIEMPO_LIMITE,
    limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
    trust_env=False,
)

# Se define una excepción propia para cuando el motor de políticas no responde o responde algo inesperado
class ErrorDelMotor(RuntimeError):
    """El motor no respondio, o respondio algo que no se puede interpretar.
    Quien la capture tiene que negar. No existe ningun caso en el que está excepcion signifique "siga adelante".
    """

def consultar(entrada: dict[str, Any]) -> dict[str, Any]:
    try:
        # Se envia la peticion a OPA y se espera la respuesta
        respuesta = cliente.post(URL_DECISION, json={"input": entrada})
        respuesta.raise_for_status() # si la respuesta no es 200, lanza httpx.HTTPStatusError
        cuerpo_respuesta = respuesta.json() # se espera un JSON con la decision del motor
    except Exception as error:
        raise ErrorDelMotor(f"El motor de politicas no respondió: {error!r}") from error

    # Se espera que la respuesta tenga un campo "result" con la decision del motor
    if "result" not in cuerpo_respuesta:
        raise ErrorDelMotor(
            "El motor respondió sin 'result': la regla no existe o no se puede evaluar"
        )

    # Se espera que el campo "result" sea un diccionario con la decision del motor
    decision = cuerpo_respuesta["result"]
    if not isinstance(decision, dict) or "permitido" not in decision:
        raise ErrorDelMotor(
            f"El motor respondió con una decision con forma inesperada: {decision!r}"
        )

    # Se retorna la decisión del motor
    return decision

# Se obtiene la URL base del motor de políticas
def _obtener_url_base() -> str:
    partes = urlsplit(URL_DECISION)
    return urlunsplit((partes.scheme, partes.netloc, "", "", ""))

# Verifica si el motor de politicas esta disponible, petición a /health de OPA
# Si el motor no responde con 200, se considera que no está disponible (caído)
def OPA_disponible() -> bool:
    try:
        respuesta = cliente.get(f"{_obtener_url_base()}/health")
        # regresa True si el motor responde con 200, False en cualquier otro caso
        return respuesta.status_code == 200 
    except Exception:
        return False
