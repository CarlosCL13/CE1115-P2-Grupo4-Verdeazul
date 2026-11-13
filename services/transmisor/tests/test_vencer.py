"""La tarea vencer contra una bandeja de mentira."""

from datetime import date

from app.tareas import vencer
from test_transmitir import Cursor, abridor

AYER = date(2026, 11, 12)


def correr(diario, asignaciones=(), consentimientos=()):
    cur = Cursor("bandeja", diario,
                 respuestas=[list(asignaciones), list(consentimientos)])
    return vencer.ejecutar(abrir_bandeja=abridor(cur))


def test_las_fronteras_de_fecha_son_las_de_c1_y_c9():
    # Asignacion: vale el dia que vence (C1: vence >= hoy), vence despues.
    assert "vence < CURRENT_DATE" in vencer._ASIGNACIONES
    # Consentimiento: el dia que vence ya no sirve (C9: hoy < vence).
    assert "vence <= CURRENT_DATE" in vencer._CONSENTIMIENTOS
    # Solo toca lo que no estaba revocado: correrla dos veces no hace nada.
    assert "revocada_en IS NULL" in vencer._ASIGNACIONES
    assert "revocado_en IS NULL" in vencer._CONSENTIMIENTOS


def test_solo_cambia_la_fecha_de_revocacion():
    for sql in (vencer._ASIGNACIONES, vencer._CONSENTIMIENTOS):
        cambia = sql.split("SET", 1)[1].split("WHERE", 1)[0]
        assert cambia.strip() in ("revocada_en = now()", "revocado_en = now()")


def test_revoca_y_anota_un_evento_por_fila():
    diario = []
    r = correr(diario,
               asignaciones=[{"id": 5, "sujeto": 4, "zona": "CS", "vence": AYER}],
               consentimientos=[{"id": 2, "finca": 1, "tercero": 11, "vence": AYER}])
    assert r == {"tarea": "vencer", "asignaciones_revocadas": [5],
                 "consentimientos_revocados": [2]}

    inserts = [d for d in diario if d[1].startswith("INSERT")]
    assert len(inserts) == 1
    eventos = [(accion, sujeto, objeto, detalle.obj)
               for accion, sujeto, objeto, detalle in inserts[0][2]]
    assert eventos == [
        ("ASIGNACION_VENCIDA", "SISTEMA", "O8:5",
         {"asignado": "4", "zona": "CS", "vence": "2026-11-12"}),
        ("CONSENTIMIENTO_VENCIDO", "SISTEMA", "O7:2",
         {"finca": "1", "tercero": "11", "vence": "2026-11-12"}),
    ]
    # Revocacion y evento en la misma transaccion.
    assert diario[-1] == ("bandeja", "COMMIT", None)


def test_sin_nada_vencido_no_anota_nada():
    diario = []
    r = correr(diario)
    assert r["asignaciones_revocadas"] == [] and r["consentimientos_revocados"] == []
    assert not [d for d in diario if d[1].startswith("INSERT")]
