"""Emite un evento de auditoria. Contrato 03.

    from app.bitacora import registrar

    with bd.transaccion():
        ...
        registrar(accion="SESION_INICIADA", sujeto="4", objeto="O10:4",
                  resultado="PERMITIDO")

Quien emite no sabe como se guarda. Aqui solo se inserta en la bandeja de
salida (eventos_pendientes) con el cursor de la transaccion en curso, para que
la operacion y su evento se confirmen juntos. Copiarlo a la otra base y
calcular el eslabon de la cadena es del transmisor (F5).

Si el resultado es DENEGADO, ademas se marca con bd.preservar(): la operacion
que se nego se revierte, pero el intento tiene que quedar (contrato 02, regla
4).

Version minima escrita por el frente de identidad, que la necesitaba el primer
dia. La firma es la del contrato y no cambia; el frente de bitacora puede
reemplazar el cuerpo sin que nadie mas toque su codigo.
"""

from psycopg.types.json import Jsonb

from app import bd

RESULTADOS = ("PERMITIDO", "DENEGADO")

# El contrato 03 dice que en un evento nunca entran contrasenas, cedulas,
# telefonos, llaves ni cookies. Esto no reemplaza el cuidado de quien llama,
# pero ataja el error mas comun: pasar el cuerpo de la peticion entero.
# Coincidencia exacta a proposito, para no estorbar claves legitimas como
# "huella_llave", que el contrato 03 pone de ejemplo.
_CLAVES_PROHIBIDAS = frozenset({
    "clave", "clave_actual", "clave_nueva", "contrasena", "password",
    "token", "cookie", "cedula", "telefono", "secreto", "totp_secreto",
})


class EventoInvalido(ValueError):
    """El evento no cumple el contrato 03."""


def _revisar_detalle(detalle: dict | None) -> None:
    if not detalle:
        return
    for clave in detalle:
        if str(clave).lower() in _CLAVES_PROHIBIDAS:
            raise EventoInvalido(
                "El detalle de un evento no lleva %r: el contrato 03 prohibe "
                "datos personales y secretos en la bitacora." % clave)


def registrar(*, accion: str, sujeto: str, objeto: str, resultado: str,
              motivo: str | None = None, detalle: dict | None = None) -> None:
    """Anota un evento en la bandeja de salida, dentro de la transaccion."""
    if resultado not in RESULTADOS:
        raise EventoInvalido("resultado tiene que ser PERMITIDO o DENEGADO")
    if resultado == "DENEGADO" and not motivo:
        raise EventoInvalido("un evento DENEGADO lleva motivo (contrato 03)")
    _revisar_detalle(detalle)

    fila = {
        "accion": accion,
        "sujeto": str(sujeto),
        "objeto": str(objeto),
        "resultado": resultado,
        "motivo": motivo,
        "detalle": Jsonb(detalle) if detalle else None,
    }

    cur = bd.cursor_actual()
    cur.execute(
        "INSERT INTO eventos_pendientes "
        "(accion, sujeto, objeto, resultado, motivo, detalle) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        tuple(fila.values()),
    )

    if resultado == "DENEGADO":
        bd.preservar(fila)
