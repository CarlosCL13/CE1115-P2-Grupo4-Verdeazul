"""Tarea `transmitir`: de la bandeja de salida a la bitacora. Contrato 03.

Son dos bases y ninguna transaccion cubre las dos. Lo que hace que eso no
importe:

  1. Un candado en la bandeja, tomado al principio y soltado al final. Dos
     corridas cruzadas partirian la cadena en dos.
  2. El punto de partida es el eslabon del ultimo evento encadenado.
  3. Un lote acotado, en orden. Lo que falte va en la corrida siguiente.
  4. El eslabon se calcula siempre igual (app/eslabon.py).
  5. El uuid de la bitacora se deriva del id de la bandeja, y el INSERT salta
     los que ya estan.
  6. Primero se confirma la bitacora y despues la bandeja. Si algo falla
     entre los dos pasos, la corrida siguiente repite el mismo lote, con los
     mismos uuid y los mismos eslabones, y la bitacora no duplica nada.
  7. Se copia el `momento` de la bandeja, que es la hora de la operacion
     (D-19), no la de la copia.

Las conexiones se reciben como parametro para probar todo esto sin base. En
la nube son bd.bandeja() y bd.bitacora().
"""

import logging

from psycopg.types.json import Jsonb

from app import bd, config, eslabon

log = logging.getLogger("transmisor.transmitir")

# Numero del candado de pg_advisory_xact_lock. Solo lo toma esta tarea.
CANDADO = 42

# El orden de la cadena es (enviado_en, id): enviado_en es el mismo para todo
# un lote (now() no cambia dentro de una transaccion) y crece de un lote al
# siguiente; dentro del lote manda el id. Ordenar solo por id no sirve: un
# evento con id menor que se confirma tarde sale en un lote posterior, y el
# "ultimo por id" ya no seria el ultimo encadenado.
_ULTIMO_ESLABON = (
    "SELECT eslabon FROM eventos_pendientes "
    "WHERE enviado_en IS NOT NULL "
    "ORDER BY enviado_en DESC, id DESC LIMIT 1")

_LOTE = (
    "SELECT id, momento, accion, sujeto, objeto, resultado, motivo, detalle "
    "FROM eventos_pendientes "
    "WHERE enviado_en IS NULL "
    "  AND momento < now() - make_interval(secs => %s) "
    "ORDER BY id LIMIT %s")

# Sin destino en ON CONFLICT a proposito: con destino, PostgreSQL pide SELECT
# sobre la columna, y log_writer no lee. Sin destino basta INSERT.
_INSERTAR = (
    "INSERT INTO eventos "
    "(id, momento, accion, sujeto, objeto, resultado, motivo, detalle, eslabon) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT DO NOTHING")

# outbox_rw solo puede cambiar estas dos columnas (migraciones 010 y 012).
_MARCAR = (
    "UPDATE eventos_pendientes SET enviado_en = now(), eslabon = %s "
    "WHERE id = %s AND enviado_en IS NULL")


def _llave() -> bytes:
    secreto = config.LLAVE_CADENA
    return eslabon.llave_desde_texto(secreto.revelar() if secreto else None)


def sellar(llave: bytes, anterior: str, pendientes: list[dict]) -> list[tuple]:
    """Encadena el lote en orden. Devuelve (id_bandeja, evento, eslabon)."""
    sellados = []
    for fila in pendientes:
        evento = {
            "id": eslabon.id_en_bitacora(fila["id"]),
            "momento": fila["momento"],
            "accion": fila["accion"],
            "sujeto": fila["sujeto"],
            "objeto": fila["objeto"],
            # resultado es un enum en la bandeja y texto en la bitacora.
            "resultado": str(fila["resultado"]),
            "motivo": fila["motivo"],
            "detalle": fila["detalle"],
        }
        anterior = eslabon.calcular(llave, anterior, evento)
        sellados.append((fila["id"], evento, anterior))
    return sellados


def ejecutar(*, llave: bytes | None = None, tope: int | None = None,
             margen: int | None = None, abrir_bandeja=None,
             abrir_bitacora=None) -> dict:
    """Una corrida: un lote como maximo, y termina."""
    llave = llave if llave is not None else _llave()
    tope = tope or config.EVENTOS_POR_CORRIDA
    margen = config.MARGEN_SEGUNDOS if margen is None else margen
    abrir_bandeja = abrir_bandeja or bd.bandeja
    abrir_bitacora = abrir_bitacora or bd.bitacora

    with abrir_bandeja() as bandeja:
        bandeja.execute("SELECT pg_advisory_xact_lock(%s)", (CANDADO,))

        bandeja.execute(_ULTIMO_ESLABON)
        fila = bandeja.fetchone()
        anterior = fila["eslabon"] if fila else eslabon.INICIO

        bandeja.execute(_LOTE, (margen, tope))
        pendientes = bandeja.fetchall()
        if not pendientes:
            return {"tarea": "transmitir", "transmitidos": 0, "quedan_mas": False}

        sellados = sellar(llave, anterior, pendientes)

        # Paso 6: la bitacora se confirma al salir de este bloque, antes de
        # tocar la bandeja.
        with abrir_bitacora() as bitacora:
            bitacora.executemany(_INSERTAR, [
                (ev["id"], ev["momento"], ev["accion"], ev["sujeto"],
                 ev["objeto"], ev["resultado"], ev["motivo"],
                 Jsonb(ev["detalle"]) if ev["detalle"] is not None else None,
                 sello)
                for _, ev, sello in sellados])

        bandeja.executemany(_MARCAR, [(sello, id_bandeja)
                                      for id_bandeja, _, sello in sellados])

    resultado = {
        "tarea": "transmitir",
        "transmitidos": len(sellados),
        "primero": sellados[0][0],
        "ultimo": sellados[-1][0],
        # Si el lote salio lleno, probablemente quedan mas: van en la corrida
        # siguiente, no en un bucle aqui (§3.1).
        "quedan_mas": len(sellados) == tope,
    }
    log.info("transmitir: %s", resultado)
    return resultado
