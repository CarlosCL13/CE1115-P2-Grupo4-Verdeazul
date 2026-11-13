"""Tarea `vencer`: revoca lo que ya vencio. HBAC-03, CU-07, CU-09.

Dos cosas tienen fecha de fin y dejan de dar acceso solas:

    O8 asignaciones tecnico-zona   vigente mientras vence >= hoy   (C1)
    O7 consentimientos a terceros  vigente mientras hoy < vence    (C9)

El motor ya las niega al vencer, porque C1 y C9 comparan con la fecha de
hoy. Esta tarea no es la que corta el acceso: lo deja asentado. Marca la
fila como revocada y anota un evento por cada una, para que la bitacora
responda «quien perdio que acceso y cuando» igual que si la hubiera revocado
una persona, y para que la tabla diga la verdad sin tener que comparar
fechas al leerla.

Las fronteras de fecha copian las de cada condicion: una asignacion vale el
dia que vence (>=), un consentimiento no (<, ver condiciones.rego).

Cada UPDATE revoca todo lo vencido de una vez y termina. Correrla dos veces
no hace nada la segunda: solo toca filas sin revocar.
"""

import logging

from app import bd

log = logging.getLogger("transmisor.vencer")

_ASIGNACIONES = (
    "UPDATE asignaciones_zona SET revocada_en = now() "
    "WHERE revocada_en IS NULL AND vence < CURRENT_DATE "
    "RETURNING id, sujeto, zona, vence")

_CONSENTIMIENTOS = (
    "UPDATE consentimientos SET revocado_en = now() "
    "WHERE revocado_en IS NULL AND vence <= CURRENT_DATE "
    "RETURNING id, finca, tercero, vence")


def ejecutar(*, abrir_bandeja=None) -> dict:
    abrir_bandeja = abrir_bandeja or bd.bandeja

    with abrir_bandeja() as cur:
        cur.execute(_ASIGNACIONES)
        asignaciones = cur.fetchall()
        cur.execute(_CONSENTIMIENTOS)
        consentimientos = cur.fetchall()

        bd.anotar(cur, [
            ("ASIGNACION_VENCIDA", "O8:%d" % a["id"],
             {"asignado": str(a["sujeto"]), "zona": a["zona"],
              "vence": a["vence"].isoformat()})
            for a in asignaciones
        ] + [
            ("CONSENTIMIENTO_VENCIDO", "O7:%d" % c["id"],
             {"finca": str(c["finca"]), "tercero": str(c["tercero"]),
              "vence": c["vence"].isoformat()})
            for c in consentimientos
        ])

    resultado = {
        "tarea": "vencer",
        "asignaciones_revocadas": [a["id"] for a in asignaciones],
        "consentimientos_revocados": [c["id"] for c in consentimientos],
    }
    log.info("vencer: %s", resultado)
    return resultado
