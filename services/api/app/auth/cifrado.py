"""Cifrado de datos en la aplicacion: AES-256-GCM.

LG-05 exige que los datos personales se guarden cifrados. D-03 explica por que
el cifrado paso de OpenBao a la aplicacion: la base guarda texto cifrado y la
llave vive en Secret Manager, nunca en Neon. Un volcado de la base, solo, no
entrega ni una cedula ni un secreto TOTP.

    blob = cifrar("1-1234-0567", "datos_personales.cedula:9")
    descifrar(blob, "datos_personales.cedula:9")   -> "1-1234-0567"

El segundo argumento es el contexto, que GCM autentica sin cifrar (AAD). Ata
cada texto cifrado a su columna y a su fila: si alguien con acceso a la base
copia la cedula cifrada de la cuenta 9 sobre la de la cuenta 10, descifrarla
como la de la 10 falla en vez de devolver la cedula ajena.

Formato del blob: 1 byte de version, 12 de nonce, el texto cifrado y 16 de
etiqueta. La version deja cambiar de algoritmo o de llave sin perder lo viejo.

GCM y no CBC porque autentica: si alguien altera un byte del blob, descifrar
falla en vez de devolver basura. Y AESGCM de la biblioteca cryptography, no
una implementacion propia.
"""

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app import config

VERSION = b"\x01"
_NONCE = 12


class SinLlave(RuntimeError):
    """No hay LLAVE_CIFRADO_DATOS configurada, o no mide 32 bytes."""


class DatoAlterado(ValueError):
    """El blob no descifra con este contexto: fue alterado o es de otra fila."""


def _llave() -> AESGCM:
    secreto = config.LLAVE_CIFRADO_DATOS
    if secreto is None:
        raise SinLlave(
            "Falta LLAVE_CIFRADO_DATOS. Generala con: python -c \"import "
            "secrets; print(secrets.token_urlsafe(32))\"")
    # strip(): un secreto creado desde PowerShell suele traer un salto de
    # linea al final, y Secret Manager lo guarda tal cual.
    texto = secreto.revelar().strip()
    try:
        crudo = base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))
    except ValueError:
        raise SinLlave("LLAVE_CIFRADO_DATOS no es base64 url") from None
    if len(crudo) != 32:
        raise SinLlave("LLAVE_CIFRADO_DATOS tiene que dar 32 bytes (AES-256)")
    return AESGCM(crudo)


def cifrar(texto: str, contexto: str) -> bytes:
    """Cifra con un nonce aleatorio nuevo. Mismo texto, blobs distintos."""
    nonce = os.urandom(_NONCE)
    cifrado = _llave().encrypt(nonce, texto.encode("utf-8"),
                               contexto.encode("utf-8"))
    return VERSION + nonce + cifrado


def descifrar(blob: bytes, contexto: str) -> str:
    """Descifra y comprueba la etiqueta. Lanza DatoAlterado si no cuadra."""
    blob = bytes(blob)
    if len(blob) < 1 + _NONCE + 16 or blob[:1] != VERSION:
        raise DatoAlterado("formato de blob desconocido")
    nonce, cifrado = blob[1:1 + _NONCE], blob[1 + _NONCE:]
    try:
        claro = _llave().decrypt(nonce, cifrado, contexto.encode("utf-8"))
    except InvalidTag:
        raise DatoAlterado(
            "el dato no corresponde a este contexto o fue alterado") from None
    return claro.decode("utf-8")
