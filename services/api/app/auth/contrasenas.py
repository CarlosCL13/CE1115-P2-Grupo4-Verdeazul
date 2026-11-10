"""Contrasenas: Argon2id con sal, y las reglas CO-01 a CO-05 de P1.

Este archivo es el control 2.3.1 del enunciado. §7.1: "contrasenas sin hash o
con hash rapido: se pierde la mitad del criterio de control de acceso".

    hashear(clave)           -> "$argon2id$v=19$m=19456,t=2,p=1$<sal>$<hash>"
    verificar(hash, clave)   -> True o False, nunca lanza
    problemas(clave, ...)    -> lista de reglas que la clave nueva no cumple

Por que Argon2id y no bcrypt: es el ganador del Password Hashing Competition y
la primera opcion de la OWASP. La variante id resiste los dos ataques que
importan: el de GPU (por la memoria que exige) y el de canal lateral.

Los parametros salen de config.ARGON2 y son los que fijo P1 siguiendo la
OWASP: 19 MiB, 2 iteraciones, 1 hilo. Viajan dentro de cada hash, asi que se
pueden subir mas adelante sin invalidar nada: al iniciar sesion se detecta un
hash con parametros viejos y se rehace (necesita_rehash).

La sal la genera argon2-cffi con os.urandom, 16 bytes, una distinta por cada
hash. Por eso dos personas con la misma clave tienen hashes distintos.
"""

import functools
import hashlib
import pathlib
import secrets
import unicodedata

import httpx
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app import config

# CO-01: minimo 15, y "hasta al menos 64". El tope existe porque Argon2 procesa
# lo que le den: sin tope, una clave de un megabyte es una forma barata de
# ocupar un hilo del servidor.
LARGO_MINIMO = 15
LARGO_MAXIMO = 128

_hasher = PasswordHasher(
    time_cost=config.ARGON2["iteraciones"],
    memory_cost=config.ARGON2["memoria_kib"],
    parallelism=config.ARGON2["hilos"],
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

_PROHIBIDAS = pathlib.Path(__file__).with_name("prohibidas.txt")


def normalizar(clave: str) -> str:
    """NFKC, como pide NIST SP 800-63B §5.1.1.2.

    Sin esto, una clave con una "n" con tilde escrita en un telefono y en un
    computador puede llegar con dos secuencias de bytes distintas y no
    coincidir nunca. Se aplica igual al guardar y al verificar.
    """
    return unicodedata.normalize("NFKC", clave)


def hashear(clave: str) -> str:
    """El hash Argon2id de la clave, con sal nueva. Nunca la clave."""
    return _hasher.hash(normalizar(clave))


def verificar(hash_guardado: str, clave: str) -> bool:
    """Si la clave corresponde al hash. Tiempo constante, nunca lanza."""
    try:
        return _hasher.verify(hash_guardado, normalizar(clave))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def necesita_rehash(hash_guardado: str) -> bool:
    """Si el hash se hizo con parametros distintos de los actuales."""
    try:
        return _hasher.check_needs_rehash(hash_guardado)
    except InvalidHashError:
        return True


@functools.cache
def hash_senuelo() -> str:
    """Un hash de algo que nadie conoce, para gastar el mismo tiempo.

    Cuando el usuario no existe se verifica contra esto. Sin el, responder
    "no" sin calcular nada tarda microsegundos y responder "no" a una clave
    equivocada tarda decenas de milisegundos: midiendo el tiempo se sabria que
    usuarios existen.
    """
    return hashear(secrets.token_urlsafe(32))


@functools.cache
def _lista_prohibida() -> frozenset[str]:
    """CO-02: las contrasenas comunes de 15 o mas caracteres.

    Solo las de 15 o mas, porque las cortas ya las rechaza CO-01. Asi la lista
    cabe en el repositorio (unas 16 mil) y se carga una sola vez.
    """
    lineas = _PROHIBIDAS.read_text(encoding="utf-8").splitlines()
    return frozenset(l for l in lineas if l and not l.startswith("# "))


def _filtrada(clave: str) -> bool:
    """CO-02: si la clave aparece en filtraciones conocidas.

    Have I Been Pwned por k-anonimato: se manda solo el comienzo del SHA-1, 5
    caracteres hexadecimales, y el servicio devuelve todos los sufijos que
    empiezan asi. La clave ni su hash completo salen nunca del servidor.

    Si el servicio no contesta no se bloquea el cambio: la lista local ya
    cubrio lo mas comun, y que un tercero caido impida cambiar una clave
    comprometida seria peor.
    """
    if not config.VERIFICAR_FILTRACIONES:
        return False
    huella = hashlib.sha1(clave.encode("utf-8")).hexdigest().upper()
    prefijo, sufijo = huella[:5], huella[5:]
    try:
        respuesta = httpx.get(
            "https://api.pwnedpasswords.com/range/" + prefijo,
            headers={"Add-Padding": "true"},
            timeout=3.0,
        )
        respuesta.raise_for_status()
    except httpx.HTTPError:
        return False
    for linea in respuesta.text.splitlines():
        candidato, _, veces = linea.partition(":")
        if candidato == sufijo and veces.strip() != "0":
            return True
    return False


def problemas(clave: str, usuario: str = "", nombre: str = "") -> list[str]:
    """Las reglas que la clave nueva no cumple. Vacia si sirve.

    Mensajes para la persona, no codigos: los muestra el formulario tal cual.
    Sin reglas de composicion (mayusculas, simbolos), a proposito: CO-01
    sigue a NIST, que las desaconseja porque producen "Password1!" anotado en
    un papel.
    """
    clave = normalizar(clave)
    minuscula = clave.casefold()
    fallas: list[str] = []

    if len(clave) < LARGO_MINIMO:
        fallas.append("Tiene que tener al menos %d caracteres." % LARGO_MINIMO)
    if len(clave) > LARGO_MAXIMO:
        fallas.append("No puede tener más de %d caracteres." % LARGO_MAXIMO)
    if fallas:
        return fallas

    if "verdeazul" in minuscula:
        fallas.append("No puede contener el nombre de la empresa.")
    for parte in (usuario, *nombre.split()):
        parte = normalizar(parte).casefold()
        if len(parte) >= 3 and parte in minuscula:
            fallas.append("No puede contener su nombre ni su usuario.")
            break

    # Quince veces la misma letra, o "abcabcabcabcabc", cumplen el largo pero
    # no aportan nada. Pocos caracteres distintos es la senal mas simple.
    if len(set(minuscula)) < 5:
        fallas.append("Usa muy pocos caracteres distintos.")

    if minuscula in _lista_prohibida():
        fallas.append("Es una contraseña común, de las primeras que se prueban.")
    elif _filtrada(clave):
        fallas.append("Aparece en filtraciones conocidas de otros sitios.")

    return fallas


def generar_temporal() -> str:
    """Una clave temporal para una cuenta nueva. 20 caracteres, unos 120 bits.

    La ve quien crea la cuenta, asi que la cuenta nace con debe_cambiar y no
    sirve para nada mas que cambiarla.
    """
    return secrets.token_urlsafe(15)
