"""Segundo factor: codigos de seis digitos de una aplicacion autenticadora.

TOTP es el RFC 6238: el telefono y el servidor comparten un secreto y cada uno
calcula, cada 30 segundos, HMAC-SHA1(secreto, numero de ventana) truncado a
seis digitos. Si coinciden, quien escribio el codigo tiene el telefono.

P1 preferia llaves de acceso (passkeys) y aceptaba TOTP como alternativa. D-05
explica por que aqui solo hay TOTP. SMS sigue prohibido, como dijo P1.

Tres cosas que este modulo agrega a la biblioteca:

  tolerancia   se acepta la ventana anterior y la siguiente, porque el reloj
               del telefono no esta perfectamente sincronizado
  sin repetir  cada codigo sirve una sola vez. La tolerancia hace que un codigo
               valga hasta 90 segundos; sin esto, quien lo vea por encima del
               hombro lo puede usar despues (credenciales.totp_ultimo_paso)
  cifrado      el secreto se guarda cifrado con AES-GCM. Quien lea la base no
               puede generar codigos
"""

import hashlib
import hmac
import secrets
import time

import pyotp
import segno

from app.auth import cifrado

EMISOR = "Verdeazul Carbono"
DIGITOS = 6
INTERVALO = 30
TOLERANCIA = 1

# RC-02: codigos de recuperacion de un solo uso, entregados al activar.
CANTIDAD_RECUPERACION = 8

# Los roles que no pueden entrar sin segundo factor. D-05: "mantenemos TOTP
# para los roles que pueden aprobar, emitir o cambiar permisos". Los demas
# pueden activarlo, y una vez activo se les pide siempre.
ROLES_OBLIGADOS = frozenset({
    "DIRECCION_GENERAL",
    "DIRECCION_CERTIFICACION",
    "PERSONAL_ADMINISTRATIVO",
    "VERIFICADOR",
})


def _contexto(cuenta: int) -> str:
    return "credenciales.totp_secreto:%d" % cuenta


def nuevo_secreto() -> str:
    """160 bits en base32, lo que el RFC 4226 recomienda."""
    return pyotp.random_base32(length=32)


def cifrar_secreto(secreto: str, cuenta: int) -> bytes:
    return cifrado.cifrar(secreto, _contexto(cuenta))


def descifrar_secreto(blob: bytes, cuenta: int) -> str:
    return cifrado.descifrar(blob, _contexto(cuenta))


def uri(secreto: str, usuario: str) -> str:
    """La direccion otpauth:// que lee la aplicacion del telefono."""
    return pyotp.TOTP(secreto, digits=DIGITOS, interval=INTERVALO).provisioning_uri(
        name=usuario, issuer_name=EMISOR)


def qr_svg(direccion: str) -> str:
    """El QR como data URI de SVG, para un <img> sin JavaScript.

    La CSP del borde permite img-src data:, y nada mas hace falta.
    """
    return segno.make(direccion, error="m").svg_data_uri(scale=5, border=2)


def verificar(secreto: str, codigo: str, ultimo_paso: int | None,
              ahora: float | None = None) -> int | None:
    """El numero de ventana del codigo si es valido y nuevo; None si no.

    Quien llama guarda el numero devuelto en credenciales.totp_ultimo_paso.
    """
    codigo = "".join(c for c in str(codigo) if c.isdigit())
    if len(codigo) != DIGITOS:
        return None
    ahora = time.time() if ahora is None else ahora
    generador = pyotp.TOTP(secreto, digits=DIGITOS, interval=INTERVALO)
    paso_actual = int(ahora // INTERVALO)

    aceptado = None
    for desfase in range(-TOLERANCIA, TOLERANCIA + 1):
        paso = paso_actual + desfase
        esperado = generador.at(paso * INTERVALO)
        # Comparacion de tiempo constante, aunque sean seis digitos.
        if hmac.compare_digest(esperado, codigo):
            aceptado = paso
    if aceptado is None:
        return None
    if ultimo_paso is not None and aceptado <= ultimo_paso:
        return None
    return aceptado


def codigos_recuperacion() -> list[str]:
    """Ocho codigos como "K7QM-2XRP-9D", unos 50 bits cada uno."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    codigos = []
    for _ in range(CANTIDAD_RECUPERACION):
        crudo = "".join(secrets.choice(alfabeto) for _ in range(10))
        codigos.append("%s-%s-%s" % (crudo[:4], crudo[4:8], crudo[8:]))
    return codigos


def huella_recuperacion(codigo: str) -> str:
    """Lo que se guarda de un codigo de recuperacion. Sin guiones ni espacios."""
    limpio = "".join(c for c in codigo.upper() if c.isalnum())
    return hashlib.sha256(limpio.encode("ascii", "ignore")).hexdigest()
