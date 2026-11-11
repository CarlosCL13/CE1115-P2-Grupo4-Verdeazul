"""Los estados de periodos y mediciones, y quien puede moverlos.

C2 y C11 leen `periodo.estado`, C6 lee `medicion.estado`. Por eso los nombres
no se tocan sin avisar a quien escribe las politicas (persona 3).

    periodo      ABIERTO <-> CERRADO     solo Direccion de Certificacion
    medicion     REGISTRADA -> APROBADA | DEVUELTA     solo Verificador

Una medicion APROBADA o DEVUELTA no vuelve a REGISTRADA: no se modifica, se
enmienda (O4, persona 1). La base lo refuerza quitando UPDATE a app_rw sobre
las demas columnas (migracion 006).
"""

from app.errores import ErrorAPI

PERIODO_ABIERTO = "ABIERTO"
PERIODO_CERRADO = "CERRADO"

REGISTRADA = "REGISTRADA"
APROBADA = "APROBADA"
DEVUELTA = "DEVUELTA"

_TRANSICIONES_MEDICION = {REGISTRADA: {APROBADA, DEVUELTA}}


def exigir_transicion_medicion(actual: str, nuevo: str) -> None:
    if nuevo not in _TRANSICIONES_MEDICION.get(actual, set()):
        raise ErrorAPI(409, "estado_invalido",
                       "La medición ya está %s." % actual.lower())


def exigir_periodo_en(estado_actual: str, esperado: str) -> None:
    if estado_actual != esperado:
        raise ErrorAPI(409, "estado_invalido",
                       "El período ya está %s." % estado_actual.lower())


def mediciones_sin_aprobar(cur, periodo: int) -> int:
    """Cuantas quedan por decidir. Un periodo no cierra con REGISTRADAS.

    Las DEVUELTAS no cuentan: ya tienen decision, y su autor no puede
    corregirlas (inmutables), asi que esperarlas bloquearia el cierre para
    siempre.
    """
    cur.execute("SELECT count(*) AS n FROM mediciones "
                "WHERE periodo = %s AND estado = 'REGISTRADA'", (periodo,))
    return cur.fetchone()["n"]
