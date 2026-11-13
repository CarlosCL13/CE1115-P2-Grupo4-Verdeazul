"""La maquina de estados de una enmienda. C5 lee `enmienda.estado`.

    SOLICITADA --A (verificador)--> REVISADA --Cr (Dir. Certificacion)--> CERRADA
         \\
          --D (verificador)--> DEVUELTA

Tres personas distintas de punta a punta (SR-03): quien pide (C11), quien
revisa (C4) y quien cierra (C5). CERRADA y DEVUELTA son finales: una
enmienda devuelta no se reabre, se pide otra.

El motor ya niega cerrar lo que no esta REVISADA (C5 lo exige). Esto lo
vuelve a comprobar con la fila bloqueada, para que dos personas actuando a
la vez no puedan llevarla dos veces por el mismo camino.
"""

from app.errores import ErrorAPI

SOLICITADA = "SOLICITADA"
REVISADA = "REVISADA"
CERRADA = "CERRADA"
DEVUELTA = "DEVUELTA"

# Las que todavia esperan una decision. Mientras haya una, no se pide otra
# sobre la misma medicion.
ABIERTAS = (SOLICITADA, REVISADA)

_TRANSICIONES = {
    SOLICITADA: {REVISADA, DEVUELTA},
    REVISADA: {CERRADA},
}


def exigir_transicion(actual: str, nuevo: str) -> None:
    if nuevo not in _TRANSICIONES.get(actual, set()):
        raise ErrorAPI(409, "estado_invalido",
                       "La enmienda está %s: no se puede llevar a %s."
                       % (actual.lower(), nuevo.lower()))
