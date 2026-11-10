"""Cedula y telefono: cifrados para guardarlos, HMAC para buscarlos.

LG-05 exige cifrar la cedula y el telefono. Pero el personal administrativo
necesita buscar a un dueno por cedula, y no se puede buscar en una columna
cifrada con nonce aleatorio: la misma cedula da un blob distinto cada vez.

La solucion son dos columnas:

    cedula_cifrada    AES-256-GCM, para leerla (app/auth/cifrado.py)
    cedula_busqueda   HMAC-SHA256 con llave, para encontrarla

El HMAC es determinista, asi que la misma cedula da siempre el mismo valor y
se busca con un WHERE normal y un indice UNIQUE. Lleva llave, y no es un
SHA-256 simple, porque una cedula de Costa Rica son nueve digitos: con un hash
sin llave, quien tenga un volcado calcula las mil millones de cedulas posibles
en minutos y las recupera todas. Con HMAC necesita ademas la llave, que vive en
Secret Manager y no en Neon (pregunta abierta 3 del esquema, resuelta asi).
"""

import hashlib
import hmac

from app import config
from app.auth import cifrado


class CedulaInvalida(ValueError):
    pass


def normalizar(cedula: str) -> str:
    """Solo los digitos. "1-1234-0567", "112340567" y "1 1234 0567" son la misma.

    Nueve digitos para la cedula fisica, diez para la juridica, once o doce
    para el DIMEX. Lo que no encaje no entra.
    """
    digitos = "".join(c for c in str(cedula) if c.isdigit())
    otros = "".join(c for c in str(cedula) if not c.isdigit() and c not in " -")
    if otros or not 9 <= len(digitos) <= 12:
        raise CedulaInvalida("La cédula tiene que tener entre 9 y 12 dígitos.")
    return digitos


def normalizar_telefono(telefono: str) -> str:
    limpio = "".join(c for c in str(telefono) if c.isdigit() or c == "+")
    otros = "".join(c for c in str(telefono)
                    if not (c.isdigit() or c in "+ -()"))
    digitos = limpio.lstrip("+")
    if otros or "+" in digitos or not 8 <= len(digitos) <= 15:
        raise CedulaInvalida("El teléfono tiene que tener entre 8 y 15 dígitos.")
    return limpio


def huella_busqueda(cedula_normalizada: str) -> bytes:
    """El HMAC con el que se busca. Version en el mensaje, por si cambia."""
    llave = config.LLAVE_BUSQUEDA_CEDULA
    if llave is None:
        raise cifrado.SinLlave("Falta LLAVE_BUSQUEDA_CEDULA.")
    # strip(): el mismo valor en el .env y en Secret Manager tiene que dar el
    # mismo HMAC, aunque uno de los dos traiga un salto de linea al final.
    return hmac.new(llave.revelar().strip().encode("utf-8"),
                    b"cedula:v1:" + cedula_normalizada.encode("ascii"),
                    hashlib.sha256).digest()


def _contexto(campo: str, cuenta: int) -> str:
    return "datos_personales.%s:%d" % (campo, cuenta)


def cifrar_cedula(cedula_normalizada: str, cuenta: int) -> bytes:
    return cifrado.cifrar(cedula_normalizada, _contexto("cedula", cuenta))


def descifrar_cedula(blob: bytes, cuenta: int) -> str:
    return cifrado.descifrar(blob, _contexto("cedula", cuenta))


def cifrar_telefono(telefono: str, cuenta: int) -> bytes:
    return cifrado.cifrar(telefono, _contexto("telefono", cuenta))


def descifrar_telefono(blob: bytes | None, cuenta: int) -> str | None:
    if blob is None:
        return None
    return cifrado.descifrar(blob, _contexto("telefono", cuenta))


def enmascarar(cedula_normalizada: str) -> str:
    """Para los listados: solo los ultimos cuatro. "*****0567"."""
    return "*" * (len(cedula_normalizada) - 4) + cedula_normalizada[-4:]
