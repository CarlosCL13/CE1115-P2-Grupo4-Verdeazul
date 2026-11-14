"""Firma de certificados con Ed25519. Control 2.3.6 del enunciado, D-10.

Un certificado es un archivo JSON con tres partes:

    {
      "formato":   "verdeazul-certificado-carbono/1",
      "contenido": { ...lo que se certifica... },      <- esto es lo firmado
      "firma": {
        "algoritmo":     "Ed25519",
        "llave_publica": "...",      la clave publica, viaja en el documento
        "huella_llave":  "SHA256:...",
        "valor":         "..."       la firma de `contenido`
      }
    }

Lo que se firma no es el texto tal como quedo en el archivo, sino una forma
canonica de `contenido`: llaves ordenadas, sin espacios, UTF-8. Asi, si
alguien abre el archivo y lo vuelve a guardar con otra sangria, la firma
sigue valiendo; si cambia una sola letra de un valor, deja de valer.

Delante del contenido se firma un prefijo fijo (DOMINIO). Sirve para que una
firma de Verdeazul sobre un certificado no se pueda hacer pasar por la firma
de otra cosa que algun dia se firme con la misma llave.

Ningun valor del contenido es un numero con decimales: las toneladas van como
texto ("120.500"). Un float se puede escribir de varias formas (120.5,
120.50) y cada una da bytes distintos.

La llave privada sale de config.LLAVE_FIRMA_CERTIFICADOS, que en la nube
inyecta Secret Manager. Este modulo nunca la escribe, la registra ni la
devuelve: solo la usa para firmar.
"""

import base64
import datetime
import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (Encoding,
                                                          PublicFormat)

from app import config

FORMATO = "verdeazul-certificado-carbono/1"
ALGORITMO = "Ed25519"
DOMINIO = FORMATO.encode() + b"\n"
EMISOR = "Verdeazul Carbono S.A."


class SinLlaveFirma(RuntimeError):
    """No hay llave de firma configurada, o la que hay no sirve."""


def b64(datos: bytes) -> str:
    """Base64 url, sin el relleno '=' del final."""
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def desb64(texto: str) -> bytes:
    """Lo inverso de b64(). Lanza ValueError si el texto no es base64."""
    if not isinstance(texto, str):
        raise ValueError("no es texto")
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def canonico(contenido: dict) -> bytes:
    """Los bytes exactos que se firman: el prefijo y el contenido ordenado."""
    texto = json.dumps(contenido, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False)
    return DOMINIO + texto.encode("utf-8")


def huella(llave_publica: bytes) -> str:
    """Huella de una clave publica: SHA-256 de sus 32 bytes, en hexadecimal.

    Es lo que se compara con la huella publicada de Verdeazul. Comparar 64
    caracteres es mas facil que comparar la llave entera, y es igual de
    seguro.
    """
    return "SHA256:" + hashlib.sha256(llave_publica).hexdigest()


def _llave_privada() -> Ed25519PrivateKey:
    secreto = config.LLAVE_FIRMA_CERTIFICADOS
    if secreto is None:
        raise SinLlaveFirma("falta LLAVE_FIRMA_CERTIFICADOS")
    try:
        crudo = desb64(secreto.revelar())
    except ValueError:
        raise SinLlaveFirma("LLAVE_FIRMA_CERTIFICADOS no es base64") from None
    if len(crudo) != 32:
        raise SinLlaveFirma("LLAVE_FIRMA_CERTIFICADOS no tiene 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(crudo)


def llave_publica_verdeazul() -> bytes:
    """Los 32 bytes de la clave publica que corresponde a la privada."""
    return _llave_privada().public_key().public_bytes(Encoding.Raw,
                                                      PublicFormat.Raw)


def huella_verdeazul() -> str:
    """La huella de la llave con la que firma este sistema.

    Es la que se publica por un canal aparte (D-10) y contra la que compara
    la verificacion publica. Se calcula de la llave privada en vez de
    guardarse aparte, asi no puede quedar desincronizada.
    """
    return huella(llave_publica_verdeazul())


def ahora() -> datetime.datetime:
    """La hora de emision: UTC y sin microsegundos, para que el texto sea
    siempre el mismo al firmarlo y al guardarlo."""
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def fecha_texto(momento: datetime.datetime) -> str:
    return momento.astimezone(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def firmar(contenido: dict) -> dict:
    """Firma el contenido y devuelve el documento completo, listo para
    guardar y entregar."""
    privada = _llave_privada()
    publica = privada.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    valor = privada.sign(canonico(contenido))
    return {
        "formato": FORMATO,
        "contenido": contenido,
        "firma": {
            "algoritmo": ALGORITMO,
            "llave_publica": b64(publica),
            "huella_llave": huella(publica),
            "valor": b64(valor),
        },
    }


def documento_texto(documento: dict) -> str:
    """El archivo que se guarda y se descarga: JSON legible, con sangria.

    La sangria no afecta la firma, porque se verifica la forma canonica.
    """
    return json.dumps(documento, ensure_ascii=False, indent=2,
                      sort_keys=False)
