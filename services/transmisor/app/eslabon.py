"""El eslabon de la cadena de la bitacora. Contrato 03, «La cadena».

    eslabon = HMAC-SHA256(llave, eslabon_anterior + "\\n" + evento_canonico)

Lo usan dos tareas: `transmitir`, que lo calcula al copiar cada evento, y
`cadena`, que lo recalcula leyendo la bitacora para ver si alguien la altero.
Las dos tienen que llegar al mismo resultado byte por byte, y por eso todo lo
que decide el resultado vive aqui y en ningun otro lugar.

Solo usa la biblioteca estandar. No abre conexiones ni lee el entorno: recibe
la llave ya decodificada, para que se pueda probar sin base y sin secretos.

La forma canonica sale solo de columnas que existen en la tabla `eventos` de
la bitacora (id, momento, accion, sujeto, objeto, resultado, motivo, detalle).
Asi `cadena` puede recalcular todo con log_reader, sin mirar la bandeja.

CUIDADO: cambiar algo de este archivo (un campo, el formato de la hora, el
separador, el espacio de ids) rompe la verificacion de todos los eventos que
ya estan en la bitacora, que no se pueden borrar. La prueba del vector fijo en
tests/test_eslabon.py existe para que eso no pase sin que nadie se entere.
"""

import base64
import binascii
import hashlib
import hmac
import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone

# El anterior del primer evento de la cadena.
INICIO = ""

# Espacio de nombres para derivar el uuid de la bitacora a partir del id de la
# bandeja (uuid5). Es un valor fijo y no secreto: lo que importa es que no
# cambie nunca, para que reintentar un evento de el mismo id y la bitacora lo
# salte en vez de duplicarlo.
ESPACIO_IDS = uuid.UUID("6f1d3c52-8a4e-5b0f-9c7d-2e8b4a1f0d36")


class LlaveInvalida(ValueError):
    """La llave de la cadena falta o no da 32 bytes."""


def llave_desde_texto(texto: str | None) -> bytes:
    """Decodifica la llave como la generan las demas: token_urlsafe(32).

    strip(): un secreto creado desde PowerShell suele traer un salto de linea
    al final, y ese salto cambiaria todos los eslabones.
    """
    if not texto:
        raise LlaveInvalida(
            "Falta LLAVE_CADENA_BITACORA. Tiene que ser la misma de Secret "
            "Manager (llave-cadena-bitacora).")
    texto = texto.strip()
    try:
        crudo = base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))
    except (ValueError, binascii.Error):
        raise LlaveInvalida("LLAVE_CADENA_BITACORA no es base64 url") from None
    if len(crudo) != 32:
        raise LlaveInvalida("LLAVE_CADENA_BITACORA tiene que dar 32 bytes")
    return crudo


def id_en_bitacora(id_bandeja: int) -> uuid.UUID:
    """El uuid con que un evento de la bandeja entra a la bitacora."""
    return uuid.uuid5(ESPACIO_IDS, str(int(id_bandeja)))


def _momento(valor: datetime) -> str:
    """La hora siempre en UTC y con microsegundos, que es lo que guarda
    timestamptz. Asi el mismo instante se escribe igual aunque la sesion de
    la base este en otra zona horaria."""
    if not isinstance(valor, datetime) or valor.tzinfo is None:
        raise ValueError("momento tiene que ser una fecha con zona horaria")
    return valor.astimezone(timezone.utc).isoformat(timespec="microseconds")


def canonico(evento: Mapping) -> bytes:
    """El evento escrito siempre igual: mismos campos, mismo orden.

    `detalle` sale de una columna jsonb en las dos bases, y jsonb ya normaliza
    lo que guarda, asi que el diccionario que lee `transmitir` de la bandeja y
    el que lee `cadena` de la bitacora son iguales. sort_keys hace que el
    orden de las claves tampoco importe.
    """
    datos = {
        "id": str(evento["id"]),
        "momento": _momento(evento["momento"]),
        "accion": str(evento["accion"]),
        "sujeto": str(evento["sujeto"]),
        "objeto": str(evento["objeto"]),
        "resultado": str(evento["resultado"]),
        "motivo": evento.get("motivo"),
        "detalle": evento.get("detalle"),
    }
    return json.dumps(datos, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def calcular(llave: bytes, anterior: str, evento: Mapping) -> str:
    """El eslabon de `evento`, encadenado al `anterior`. En hexadecimal.

    El anterior es INICIO o 64 caracteres hexadecimales, y el salto de linea
    nunca aparece en el JSON canonico, asi que la concatenacion no es ambigua.
    """
    mensaje = anterior.encode("ascii") + b"\n" + canonico(evento)
    return hmac.new(llave, mensaje, hashlib.sha256).hexdigest()


def coincide(esperado: str, calculado: str) -> bool:
    """Comparacion en tiempo constante, para la tarea `cadena`."""
    return hmac.compare_digest(esperado, calculado)
