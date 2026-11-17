"""Verificacion de un certificado a partir del archivo. Sin base de datos (D-09).

Quien verifica trae el archivo. Aqui se responden dos preguntas distintas:

1. ¿El contenido cambio desde que se firmo?
   Se recalcula la forma canonica del contenido y se comprueba la firma con
   la clave publica que viaja en el mismo archivo. Si alguien cambio una
   letra, la firma no cuadra.

2. ¿Lo firmo Verdeazul?
   La pregunta 1 sola no alcanza: cualquiera puede generar su propio par de
   llaves, escribir un certificado falso y firmarlo, y la firma cuadraria con
   la clave publica que el mismo puso en el archivo. Por eso ademas se
   compara la huella de esa clave con la huella de Verdeazul, que se publica
   por un canal aparte (D-10).

Un certificado es valido solo si las dos respuestas son si.

Todo es estricto a proposito. Un campo de mas fuera de `contenido` se
rechaza, porque no esta firmado y alguien podria usarlo para mostrar un dato
falso junto a una firma valida. Una llave repetida en el JSON tambien se
rechaza: dos programas distintos podrian leer valores distintos del mismo
archivo, y uno veria lo que el otro verifico.

Este modulo no importa nada de la base ni de la sesion, y se prueba solo
(tests/certificados/test_firma.py).
"""

import dataclasses
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.certificados import firma

# Un certificado real pesa unos 2 KB. Con 64 KB sobra, y un archivo enorme no
# llega a ocupar memoria ni tiempo de CPU.
MAXIMO_BYTES = 64 * 1024

_LLAVES_DOCUMENTO = {"formato", "contenido", "firma"}
_LLAVES_FIRMA = {"algoritmo", "llave_publica", "huella_llave", "valor"}


class FormatoInvalido(ValueError):
    """El archivo no tiene la forma de un certificado de Verdeazul."""


@dataclasses.dataclass(frozen=True)
class Resultado:
    valido: bool                  # las dos cosas: intacto y de Verdeazul
    firma_valida: bool            # el contenido no cambio
    llave_de_verdeazul: bool      # la llave que firmo es la de Verdeazul
    motivo: str                   # valido | formato_invalido | firma_invalida | llave_desconocida
    huella_llave: str | None = None
    contenido: dict | None = None  # solo si es valido, para mostrarlo


def _sin_repetidas(pares):
    objeto = {}
    for clave, valor in pares:
        if clave in objeto:
            raise FormatoInvalido("llave repetida: %r" % clave)
        objeto[clave] = valor
    return objeto


def _sin_constantes(valor):
    raise FormatoInvalido("NaN e Infinity no son JSON valido: %r" % valor)


def leer(texto: str) -> dict:
    """Convierte el texto del archivo en un dict, o lanza FormatoInvalido."""
    if not isinstance(texto, str):
        raise FormatoInvalido("no es texto")
    if len(texto.encode("utf-8")) > MAXIMO_BYTES:
        raise FormatoInvalido("archivo demasiado grande")
    try:
        documento = json.loads(texto, object_pairs_hook=_sin_repetidas,
                               parse_constant=_sin_constantes)
    except FormatoInvalido:
        raise
    except (ValueError, RecursionError):
        raise FormatoInvalido("no es JSON") from None
    if not isinstance(documento, dict):
        raise FormatoInvalido("no es un objeto JSON")
    return documento


def _partes(documento: dict) -> tuple[dict, bytes, bytes, str]:
    if set(documento) != _LLAVES_DOCUMENTO:
        raise FormatoInvalido("campos del documento")
    if documento["formato"] != firma.FORMATO:
        raise FormatoInvalido("formato desconocido")
    contenido = documento["contenido"]
    bloque = documento["firma"]
    if not isinstance(contenido, dict) or not isinstance(bloque, dict):
        raise FormatoInvalido("contenido o firma no son objetos")
    if set(bloque) != _LLAVES_FIRMA:
        raise FormatoInvalido("campos de la firma")
    if bloque["algoritmo"] != firma.ALGORITMO:
        raise FormatoInvalido("algoritmo distinto de Ed25519")
    try:
        publica = firma.desb64(bloque["llave_publica"])
        valor = firma.desb64(bloque["valor"])
    except ValueError:
        raise FormatoInvalido("base64 invalido") from None
    if len(publica) != 32 or len(valor) != 64:
        raise FormatoInvalido("largo de llave o de firma")
    # La huella escrita en el archivo no esta firmada: se recalcula y, si no
    # coincide con la llave, el archivo es incoherente.
    calculada = firma.huella(publica)
    if bloque["huella_llave"] != calculada:
        raise FormatoInvalido("la huella no corresponde a la llave")
    return contenido, publica, valor, calculada


def verificar(documento: dict, huellas_confiables: set[str] | frozenset[str]
              ) -> Resultado:
    """Comprueba un certificado ya leido con leer().

    `huellas_confiables` son las huellas publicadas de Verdeazul. Se pasan
    como argumento para que este modulo no dependa de la configuracion y se
    pueda probar con llaves inventadas.
    """
    try:
        contenido, publica, valor, huella = _partes(documento)
        mensaje = firma.canonico(contenido)
    except (FormatoInvalido, TypeError, ValueError):
        return Resultado(False, False, False, "formato_invalido")

    try:
        Ed25519PublicKey.from_public_bytes(publica).verify(valor, mensaje)
        firma_valida = True
    except InvalidSignature:
        firma_valida = False

    de_verdeazul = huella in huellas_confiables
    if not firma_valida:
        motivo = "firma_invalida"
    elif not de_verdeazul:
        motivo = "llave_desconocida"
    else:
        motivo = "valido"
    valido = firma_valida and de_verdeazul
    return Resultado(valido, firma_valida, de_verdeazul, motivo, huella,
                     contenido if valido else None)


def verificar_texto(texto: str, huellas_confiables: set[str] | frozenset[str]
                    ) -> Resultado:
    """leer() y verificar() juntos. Lo que usa el endpoint publico."""
    try:
        documento = leer(texto)
    except FormatoInvalido:
        return Resultado(False, False, False, "formato_invalido")
    return verificar(documento, huellas_confiables)
