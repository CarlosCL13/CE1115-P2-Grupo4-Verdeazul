"""Tarea `cadena`: comprueba que nadie altero la bitacora. LG-07, AI-07.

Relee la bitacora entera con log_reader, en orden de `secuencia`, y
recalcula cada eslabon con la misma funcion que uso `transmitir`
(app/eslabon.py). Que el eslabon guardado coincida con el recalculado prueba
que el evento no cambio desde que se sello.

Tres cosas que detecta, y como:

  - Un evento modificado: su eslabon no cuadra con su contenido.
  - Un evento borrado del medio: el eslabon del siguiente no cuadra, porque
    se calculo con el del borrado como anterior.
  - Eventos borrados del final: la cadena que queda cuadra sola, asi que
    eso no lo ve el recalculo. Lo ve la «cola»: la bandeja de salida sabe
    cuantos eventos se enviaron y con que ultimo eslabon, y la bitacora
    tiene que tener los mismos.

Para seguir recalculando despues de un eslabon roto se usa el eslabon
guardado como anterior, no el recalculado. Asi se marca solo el evento
alterado (y el siguiente a un borrado), no todos los que vienen despues.

Huecos en `secuencia` son normales (un INSERT que falla gasta un numero) y no
cuentan como borrados: la cadena prueba integridad, no numeracion.

Lee por lotes y termina: la bitacora es finita y cada vuelta avanza. No
reintenta (§3.1).
"""

import logging

from app import bd, config, eslabon
from app.tareas.transmitir import CANDADO, _ULTIMO_ESLABON

log = logging.getLogger("transmisor.cadena")

LOTE = 1000

_LEER = (
    "SELECT secuencia, id, momento, accion, sujeto, objeto, resultado, "
    "       motivo, detalle, eslabon "
    "FROM eventos WHERE secuencia > %s ORDER BY secuencia LIMIT %s")

_ENVIADOS = ("SELECT count(*) AS n FROM eventos_pendientes "
             "WHERE enviado_en IS NOT NULL")


def _llave() -> bytes:
    secreto = config.LLAVE_CADENA
    return eslabon.llave_desde_texto(secreto.revelar() if secreto else None)


def recorrer(llave: bytes, lotes) -> dict:
    """Recalcula la cadena sobre los lotes de filas, en orden.

    Separado de las conexiones para probarlo sin base.
    """
    anterior = eslabon.INICIO
    total, rotos, primer_roto = 0, 0, None
    for filas in lotes:
        for fila in filas:
            if not eslabon.coincide(fila["eslabon"],
                                    eslabon.calcular(llave, anterior, fila)):
                rotos += 1
                if primer_roto is None:
                    primer_roto = fila["secuencia"]
            anterior = fila["eslabon"]
            total += 1
    return {"eventos": total, "rotos": rotos, "primer_roto": primer_roto,
            "ultimo_eslabon": anterior}


def _lotes(cur, tamano: int):
    desde = 0
    while True:
        cur.execute(_LEER, (desde, tamano))
        filas = cur.fetchall()
        if not filas:
            return
        yield filas
        desde = filas[-1]["secuencia"]


def ejecutar(*, llave: bytes | None = None, abrir_bandeja=None,
             abrir_lectura=None, tamano: int = LOTE) -> dict:
    llave = llave if llave is not None else _llave()
    abrir_bandeja = abrir_bandeja or bd.bandeja
    abrir_lectura = abrir_lectura or bd.lectura

    with abrir_bandeja() as bandeja:
        # El mismo candado que transmitir: mientras se compara, nadie agrega
        # eventos a la cadena, asi que la cola de la bandeja y la de la
        # bitacora se miran en el mismo instante.
        bandeja.execute("SELECT pg_advisory_xact_lock(%s)", (CANDADO,))
        bandeja.execute(_ENVIADOS)
        enviados = bandeja.fetchone()["n"]
        bandeja.execute(_ULTIMO_ESLABON)
        fila = bandeja.fetchone()
        ultimo_enviado = fila["eslabon"] if fila else eslabon.INICIO

        with abrir_lectura() as lectura:
            resultado = recorrer(llave, _lotes(lectura, tamano))

        cola_completa = (resultado["eventos"] == enviados and
                         eslabon.coincide(resultado["ultimo_eslabon"],
                                          ultimo_enviado))
        intacta = resultado["rotos"] == 0 and cola_completa
        informe = {
            "tarea": "cadena",
            "intacta": intacta,
            "eventos": resultado["eventos"],
            "enviados_segun_bandeja": enviados,
            "rotos": resultado["rotos"],
            "primer_roto": resultado["primer_roto"],
            "cola_completa": cola_completa,
        }
        # La comprobacion misma queda en la bitacora: «su integridad se
        # comprueba periodicamente» (LG-07) con evidencia de cada vez.
        bd.anotar(bandeja, [(
            "CADENA_VERIFICADA" if intacta else "CADENA_ROTA", "O11:*",
            {k: v for k, v in informe.items() if k != "tarea"})])

    if intacta:
        log.info("cadena: %s", informe)
    else:
        log.error("cadena ROTA: %s", informe)
    return informe
